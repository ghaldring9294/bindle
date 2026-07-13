#!/usr/bin/env bash
# Drop the tiered-context doc structure into a project.
# Usage:
#   init-project.sh /path/to/repo                      # team-visible docs/ scaffold
#   init-project.sh /path/to/repo --local <name>       # personal .claude-local linked
#                                                      # to ~/bindle-memories/projects/<name>
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TEMPLATES="$REPO_DIR/templates"
MEMORIES_DIR="${BINDLE_MEMORIES_DIR:-$HOME/bindle-memories}"

TARGET="${1:?usage: init-project.sh /path/to/repo [--local <project-name>]}"
TARGET="$(cd "$TARGET" && pwd)"
shift

LOCAL_NAME=""
if [ "${1:-}" = "--local" ]; then
  LOCAL_NAME="${2:?--local requires a project name}"
fi

copy_if_absent() {
  local src="$1" dst="$2"
  if [ -e "$dst" ]; then
    echo "  exists, skipping: $dst"
  else
    mkdir -p "$(dirname "$dst")"
    cp "$src" "$dst"
    echo "  created: $dst"
  fi
}

if [ -n "$LOCAL_NAME" ]; then
  echo "==> Personal context: .claude-local -> $MEMORIES_DIR/projects/$LOCAL_NAME"
  MEM="$MEMORIES_DIR/projects/$LOCAL_NAME"
  mkdir -p "$MEM/docs"
  copy_if_absent "$TEMPLATES/docs-index.md"   "$MEM/index.md"
  copy_if_absent "$TEMPLATES/architecture.md" "$MEM/docs/architecture.md"
  ln -sfn "$MEM" "$TARGET/.claude-local"
  echo "  linked $TARGET/.claude-local"
  echo "  (ignored everywhere via global git excludes — team repo stays pristine)"
else
  echo "==> Team-visible docs scaffold in $TARGET/docs"
  copy_if_absent "$TEMPLATES/docs-index.md"   "$TARGET/docs/index.md"
  copy_if_absent "$TEMPLATES/architecture.md" "$TARGET/docs/architecture.md"
fi

echo ""
echo "Next: fill in architecture.md (data model mermaid first — highest value),"
echo "then keep index.md current. Claude reads index.md before anything else."
