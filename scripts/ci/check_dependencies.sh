#!/usr/bin/env bash
set -euo pipefail

auditor=${PIP_AUDIT_BIN:-pip-audit}
exec "$auditor" \
  --strict --progress-spinner off \
  --requirement requirements.txt \
  --requirement requirements-bot.txt \
  --requirement requirements-jobs.txt \
  --requirement requirements-ci.txt
