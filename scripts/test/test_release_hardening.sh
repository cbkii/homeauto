#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT_DIR"

fail(){ echo "FAIL: $*"; exit 1; }
pass(){ echo "PASS: $*"; }

scan_files=(README.md install.sh update.sh uninstall.sh)
while IFS= read -r f; do scan_files+=("$f"); done < <(find docs scripts .github/workflows -type f \( -name '*.md' -o -name '*.sh' -o -name '*.yml' \) | sort)

search_cmd() {
  if command -v rg >/dev/null 2>&1; then
    rg "$@"
  else
    grep -R "$@"
  fi
}

# 1) no unsafe eval in runtime scripts
if search_cmd -n "\beval\b" scripts install.sh update.sh uninstall.sh 2>/dev/null | grep -v 'scripts/test/test_release_hardening.sh' | grep -Ev '^[^:]+:[0-9]+:[[:space:]]*#'; then
  fail "unexpected eval usage"
fi
pass "no unsafe eval usage"

# 2) malformed command/token regressions across docs/scripts/workflows
# NOTE: this file is excluded from the scan to avoid matching its own pattern definition.
# shellcheck disable=SC2016
pattern='cp\.env|\.env\.example\.env|source\.env|\[\[? -f\.env|install -m 0600\.env|sudo\./|run_or_flag\./|run:\./|if!|find\.|"\$MODE"!=|"\$UNINSTALL_MODE"!=|using\.env|but\.env|no\.env|before\.env|and\.env'
if search_cmd -nE "$pattern" "${scan_files[@]}" 2>/dev/null | grep -v 'scripts/test/test_release_hardening\.sh'; then
  fail "malformed command/token pattern found"
fi
pass "no malformed command/token regressions"

# 3) ADB serial format checks
ANDROID_TV_PORT=5555 bash -c 'source scripts/adb/_adb_common.sh; [[ "$(adb_serial 192.168.1.60)" == "192.168.1.60:5555" ]]' || fail "adb serial default port"
ANDROID_TV_PORT=4444 bash -c 'source scripts/adb/_adb_common.sh; [[ "$(adb_serial 10.0.0.8)" == "10.0.0.8:4444" ]]' || fail "adb serial custom port"
pass "adb serial formatting"

# 4) profile model: core is default (no explicit core profile), zigbee/extras optional
grep -q -- '--with-zigbee' install.sh || fail "install flag missing"
grep -q -- '--with-extras' install.sh || fail "install flag missing"
grep -q -- '--with-all' install.sh || fail "install flag missing"
! grep -q 'profiles: \["core"\]' docker-compose.yml || fail "core should not require explicit profile"
grep -q 'profiles: \["zigbee"\]' docker-compose.yml || fail "zigbee profile missing"
grep -q 'profiles: \["extras"\]' docker-compose.yml || fail "extras profile missing"
pass "compose profile model"

# 5) Docker minimum version guard presence + comparison behavior examples
grep -q 'MIN_DOCKER_VERSION="23.0.0"' install.sh || fail "docker min version missing"
version_ge_test(){ local a="${1%%[-+]*}" b="${2%%[-+]*}"; [[ "$(printf '%s\n%s\n' "$b" "$a" | sort -V | tail -n1)" == "$a" ]]; }
version_ge_test 23.0.0 23.0.0 || fail "version compare equal"
version_ge_test 24.0.7+dfsg 23.0.0 || fail "version compare suffix"
version_ge_test 25.0.0 23.0.0 || fail "version compare newer"
! version_ge_test 20.10.24 23.0.0 || fail "version compare older"
pass "docker version guard semantics"

# 6) Zigbee device validation is conditional on zigbee profile
# shellcheck disable=SC2016
grep -q 'if \[\[ ",\$PROFILES," == \*",zigbee,"\* \]\] && \[\[ ! -e "\$ZIGBEE_DEVICE" \]\]' install.sh || fail "zigbee conditional validation missing"
pass "zigbee conditional validation"

# 7) smoke harness uses argv-safe execution
# shellcheck disable=SC2016
grep -q 'if "\$@" >>"\$OUTPUT" 2>&1; then' scripts/smoke/run_release_smoke.sh || fail "smoke argv-safe execution missing"
pass "smoke verify argv-safe execution"

# 8) backup script marks dump status in manifest and partial failure
grep -q 'backup-manifest.txt' scripts/stack/backup.sh || fail "backup manifest missing"
grep -q 'db_logical_dump_status' scripts/stack/backup.sh || fail "db dump status missing"
grep -q 'exit 2' scripts/stack/backup.sh || fail "partial-backup non-zero exit missing"
pass "backup manifest status and partial failure"

echo "All release-hardening static tests passed"
