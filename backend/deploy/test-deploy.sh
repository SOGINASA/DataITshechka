#!/usr/bin/env bash
set -Eeuo pipefail

source_script=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/deploy.sh
sandbox=$(mktemp -d /tmp/bimbombam-deploy-test.XXXXXXXX)
trap 'rm -rf -- "$sandbox"' EXIT
export MOCK_LOG="$sandbox/docker.log"
mkdir -p "$sandbox/bin"
cat > "$sandbox/bin/docker" <<'MOCK'
#!/usr/bin/env bash
set -eu
echo "$*" >> "$MOCK_LOG"
case "$*" in
  'build '*|*' build '*) echo 'VPS must not build images' >&2; exit 99 ;;
  'load '*) [[ ${MOCK_LOAD_FAIL:-0} == 0 ]] || exit 18 ;;
  'image inspect '*) echo "${MOCK_IMAGE_REVISION:-$MOCK_TARGET}" ;;
  *'ps -aq backend'*) echo fake-backend ;;
  'inspect '*) echo sha256:previous-image ;;
  *'pg_dump '*) [[ ${MOCK_BACKUP_FAIL:-0} == 0 ]] || exit 17; echo fake-dump ;;
  *'pg_restore --list'*) cat > /dev/null ;;
esac
MOCK
chmod +x "$sandbox/bin/docker"
export PATH="$sandbox/bin:$PATH"
git init -q --bare --initial-branch=master "$sandbox/origin.git"
git clone -q "$sandbox/origin.git" "$sandbox/repo" 2>/dev/null
cd "$sandbox/repo"
git config user.name 'Deploy test'
git config user.email 'deploy-test@example.invalid'
mkdir -p backend
printf '.deploy/\nbackend/.env\n' > .gitignore
printf 'initial\n' > backend/app.txt
git add .
git commit -qm initial
git push -q origin master
printf 'POSTGRES_PASSWORD=keep-this-value\n' > backend/.env
printf fake-image > "$sandbox/image.tar.gz"
release_sha=$(git rev-parse HEAD)
first_sha=$release_sha

run_deploy() { MOCK_TARGET="$release_sha" bash "$source_script" "$PWD" "$release_sha" "$sandbox/image.tar.gz"; }
expect_failure() {
  if run_deploy; then echo 'Expected deployment to fail' >&2; exit 1; fi
}
assert_no_start() {
  if grep -q 'up .*--force-recreate.*backend' "$MOCK_LOG"; then
    echo 'Backend started after a failed prerequisite' >&2; exit 1
  fi
}
assert_no_stop() {
  if grep -q 'stop -t' "$MOCK_LOG"; then
    echo 'Running backend stopped before image validation' >&2; exit 1
  fi
}

run_deploy
test "$(cat .deploy/deployed-revision)" = "$release_sha"
test "$(find .deploy/backups -name '*.dump' | wc -l)" -eq 1
grep -q 'up .*--no-build.*backend' "$MOCK_LOG"
tag_line=$(grep -n '^tag ' "$MOCK_LOG" | head -1 | cut -d: -f1)
load_line=$(grep -n '^load ' "$MOCK_LOG" | head -1 | cut -d: -f1)
test "$tag_line" -lt "$load_line"
echo 'PASS: archive deployment without builds, backup, readiness and retained image'

: > "$MOCK_LOG"
echo changed >> backend/app.txt
expect_failure
test ! -s "$MOCK_LOG"
echo 'PASS: local changes preserved'
git add backend/app.txt
git commit -qm backend-change
git push -q origin master
release_sha=$(git rev-parse HEAD)

export MOCK_BACKUP_FAIL=1
expect_failure
assert_no_start
test "$(cat .deploy/deployed-revision)" = "$first_sha"
test "$(cat .deploy/failed-revision)" = "$release_sha"
unset MOCK_BACKUP_FAIL
echo 'PASS: failed backup blocks migration/start and preserves successful revision'

run_deploy
test ! -f .deploy/failed-revision
test "$(cat backend/.env)" = POSTGRES_PASSWORD=keep-this-value
echo 'PASS: explicit workflow retry succeeds without replacing environment'

: > "$MOCK_LOG"
export MOCK_LOAD_FAIL=1
expect_failure
unset MOCK_LOAD_FAIL
assert_no_start
assert_no_stop
echo 'PASS: archive load failure does not stop the backend'

: > "$MOCK_LOG"
export MOCK_IMAGE_REVISION=wrong-revision
expect_failure
unset MOCK_IMAGE_REVISION
assert_no_start
assert_no_stop
echo 'PASS: wrong image revision rejected before stopping the backend'

: > "$MOCK_LOG"
release_sha=$first_sha
expect_failure
test ! -s "$MOCK_LOG"
echo 'PASS: older workflow cannot roll back a newer checkout'

echo ahead >> backend/app.txt
git add backend/app.txt
git commit -qm local-only
release_sha=$(git rev-parse HEAD)
expect_failure
test ! -s "$MOCK_LOG"
echo 'PASS: revision outside origin/master rejected'
