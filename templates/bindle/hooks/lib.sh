#!/usr/bin/env bash
# Shared by this bindle's hooks and the bindle CLI. Managed by bindle: `bindle doctor` flags a
# copy that differs from the base template. Expects CLAUDE_PLUGIN_ROOT (the bindle's folder).

root="${CLAUDE_PLUGIN_ROOT:?}"
memory="${root}/memory"
log="${BINDLE_SYNC_LOG:-${root}/.git/bindle-sync.log}"

# Never prompt for credentials or hang on a dead network inside a hook.
export GIT_TERMINAL_PROMPT=0
export GIT_SSH_COMMAND="${GIT_SSH_COMMAND:-ssh -o ConnectTimeout=5 -o BatchMode=yes}"

say() { printf '%s %s\n' "$(date '+%Y-%m-%d %H:%M:%S')" "$*" >> "$log" 2>/dev/null || true; }
g() { git -C "$root" "$@"; }

bindle_name() { sed -n 's/.*"name"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' "${root}/bindle.json" | head -1; }

sync_enabled() {
  [ -n "${BINDLE_SYNC_FORCE:-}" ] || grep -q '"sync"[[:space:]]*:[[:space:]]*true' "${root}/bindle.json"
}

# The folder a session was started from writes its memories here.
writable_here() {
  local settings="${CLAUDE_PROJECT_DIR:-$PWD}/.claude/settings.local.json"
  [ -f "$settings" ] && grep -q "\"autoMemoryDirectory\"[[:space:]]*:[[:space:]]*\"${memory}/\{0,1\}\"" "$settings"
}

has_remote() { [ -n "$(g remote 2>/dev/null)" ] && g rev-parse --abbrev-ref '@{upstream}' >/dev/null 2>&1; }

# Files under the given paths that look like they hold a credential. Prints paths only, never matches.
secret_hits() {
  grep -rlIE \
    -e '(api[_-]?key|secret|token|passw(or)?d)["'"'"']?[[:space:]]*[:=][[:space:]]*["'"'"']?[A-Za-z0-9_/+=.-]{16,}' \
    -e 'Bearer [A-Za-z0-9._-]{20,}' \
    -e 'AKIA[0-9A-Z]{16}' -e 'gh[pousr]_[A-Za-z0-9]{30,}' -e 'xox[abprs]-[A-Za-z0-9-]{10,}' \
    -e 'sk-[A-Za-z0-9_-]{20,}' -e '-----BEGIN [A-Z ]*PRIVATE KEY-----' \
    "$@" 2>/dev/null || true
}

# Pull the latest from the bindle's remote, and push commits an earlier session left behind.
sync_pull() {
  has_remote || { say "pull: no upstream, skipped"; return 0; }
  local ahead; ahead="$(g rev-list --count '@{upstream}..HEAD' 2>/dev/null || echo 0)"
  [ "$ahead" != 0 ] && { g push -q >>"$log" 2>&1 && say "pushed $ahead leftover commit(s)" || say "push of leftovers failed"; }
  g pull -q --ff-only >>"$log" 2>&1 && say "pulled" || say "pull failed or not fast-forward; left as is"
}

# Commit memory/ changes and push them. Refuses when a memory looks like it holds a secret:
# nothing is committed, so nothing can reach the remote, and `bindle doctor` reports it.
sync_push() {
  [ -n "$(g status --porcelain -- memory 2>/dev/null)" ] || { sync_push_leftovers; return 0; }
  local hits; hits="$(cd "$root" && secret_hits memory)"
  if [ -n "$hits" ]; then
    say "refused: possible secret in $(echo "$hits" | tr '\n' ' ')"
    echo "bindle: not syncing $(bindle_name) memories; possible secret in: $hits" >&2
    return 0
  fi
  g add -A -- memory && g commit -q -m "Memories from $(hostname -s) on $(date '+%Y-%m-%d')" -- memory >>"$log" 2>&1 \
    || { say "commit failed"; return 0; }
  say "committed memory changes"
  sync_push_leftovers
}

sync_push_leftovers() {
  has_remote || { say "push: no upstream, kept local"; return 0; }
  local ahead; ahead="$(g rev-list --count '@{upstream}..HEAD' 2>/dev/null || echo 0)"
  [ "$ahead" = 0 ] && return 0
  if ! g pull -q --rebase --autostash >>"$log" 2>&1; then
    g rebase --abort >/dev/null 2>&1 || true
    say "rebase conflict; commits kept local"
    return 0
  fi
  g push -q >>"$log" 2>&1 && say "pushed" || say "push failed; commits kept local"
}
