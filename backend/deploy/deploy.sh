#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

main() {
# This checkout is dedicated to deployment; local changes are never discarded.
repo=$(git -C "$(dirname "${BASH_SOURCE[0]}")" rev-parse --show-toplevel)
cd "$repo"
state="$repo/.deploy"
mkdir -p "$state/backups"
exec 9>"$state/deploy.lock"
flock -n 9 || exit 0

force=false
case "${1:-}" in
  '') ;;
  --force) force=true ;;
  *) echo 'Usage: deploy.sh [--force]' >&2; exit 2 ;;
esac

export GIT_TERMINAL_PROMPT=0
[[ $(git branch --show-current) == master ]] || { echo 'Expected master branch' >&2; exit 1; }
[[ -z $(git status --porcelain --untracked-files=normal) ]] || {
  echo 'Checkout has local changes; deployment stopped without overwriting them.' >&2
  exit 1
}
git fetch --quiet origin master
target=$(git rev-parse origin/master)
git merge-base --is-ancestor HEAD "$target" || {
  echo 'Checkout diverged from origin/master; fast-forward required.' >&2
  exit 1
}
git merge --ff-only --quiet "$target"

previous=$(cat "$state/deployed-revision" 2>/dev/null || true)
failed=$(cat "$state/failed-revision" 2>/dev/null || true)
if ! "$force"; then
  if [[ "$failed" == "$target" ]]; then
    echo "Revision $target previously failed; fix the cause and run with --force."
    exit 0
  fi
  if [[ -n "$previous" ]] && git diff --quiet "$previous" "$target" -- backend/; then
    exit 0
  fi
fi

[[ -f backend/.env ]] || { echo 'Create backend/.env first; see backend/deploy/README.md' >&2; exit 1; }
cd "$repo/backend"
compose=(docker compose --project-name bimbombam --env-file "$repo/backend/.env" -f "$repo/backend/docker-compose.yml")
"${compose[@]}" config --quiet

on_error() {
  result=$?
  printf '%s\n' "$target" > "$state/failed-revision"
  echo "Deployment failed ($result) at $target. Inspect journalctl -u bimbombam-deploy.service." >&2
  echo 'Database recovery is manual; no automatic destructive rollback is performed.' >&2
  exit "$result"
}
trap on_error ERR

echo "Deploying backend revision $target"
# Build before interrupting traffic. PostgreSQL is never recreated by this script.
"${compose[@]}" build backend
"${compose[@]}" up -d --no-recreate --wait --wait-timeout 120 postgres

container=$("${compose[@]}" ps -aq backend)
if [[ -n "$container" ]]; then
  old_image=$(docker inspect --format '{{.Image}}' "$container")
  docker tag "$old_image" bimbombam-backend:previous
fi

# Stop writes before the snapshot so the backup represents pre-migration state.
"${compose[@]}" stop -t 60 backend
backup="$state/backups/$(date -u +%Y%m%dT%H%M%SZ)-${target:0:12}.dump"
"${compose[@]}" exec -T postgres sh -c 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc' > "$backup.partial"
test -s "$backup.partial"
"${compose[@]}" exec -T postgres pg_restore --list < "$backup.partial" > /dev/null
mv "$backup.partial" "$backup"
echo "Database snapshot: $backup"

# entrypoint.sh applies migrations and the idempotent initial checklist.
"${compose[@]}" up -d --no-deps --no-build --force-recreate --wait --wait-timeout 180 backend
"${compose[@]}" exec -T backend python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:6767/api/ready', timeout=5)"
printf '%s\n' "$target" > "$state/deployed-revision.tmp"
mv "$state/deployed-revision.tmp" "$state/deployed-revision"
rm -f "$state/failed-revision"
echo "Backend ready on 127.0.0.1:6767, revision $target"
}

# Parse the entire function before git updates this script on disk.
main "$@"
