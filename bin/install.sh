#!/usr/bin/env bash
# Symlink this repo's config into ~/.claude and set up global git excludes.
# Idempotent: safe to re-run. Existing non-symlink files are backed up, not deleted.
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CLAUDE_DIR="${HOME}/.claude"
BACKUP_DIR="${CLAUDE_DIR}/backup-$(date +%Y%m%d-%H%M%S)"

link() {
  local src="$1" dst="$2"
  mkdir -p "$(dirname "$dst")"
  if [ -e "$dst" ] && [ ! -L "$dst" ]; then
    mkdir -p "$BACKUP_DIR"
    echo "  backing up existing $(basename "$dst") -> $BACKUP_DIR/"
    mv "$dst" "$BACKUP_DIR/"
  fi
  ln -sfn "$src" "$dst"
  echo "  linked $dst -> $src"
}

# Base ships no craft (commands/agents/skills) — those are personal/domain and are farmed
# by the overlay's own installer. Base install only links its conventions + settings.
echo "==> Linking global config into ${CLAUDE_DIR}"
link "$REPO_DIR/global/CLAUDE.md"      "$CLAUDE_DIR/CLAUDE.md"
link "$REPO_DIR/global/settings.json"  "$CLAUDE_DIR/settings.json"

echo "==> Machine-local settings"
if [ ! -f "$CLAUDE_DIR/settings.local.json" ]; then
  echo '{}' > "$CLAUDE_DIR/settings.local.json"
  echo "  created empty settings.local.json (machine-specific overrides go here; never commit it)"
else
  echo "  settings.local.json already exists, leaving it alone"
fi

echo "==> Global git excludes (.claude-local/ ignored in every repo, no team .gitignore edits)"
EXCLUDES_FILE="$(git config --global core.excludesFile || true)"
if [ -z "$EXCLUDES_FILE" ]; then
  EXCLUDES_FILE="${HOME}/.gitignore_global"
  git config --global core.excludesFile "$EXCLUDES_FILE"
  echo "  set core.excludesFile -> $EXCLUDES_FILE"
fi
EXCLUDES_FILE="${EXCLUDES_FILE/#\~/$HOME}"
touch "$EXCLUDES_FILE"
for pattern in ".claude-local" "settings.local.json"; do
  grep -qxF "$pattern" "$EXCLUDES_FILE" || { echo "$pattern" >> "$EXCLUDES_FILE"; echo "  added '$pattern'"; }
done

echo ""
echo "Done. Sanity checks:"
echo "  - CLAUDE.md + settings.json linked into ~/.claude (craft comes from the personal/domain overlay installers)"
echo "  - migrating an existing setup? Open Claude Code and say: 'Read MIGRATION.md in ~/bindle and migrate my setup.'"
