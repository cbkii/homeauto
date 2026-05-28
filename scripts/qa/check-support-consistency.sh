#!/usr/bin/env bash
set -euo pipefail

README_FILE="README.md"
SUPPORT_FILE="docs/SUPPORT_BOUNDARIES.md"
CHECKLIST_FILE="FINALIZATION_CHECKLIST.md"

if [[ ! -f "$README_FILE" || ! -f "$SUPPORT_FILE" || ! -f "$CHECKLIST_FILE" ]]; then
  echo "Required files missing for support consistency check"
  exit 1
fi

readme_mentions_trixie=0
support_mentions_trixie=0
checklist_has_s37=0

if grep -E -qi 'trixie|debian 13' "$README_FILE"; then
  readme_mentions_trixie=1
fi

if grep -E -qi 'trixie|debian 13' "$SUPPORT_FILE"; then
  support_mentions_trixie=1
fi

if grep -E -q '^\| S37 \|' "$CHECKLIST_FILE"; then
  checklist_has_s37=1
fi

if [[ $support_mentions_trixie -ne $readme_mentions_trixie ]]; then
  echo "Support statement drift: README and SUPPORT_BOUNDARIES disagree on Trixie/Debian 13 mention"
  exit 1
fi

if [[ $support_mentions_trixie -eq 1 && $checklist_has_s37 -ne 1 ]]; then
  echo "Trixie support is mentioned, but FINALIZATION_CHECKLIST.md is missing S37 tracking item"
  exit 1
fi

echo "Support consistency checks passed"
