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
  *'build backend'*) [[ ${MOCK_BUILD_FAIL:-0} == 0 ]] || exit 18 ;;
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
mkdir -p backend/deploy frontend
cp "$source_script" backend/deploy/deploy.sh
printf '.deploy/\nbackend/.env\n' > .gitignore
printf 'initial\n' > backend/app.txt
printf 'initial\n' > frontend/app.txt
git add .
git commit -qm initial
git push -q origin master
printf 'POSTGRES_PASSWORD=keep-this-value\n' > backend/.env

run_deploy() { bash backend/deploy/deploy.sh "$@"; }
expect_failure() {
  if run_deploy "$@"; then
    echo 'Expected deployment to fail' >&2
    exit 1
  fi
}
assert_no_start() {
  if grep -q 'up .*--force-recreate.*backend' "$MOCK_LOG"; then
    echo 'Backend started after a failed prerequisite' >&2
    exit 1
  fi
}

run_deploy
test "$(cat .deploy/deployed-revision)" = "$(git rev-parse HEAD)"
test "$(find .deploy/backups -name '*.dump' | wc -l)" -eq 1
grep -q 'up .*--force-recreate.*backend' "$MOCK_LOG"
tag_line=$(grep -n '^tag ' "$MOCK_LOG" | head -1 | cut -d: -f1)
build_line=$(grep -n 'build backend' "$MOCK_LOG" | head -1 | cut -d: -f1)
test "$tag_line" -lt "$build_line"
echo 'PASS: initial deployment, backup, readiness and revision'
echo 'PASS: running image retained before build replaces its tag'

: > "$MOCK_LOG"
run_deploy
test ! -s "$MOCK_LOG"
echo changed >> frontend/app.txt
git add frontend/app.txt
git commit -qm frontend-only
git push -q origin master
run_deploy
test ! -s "$MOCK_LOG"
echo 'PASS: unchanged and frontend-only commits do not rebuild'

echo changed >> backend/app.txt
expect_failure
test ! -s "$MOCK_LOG"
echo 'PASS: local changes preserved'
git add backend/app.txt
git commit -qm backend-change
git push -q origin master

export MOCK_BACKUP_FAIL=1
expect_failure
assert_no_start
test "$(cat .deploy/failed-revision)" = "$(git rev-parse HEAD)"
unset MOCK_BACKUP_FAIL
: > "$MOCK_LOG"
run_deploy
test ! -s "$MOCK_LOG"
echo 'PASS: failed backup blocks migration/start and automatic retries'

run_deploy --force
test ! -f .deploy/failed-revision
grep -q 'up .*--force-recreate.*backend' "$MOCK_LOG"
test "$(cat backend/.env)" = POSTGRES_PASSWORD=keep-this-value
echo 'PASS: explicit retry succeeds and environment remains unchanged'

: > "$MOCK_LOG"
export MOCK_BUILD_FAIL=1
expect_failure --force
unset MOCK_BUILD_FAIL
assert_no_start
if grep -q 'stop -t' "$MOCK_LOG"; then
  echo 'Build failure interrupted running backend' >&2
  exit 1
fi
echo 'PASS: build failure does not stop the backend'

: > "$MOCK_LOG"
echo ahead >> backend/app.txt
git add backend/app.txt
git commit -qm local-only
expect_failure
test ! -s "$MOCK_LOG"
echo 'PASS: divergent checkout rejected without Docker operations'
