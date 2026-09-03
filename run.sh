#!/bin/bash
# Wrapper invoked by the launchd agent every day at 05:00.
# Runs the checker, then commits + pushes docs/ if anything changed.
set -euo pipefail

cd "$(dirname "$0")"

export PATH="/Users/uttam/.local/bin:/Users/uttam/.local/node/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME="/Users/uttam"

/usr/bin/python3 check.py

if ! git diff --quiet -- docs/ ; then
  git add docs/
  git -c user.name="connector-dashboard bot" \
      -c user.email="uttam408@users.noreply.github.com" \
      commit -q -m "status: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  git push -q origin main
  echo "pushed $(date -u +%FT%TZ)"
else
  echo "no change $(date -u +%FT%TZ)"
fi
