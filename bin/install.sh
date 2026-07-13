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

# Farm src_dir into dst_dir as per-item symlinks, so an overlay install can add or override
# individual entries later. Skips dotfiles (e.g. .gitkeep) and empty dirs (glob no-match).
farm() {
  local src="$1" dst="$2" item
  [ -d "$src" ] || return 0
  mkdir -p "$dst"
  for item in "$src"/*; do
    [ -e "$item" ] || continue
    link "$item" "$dst/$(basename "$item")"
  done
}

echo "==> Linking global config into ${CLAUDE_DIR}"
link "$REPO_DIR/global/CLAUDE.md"      "$CLAUDE_DIR/CLAUDE.md"
link "$REPO_DIR/global/settings.json"  "$CLAUDE_DIR/settings.json"
farm "$REPO_DIR/global/commands"       "$CLAUDE_DIR/commands"
farm "$REPO_DIR/global/agents"         "$CLAUDE_DIR/agents"
farm "$REPO_DIR/global/skills"         "$CLAUDE_DIR/skills"

echo "==> Linking hooks"
link "$REPO_DIR/hooks/cost-tracker.sh" "$CLAUDE_DIR/hooks/cost-tracker.sh"
link "$REPO_DIR/hooks/lib"             "$CLAUDE_DIR/hooks/lib"
chmod +x "$REPO_DIR/hooks/cost-tracker.sh"

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
echo "  - python3 is required by the cost hook: $(command -v python3 >/dev/null && echo 'python3 OK' || echo 'python3 MISSING')"
echo "  - git is optional (used for ticket detection); without it the ticket column stays '-'"
echo "  - start a Claude Code session, then check for docs/claude-costs.md (or .claude-local/claude-costs.md) after your first turn"
echo "  - migrating an existing setup? Open Claude Code and say: 'Read MIGRATION.md in ~/bindle and migrate my setup.'"
