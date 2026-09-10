#!/bin/bash
# Wrapper invoked by the launchd agent daily at 05:00.
# Runs check.py (which writes this Mac's status fragments to docs/status.d/),
# commits any that changed, and pushes -- rebasing in the retry loop because
# other agents push their own fragments concurrently, and because the Mac is
# often still bringing its network up at 05:00 (a bare git call blocks ~7 min
# on DNS).
set -uo pipefail

cd "$(dirname "$0")"

export PATH="/Users/uttam/.local/bin:/Users/uttam/.local/node/bin:/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin"
export HOME="/Users/uttam"

# wait for the network first (the Mac is often still associating Wi-Fi at
# 05:00); a bare git call would otherwise block ~7 min on DNS.
for attempt in 1 2 3 4 5 6; do
  if nc -z -G 5 -w 5 github.com 443 2>/dev/null; then break; fi
  echo "no network (attempt $attempt), waiting…"
  sleep 60
done

# pick up other agents' fragment pushes before regenerating ours
git fetch -q origin main 2>/dev/null || true
git merge --ff-only -q origin/main 2>/dev/null || echo "merge skipped — local ahead"

/usr/bin/python3 check.py || { echo "check.py failed $(date -u +%FT%TZ)"; exit 1; }

if ! git diff --quiet -- docs/ ; then
  git add docs/
  git -c user.name="connector-dashboard bot" \
      -c user.email="uttam408@users.noreply.github.com" \
      commit -q -m "status: mac fragments $(date -u +%Y-%m-%dT%H:%M:%SZ)"
fi

if [ -z "$(git rev-list origin/main..HEAD 2>/dev/null)" ]; then
  echo "nothing to push $(date -u +%FT%TZ)"
  exit 0
fi

for attempt in 1 2 3 4 5; do
  git fetch -q origin main 2>/dev/null || true
  git rebase -q origin/main 2>/dev/null || { git rebase --abort 2>/dev/null; true; }
  if git push -q origin HEAD:main 2>/dev/null; then
    echo "pushed (attempt $attempt) $(date -u +%FT%TZ)"
    exit 0
  fi
  echo "push attempt $attempt failed, waiting…"
  sleep 60
done

echo "push still failing after 5 attempts $(date -u +%FT%TZ) — will retry next run"
exit 1
