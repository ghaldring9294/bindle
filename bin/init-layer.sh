#!/usr/bin/env bash
# bindle init-layer — scaffold a new LAYER repo (personal or professional).
#
# Bindle is the orchestrator: layers are SEPARATE private git repos it creates but
# never stores. A layer is one trust scope's craft + memory:
#   personal      — your cross-domain craft; loads on every machine (always-on).
#   professional  — a secure employer/client domain; loads only inside that domain's
#                   projects (scoped). Multiple allowed; each is its own boundary and
#                   must never overlap personal or another professional layer.
#
# Usage:
#   init-layer.sh <name> --scope personal|professional [--label employer|client]
#                 [--dir <parent-dir>] [--from <existing-memory-dir>]
#
#   <name>        repo name, e.g. "personal" or "acme"  -> dir "bindle-<name>"
#   --scope       personal (always-on) | professional (scoped, secure)   [required]
#   --label       optional freeform tag for a professional layer (employer|client|…)
#   --dir         where to create it (default: alongside this repo's parent)
#   --from        an existing memory dir to migrate in (e.g. a live
#                 ~/.claude/projects/<slug>/memory) — copied, then sort by hand
set -euo pipefail

NAME="${1:?usage: init-layer.sh <name> --scope personal|professional [--label X] [--dir D] [--from M]}"
shift
SCOPE="" LABEL="" DIR="" FROM="" ASSUME_YES=""
while [ $# -gt 0 ]; do
  case "$1" in
    --scope) SCOPE="${2:?}"; shift 2 ;;
    --label) LABEL="${2:?}"; shift 2 ;;
    --dir)   DIR="${2:?}";   shift 2 ;;
    --from)  FROM="${2:?}";  shift 2 ;;
    --yes)   ASSUME_YES=1;   shift ;;   # skip the migration confirm prompt (caller already consented)
    *) echo "unknown arg: $1" >&2; exit 1 ;;
  esac
done
case "$SCOPE" in
  personal|professional) ;;
  *) echo "--scope must be 'personal' or 'professional'" >&2; exit 1 ;;
esac

DIR="${DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
REPO="$DIR/bindle-$NAME"
[ -e "$REPO" ] && { echo "already exists: $REPO" >&2; exit 1; }

echo "==> Scaffolding $SCOPE layer at $REPO"
mkdir -p "$REPO"/{agents,commands,skills,memory/{reference,feedback,project,user,skill}}
touch "$REPO"/agents/.gitkeep "$REPO"/commands/.gitkeep "$REPO"/skills/.gitkeep
for t in reference feedback project user skill; do touch "$REPO/memory/$t/.gitkeep"; done
[ "$SCOPE" = professional ] && { mkdir -p "$REPO/projects"; touch "$REPO/projects/.gitkeep"; }

# The always-on rules file. personal -> CLAUDE.personal.md (base @imports it);
# professional -> CLAUDE.<name>.md (loaded scoped via a project's .claude-local chain).
CLAUDE_FILE="CLAUDE.$([ "$SCOPE" = personal ] && echo personal || echo "$NAME").md"
cat > "$REPO/$CLAUDE_FILE" <<EOF
# ${NAME} layer — ${SCOPE}$( [ -n "$LABEL" ] && echo " (${LABEL})" )

$( [ "$SCOPE" = personal ] \
   && echo "Cross-domain personal craft, loaded on every machine via the base CLAUDE.md @import." \
   || echo "Secure ${LABEL:-professional} domain. Loads ONLY inside this domain's projects (via .claude-local). Never overlaps personal or another professional layer." )
EOF

cat > "$REPO/memory/MEMORY.md" <<'EOF'
<!-- Tier-0 index. Organize by type (bindle memory taxonomy): reference / feedback /
project / user / skill. Mark in-flight state [volatile]. See bindle templates/memory-taxonomy.md. -->

## reference — what is
## feedback — how I should work
## project — ongoing work
## user — who I am
## skill — skill addenda
EOF

printf '.DS_Store\n__pycache__/\nsecrets.env\n' > "$REPO/.gitignore"

cat > "$REPO/README.md" <<EOF
# bindle-$NAME

A **$SCOPE** bindle layer$( [ -n "$LABEL" ] && echo " (\`$LABEL\`)" ) — a private repo of craft + memory,
orchestrated by bindle but stored separately (locally or on $( [ "$SCOPE" = personal ] && echo "your personal" || echo "the company's" ) git).

- \`$CLAUDE_FILE\` — this layer's rules ($( [ "$SCOPE" = personal ] && echo "always-on via base @import" || echo "scoped: loads inside this domain's projects only" )).
- \`agents/ commands/ skills/\` — craft, farmed into \`~/.claude\` by this layer's installer.
- \`memory/\` — versioned memory in the type-folder taxonomy (source of truth; copied into the loadable slot on install).
$( [ "$SCOPE" = professional ] && echo "- \`projects/<name>/\` — per-project context (docs/tickets/memory), linked into a repo via bindle init-project." )

Loading model: **$( [ "$SCOPE" = personal ] && echo "always-on" || echo "scoped-secure" )**. Memory transports by copy into
\`~/.claude/projects/<slug>/memory/\` (symlinking the slot out breaks headless detail reads).
EOF

# Optional migration: copy an existing memory dir in for hand-sorting.
# Migration touches trust boundaries, so WARN + require confirmation before copying anything.
if [ -n "$FROM" ]; then
  [ -d "$FROM" ] || { echo "--from path not found: $FROM" >&2; exit 1; }
  echo ""
  echo "  !! MIGRATION — read before confirming"
  echo "  About to copy EVERYTHING from:  $FROM"
  echo "  into the '$NAME' ($SCOPE) layer."
  if [ "$SCOPE" = personal ]; then
    echo "  A PERSONAL layer loads on EVERY machine (and may be shared or made public). Migrating here"
    echo "  is exactly right for portable personal CRAFT — carrying it between your own machines, or"
    echo "  onto a work box. Just confirm the source is personal craft only: any employer/client-"
    echo "  specific content that lands here is a cross-domain leak. If the source is work or mixed,"
    echo "  create the professional (secure) layer first and promote only cross-domain craft into personal."
  else
    echo "  This is a PROFESSIONAL (secure) layer: confirm this is the right domain, and keep it"
    echo "  isolated — its content must never reach personal or another domain's layer."
  fi
  if [ -n "$ASSUME_YES" ]; then
    echo "  (--yes given — proceeding)"
  elif [ -t 0 ]; then
    printf "  Type 'yes' to migrate (anything else skips it): "
    read -r ans
    [ "$ans" = yes ] || { echo "  Skipped migration — layer created empty."; FROM=""; }
  else
    echo "  Non-interactive and no --yes — skipping migration; layer created empty."
    FROM=""
  fi
fi
if [ -n "$FROM" ]; then
  echo "==> Migrating memory from $FROM -> memory/_incoming/ (for sorting)"
  mkdir -p "$REPO/memory/_incoming"
  cp -R "$FROM/." "$REPO/memory/_incoming/"
  echo "  copied — sort _incoming/* into reference|feedback|project|user|skill, then rm _incoming"
fi

echo "==> git init + first commit"
git -C "$REPO" init -q
git -C "$REPO" add -A
git -C "$REPO" -c user.name="bindle" -c user.email="bindle@localhost" commit -q -m "Scaffold $SCOPE layer bindle-$NAME"
echo "Done. $REPO ($SCOPE$( [ -n "$LABEL" ] && echo "/$LABEL" ))"
