#!/bin/bash
# Wrapper invoked by the launchd agent daily at 05:00.
# Runs the checker, commits docs/ if it changed, then pushes whatever is
# ahead of origin -- retrying, because the Mac is often still bringing its
# network up at 05:00 and the first push can time out on DNS.
set -uo pipefail

cd "$(dirname "$0")"

export PATH="/Users/uttam/.local/bin:/Users/uttam/.local/node/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME="/Users/uttam"

/usr/bin/python3 check.py || { echo "check.py failed $(date -u +%FT%TZ)"; exit 1; }

if ! git diff --quiet -- docs/ ; then
  git add docs/
  git -c user.name="connector-dashboard bot" \
      -c user.email="uttam408@users.noreply.github.com" \
      commit -q -m "status: $(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi

# push if we're ahead of origin -- covers today's commit plus any commit
# stranded by a previous failed push. Wait for the network first (the Mac is
# often still associating Wi-Fi at 05:00); a bare git call would otherwise
# block ~7 min on DNS.
for attempt in 1 2 3 4 5 6; do
  if nc -z -G 5 -w 5 github.com 443 2>/dev/null; then break; fi
  echo "no network (attempt $attempt), waiting…"
  sleep 60
done

git fetch -q origin main 2>/dev/null || true
if [ -z "$(git rev-list origin/main..HEAD 2>/dev/null)" ]; then
  echo "nothing to push $(date -u +%FT%TZ)"
  exit 0
fi

for attempt in 1 2 3 4 5; do
  if git push -q origin main 2>/dev/null; then
    echo "pushed (attempt $attempt) $(date -u +%FT%TZ)"
    exit 0
  fi
  echo "push attempt $attempt failed, waiting…"
  sleep 60
done

echo "push still failing after 5 attempts $(date -u +%FT%TZ) — will retry next run"
exit 1
