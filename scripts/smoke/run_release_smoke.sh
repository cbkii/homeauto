#!/usr/bin/env bash
set -euo pipefail

usage() {
  cat <<USAGE
Usage: ./scripts/smoke/run_release_smoke.sh [options]

Options:
  --mode verify|full   verify=non-destructive checks (default), full=install/update/uninstall cycle
  --output <file>      markdown report path (default: ./artifacts/smoke-report-<mode>-<timestamp>.md)
  --bridge-test        in full mode, publish a sample MQTT action and capture bridge logs
  --bridge-payload <p> payload used for --bridge-test (default: 192.168.1.60)
  --uninstall-mode preserve|purge
                      full mode cleanup behavior (default: preserve)
  -h, --help           show help

Notes:
  - verify mode requires docker + docker compose availability but does not mutate host state.
  - full mode requires root/sudo and an already-configured .env with valid devices.
USAGE
}

MODE="verify"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUTPUT=""
BRIDGE_TEST=0
BRIDGE_PAYLOAD="192.168.1.60"
UNINSTALL_MODE="preserve"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --mode)
      MODE="${2:-}"
      shift
      ;;
    --output)
      OUTPUT="${2:-}"
      shift
      ;;
    --bridge-test)
      BRIDGE_TEST=1
      ;;
    --bridge-payload)
      BRIDGE_PAYLOAD="${2:-}"
      shift
      ;;
    --uninstall-mode)
      UNINSTALL_MODE="${2:-}"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1"
      usage
      exit 1
      ;;
  esac
  shift
done

if [[ -z "$OUTPUT" ]]; then
  OUTPUT="./artifacts/smoke-report-${MODE}-${STAMP}.md"
fi

if [[ "$MODE" != "verify" && "$MODE" != "full" ]]; then
  echo "Invalid --mode '$MODE' (expected verify|full)"
  exit 1
fi

if [[ "$UNINSTALL_MODE" != "preserve" && "$UNINSTALL_MODE" != "purge" ]]; then
  echo "Invalid --uninstall-mode '$UNINSTALL_MODE' (expected preserve|purge)"
  exit 1
fi

mkdir -p "$(dirname "$OUTPUT")"

report() {
  printf '%s\n' "$1" >>"$OUTPUT"
}

run_capture() {
  local cmd="$*"
  report ""
  report "## $cmd"
  report '```text'
  if "$@" >>"$OUTPUT" 2>&1; then
    report "[PASS] $cmd"
  else
    report "[FAIL] $cmd"
    report '```'
    return 1
  fi
  report '```'
}

warn_note() {
  report ""
  report "[WARN] $1"
}

: >"$OUTPUT"
report "# Release smoke report"
report "- Date (UTC): $(date -u)"
report "- Mode: $MODE"
if [[ -r /etc/os-release ]]; then
  # shellcheck disable=SC1091
  source /etc/os-release
  report "- Host OS: ${PRETTY_NAME:-unknown}"
  report "- Host codename: ${VERSION_CODENAME:-unknown}"
fi
report "- Bridge test: $([[ $BRIDGE_TEST -eq 1 ]] && echo enabled || echo disabled)"
report "- Full uninstall mode: $UNINSTALL_MODE"

overall_status=0

run_or_flag() {
  if ! run_capture "$@"; then
    overall_status=1
  fi
}

run_or_flag_quiet() {
  local cmd="$*"
  report ""
  report "## $cmd"
  report '```text'
  if "$@" >/dev/null 2>&1; then
    report "[PASS] $cmd"
  else
    report "[FAIL] $cmd"
    overall_status=1
  fi
  report '```'
}

run_or_flag uname -a
run_or_flag bash --version

if ! command -v docker >/dev/null 2>&1; then
  report ""
  report "[FAIL] docker not installed/in PATH"
  echo "Report written to $OUTPUT"
  exit 1
fi

compose_env_file=".env"
if [[ ! -f ".env" && -f ".env.example" ]]; then
  compose_env_file=".env.example"
  warn_note ".env not found; using .env.example for compose config/ps validation"
fi

run_or_flag docker --version
run_or_flag docker compose version
run_or_flag_quiet docker compose --env-file "${compose_env_file}" config

if [[ "$MODE" == "verify" ]]; then
  run_or_flag docker compose --env-file "${compose_env_file}" ps --all
  echo "Report written to $OUTPUT"
  exit $overall_status
fi

if [[ $EUID -ne 0 ]]; then
  report ""
  report "[FAIL] full mode requires root"
  echo "Report written to $OUTPUT"
  exit 1
fi

if [[ $BRIDGE_TEST -eq 1 ]]; then
  if [[ -f ".env" ]]; then
    # shellcheck disable=SC1091
    source ".env"
  else
    warn_note "Bridge test requested but .env is missing; publish command may fail"
  fi
fi

run_or_flag ./install.sh --start --with-all
run_or_flag docker compose --profile zigbee --profile extras ps
run_or_flag ./update.sh --restart
run_or_flag docker compose --profile zigbee --profile extras ps

if [[ $BRIDGE_TEST -eq 1 ]]; then
  run_or_flag systemctl is-active ha-action-bridge
  run_or_flag mosquitto_pub -h 127.0.0.1 -u "${MQTT_USER}" -P "${MQTT_PASS}" -t ha/actions/tv_power -m "${BRIDGE_PAYLOAD}"
  run_or_flag journalctl -u ha-action-bridge -n 50 --no-pager
fi

if [[ "$UNINSTALL_MODE" == "purge" ]]; then
  run_or_flag ./uninstall.sh --yes --purge-data
else
  run_or_flag ./uninstall.sh --yes
fi

echo "Report written to $OUTPUT"
exit $overall_status
