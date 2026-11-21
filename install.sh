#!/usr/bin/env bash
# Install (or update) REINS Edu on macOS or Linux and start it:
#
#   curl -fsSL https://raw.githubusercontent.com/Shpanier/reins-edu/main/install.sh | bash
#
# It puts REINS Edu in ~/REINS-Edu (set REINS_DIR for another folder). Run
# the same line again later to update: your settings (.env), your database
# (reins.db) and your exercises (data/) are kept.
set -euo pipefail
REPO="${REINS_REPO:-https://github.com/Shpanier/reins-edu}"
BRANCH="${REINS_BRANCH:-main}"
DIR="${REINS_DIR:-$HOME/REINS-Edu}"

if [ -d "$DIR/.git" ]; then
  echo "==> Updating REINS Edu in $DIR"
  git -C "$DIR" pull --ff-only
elif command -v git >/dev/null 2>&1 && [ ! -e "$DIR" ]; then
  echo "==> Downloading REINS Edu to $DIR"
  git clone --depth 1 --branch "$BRANCH" "$REPO" "$DIR"
else
  echo "==> Downloading REINS Edu to $DIR"
  mkdir -p "$DIR"
  # Only the files of the release are written: .env, reins.db and data/ stay.
  curl -fsSL "$REPO/archive/refs/heads/$BRANCH.tar.gz" | tar -xz -C "$DIR" --strip-components=1
fi
chmod +x "$DIR/start.sh" "$DIR/start.command" 2>/dev/null || true
echo "==> Starting. Next time: $DIR/start.sh  (on a Mac you can double-click start.command)"
exec "$DIR/start.sh" "$@"
