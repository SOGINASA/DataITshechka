#!/usr/bin/env bash
# Invoked by GitHub Actions with an image built and tested on its runner.
set -Eeuo pipefail
umask 077

main() {
  repo=${1:?Usage: deploy.sh REPOSITORY COMMIT_SHA IMAGE_ARCHIVE}
  target=${2:?Missing commit SHA}
  archive=${3:?Missing image archive}
  [[ "$target" =~ ^[0-9a-f]{40}$ ]] || { echo 'Invalid commit SHA' >&2; exit 2; }
  repo=$(cd "$repo" && pwd)
  [[ -f "$archive" ]] || { echo 'Image archive is missing' >&2; exit 1; }
  cd "$repo"
  state="$repo/.deploy"
  mkdir -p "$state/backups"
  exec 9>"$state/deploy.lock"
  flock -w 300 9

  export GIT_TERMINAL_PROMPT=0
  [[ $(git branch --show-current) == master ]] || { echo 'Expected master branch' >&2; exit 1; }
  [[ -z $(git status --porcelain --untracked-files=normal) ]] || {
    echo 'Checkout has local changes; deployment stopped without overwriting them.' >&2
    exit 1
  }
  git fetch --quiet origin master
  git merge-base --is-ancestor "$target" origin/master || {
    echo 'Requested revision is not on origin/master.' >&2; exit 1;
  }
  git merge-base --is-ancestor HEAD "$target" || {
    echo 'Refusing an outdated release or divergent checkout.' >&2; exit 1;
  }
  git merge --ff-only --quiet "$target"
  [[ -f backend/.env ]] || { echo 'backend/.env is missing' >&2; exit 1; }

  export BACKEND_IMAGE="bimbombam-backend:$target"
  compose=(docker compose --project-name bimbombam --env-file "$repo/backend/.env"
    -f "$repo/backend/docker-compose.yml" -f "$repo/backend/compose.production.yml")
  "${compose[@]}" config --quiet

  on_error() {
    result=$?
    printf '%s\n' "$target" > "$state/failed-revision"
    echo "Deployment failed ($result) at $target; inspect the GitHub Actions log." >&2
    echo 'Database recovery is manual; no automatic destructive rollback is performed.' >&2
    exit "$result"
  }
  trap on_error ERR

  echo "Deploying tested image for revision $target"
  container=$("${compose[@]}" ps -aq backend)
  if [[ -n "$container" ]]; then
    old_image=$(docker inspect --format '{{.Image}}' "$container")
    docker tag "$old_image" bimbombam-backend:previous
  fi

  # No builds or dependency installation run on the VPS.
  docker load --input "$archive"
  image_revision=$(docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$BACKEND_IMAGE")
  [[ "$image_revision" == "$target" ]]
  "${compose[@]}" up -d --no-recreate --wait --wait-timeout 120 postgres

  "${compose[@]}" stop -t 60 backend
  backup="$state/backups/$(date -u +%Y%m%dT%H%M%SZ)-${target:0:12}.dump"
  "${compose[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup.partial"
  test -s "$backup.partial"
  "${compose[@]}" exec -T postgres pg_restore --list < "$backup.partial" > /dev/null
  mv "$backup.partial" "$backup"
  echo "Database snapshot: $backup"

  # entrypoint applies migrations and the idempotent initial checklist.
  "${compose[@]}" up -d --no-deps --no-build --force-recreate --wait --wait-timeout 180 backend
  "${compose[@]}" exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6767/api/ready', timeout=5)"
  docker tag "$BACKEND_IMAGE" bimbombam-backend:current
  printf '%s\n' "$target" > "$state/deployed-revision.tmp"
  mv "$state/deployed-revision.tmp" "$state/deployed-revision"
  rm -f "$state/failed-revision"
  echo "Backend ready on 127.0.0.1:6767, revision $target"
}

main "$@"
