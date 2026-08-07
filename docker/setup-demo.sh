#!/usr/bin/env bash
# Fetches third-party custom integrations needed by the demo/E2E HA instance
# that we deliberately do NOT vendor into this repo (separate license,
# separate upstream lifecycle). Safe to re-run; wipes and re-clones.
#
# Usage: bash docker/setup-demo.sh
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

DEST="ha_config/custom_components/virtual"
mkdir -p ha_config/custom_components

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

git clone --depth 1 https://github.com/twrecked/hass-virtual.git "$TMP"
rm -rf "$DEST"
cp -r "$TMP/custom_components/virtual" "$DEST"

echo "hass-virtual installed into $DEST"
echo "Next: docker compose -f docker-compose.demo.yml up -d"
