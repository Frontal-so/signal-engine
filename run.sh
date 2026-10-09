#!/usr/bin/env bash
# Daily job. Put it on launchd or cron at 07:00. Needs `claude` logged in (subscription) or ANTHROPIC_API_KEY + SIGNAL_ENGINE_BACKEND=api.
set -euo pipefail
cd "$(dirname "$0")"
exec .venv/bin/python run.py "${@:-daily}"
