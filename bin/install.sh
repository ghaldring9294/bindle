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

# Base ships no USER craft — commands/agents/skills live in the layers, farmed by each layer's
# own installer. Base links its conventions, settings, and its own /bindle orchestrator command.
echo "==> Linking global config into ${CLAUDE_DIR}"
link "$REPO_DIR/global/CLAUDE.md"          "$CLAUDE_DIR/CLAUDE.md"
link "$REPO_DIR/global/settings.json"      "$CLAUDE_DIR/settings.json"
link "$REPO_DIR/global/commands/bindle.md" "$CLAUDE_DIR/commands/bindle.md"

echo "==> Installing the 'bindle' command on PATH"
BINDIR="$HOME/.local/bin"
mkdir -p "$BINDIR"
chmod +x "$REPO_DIR/bin/bindle"
ln -sfn "$REPO_DIR/bin/bindle" "$BINDIR/bindle"
echo "  linked $BINDIR/bindle -> $REPO_DIR/bin/bindle"
case ":${PATH}:" in
  *":$BINDIR:"*) : ;;
  *) echo "  NOTE: $BINDIR is not on PATH — add:  export PATH=\"\$HOME/.local/bin:\$PATH\"" ;;
esac

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
echo "  - CLAUDE.md + settings.json linked; craft comes from the personal/professional layer installers"
echo "  - run 'bindle help' for commands (create a layer, link a project), or /bindle inside Claude Code"
echo "  - migrating an existing setup? Open Claude Code and say: 'Read MIGRATION.md in ~/bindle and migrate my setup.'"
