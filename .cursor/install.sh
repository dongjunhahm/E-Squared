#!/usr/bin/env bash
# Idempotent repository bootstrap for the Earnings Diff → Analyst Packet app.
set -euo pipefail

cd "$(dirname "$0")/.."

# The default image ships Python 3.12 but not always the venv module. Install it
# only when missing so repeated runs stay fast and non-interactive.
if ! python3 -c "import ensurepip" >/dev/null 2>&1; then
  sudo apt-get update -qq
  sudo apt-get install -y -qq python3-venv
fi

python3 -m venv .venv
# shellcheck disable=SC1091
source .venv/bin/activate

pip install --upgrade pip -q
pip install -r requirements.txt

# Seed a local .env (mock provider, no key needed) when one is not present.
if [ ! -f .env ]; then
  cp .env.example .env
fi
