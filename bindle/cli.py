"""The bindle command line."""
import argparse
import sys

from .commands import cmd_attach, cmd_detach, cmd_doctor, cmd_install, cmd_list, cmd_new, cmd_session_check, cmd_sync
from .core import VERSION, BindleError
from .global_rules import cmd_global
from .promote import KINDS, cmd_collect, cmd_outbox_add, cmd_outbox_clean, cmd_outbox_list, cmd_outbox_remove, cmd_promote, cmd_terms
from .upgrade import cmd_update, cmd_upgrade

FOLDER_HELP = "the folder you launch Claude from (default: here)"


def build_parser():
    p = argparse.ArgumentParser(prog="bindle", description="Create bindles and turn them on for folders.")
    p.add_argument("--version", action="version", version=f"bindle {VERSION}")
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("install", help="put bindle on PATH (optional when installed as a plugin)")
    s.add_argument("--session-check", action=argparse.BooleanOptionalAction, default=None,
                   help="(legacy) add or remove the user-level session-check hook; the plugin provides this now")
    s.add_argument("--cleanup", action="store_true",
                   help="remove old-style command/skill links and user-level hook left by an earlier install")
    s.set_defaults(fn=cmd_install)

    s = sub.add_parser("session-check", help="what the session check would say for a folder")
    s.add_argument("folder", nargs="?", help=FOLDER_HELP)
    s.add_argument("--hook", action="store_true", help="run as the hook: read the folder from Claude Code, answer in hook JSON")
    s.set_defaults(fn=cmd_session_check)

    s = sub.add_parser("new", help="create a bindle repo")
    s.add_argument("name")
    s.add_argument("--at", help="where to create it (default: ./.bindle)")
    s.add_argument("--sync", action="store_true", help="sync memories with the bindle's remote at session start and end")
    s.add_argument("--audience", choices=["private", "shared", "public"], default="private", help="who can see it (default: private)")
    s.add_argument("--writes", choices=["implicit", "explicit"], default="implicit",
                   help="implicit: can be a folder's writable bindle; explicit: only `bindle collect` adds to it")
    s.set_defaults(fn=cmd_new)

    s = sub.add_parser("attach", help="turn a bindle on for the folder you launch Claude from",
                       description="Turn a bindle on for a folder: sessions started from that folder load the bindle. "
                                   "Writes the folder's .claude/settings.local.json; nothing is copied or linked.")
    s.add_argument("bindle", help="path to the bindle repo, or the name of one in $BINDLE_HOME (default ~/bindles)")
    s.add_argument("folder", nargs="?", help=FOLDER_HELP)
    s.add_argument("--writable", action="store_true", help="new memories in this folder go to this bindle")
    s.add_argument("--repos", action="store_true", help="also each git repo directly inside the folder (sessions started in a repo read only its own settings)")
    s.set_defaults(fn=cmd_attach)

    s = sub.add_parser("detach", help="turn a bindle off for a folder")
    s.add_argument("bindle", help="the bindle's name or path")
    s.add_argument("folder", nargs="?", help=FOLDER_HELP)
    s.add_argument("--repos", action="store_true", help="also each git repo directly inside the folder (sessions started in a repo read only its own settings)")
    s.set_defaults(fn=cmd_detach)

    s = sub.add_parser("global", help="load a bindle's rules.md in every session and subagent, in every folder",
                       description="Load a bindle's rules.md everywhere: writes an import of it in a marked block in "
                                   "your user CLAUDE.md (~/.claude/CLAUDE.md, or in $CLAUDE_CONFIG_DIR), leaving the "
                                   "rest of that file as it is. Takes effect in the next session.")
    s.add_argument("bindle", help="the bindle's name or path (with --off, also the path doctor shows for one that moved)")
    s.add_argument("--off", action="store_true", help="stop loading it everywhere (remove its import)")
    s.set_defaults(fn=cmd_global)

    s = sub.add_parser("list", help="list your bindles: those in $BINDLE_HOME (default ~/bindles) and those on in a folder")
    s.add_argument("folder", nargs="?", help=FOLDER_HELP)
    s.set_defaults(fn=cmd_list)

    s = sub.add_parser("doctor", help="show what's on in a folder and any problems")
    s.add_argument("folder", nargs="?", help=FOLDER_HELP)
    s.set_defaults(fn=cmd_doctor)

    s = sub.add_parser("sync", help="pull the bindles that are on, and commit and push the writable one's memories")
    s.add_argument("folder", nargs="?", help=FOLDER_HELP)
    s.add_argument("--all", action="store_true", help="every bindle `bindle list` finds: pull each, and commit and push memories in those that can be writable")
    s.set_defaults(fn=cmd_sync)

    s = sub.add_parser("update", help="update bindle itself (git pull), refresh its install, and upgrade every bindle")
    s.add_argument("--push", action="store_true", help="also push each bindle the upgrade committed to, if it has a remote")
    s.add_argument("--after-pull", action="store_true", help=argparse.SUPPRESS)
    s.set_defaults(fn=cmd_update)

    s = sub.add_parser("upgrade", help="bring a bindle's managed files and layout up to this bindle version")
    s.add_argument("bindle", nargs="?", help="the bindle's name or path (default: every bindle attached to this folder)")
    s.add_argument("--all", action="store_true", help="every bindle `bindle list` finds (in ~/bindles and its registry)")
    s.add_argument("--dry-run", action="store_true", help="show what would change")
    s.set_defaults(fn=cmd_upgrade)

    s = sub.add_parser("promote", help="copy an approved, general draft from one bindle into another (checked for domain names and secrets)")
    s.add_argument("source", help="the bindle the draft comes from, by name or path (its private terms are checked)")
    s.add_argument("path", help="the draft: a memory or command .md file, or a skill folder")
    s.add_argument("--into", required=True, help="the target bindle: a path or a name; it must be on this machine")
    s.add_argument("--kind", choices=list(KINDS), default="memory")
    s.add_argument("--name", required=True, help="the item's slug, e.g. small-prs")
    s.add_argument("--description", default="", help="one line for the target's memory index")
    s.add_argument("--allow", action="append", default=[], metavar="TERM", help="a private term you've decided is fine to share in this promotion (repeatable); possible secrets can't be allowed")
    s.add_argument("--replace", action="store_true", help="update what's already in the target (git history keeps the old version)")
    s.add_argument("--dry-run", action="store_true", help="show what would change in the target, as a diff when replacing")
    s.set_defaults(fn=cmd_promote)

    s = sub.add_parser("outbox", help="a bindle's outbox: reviewed, general items waiting to be promoted")
    osub = s.add_subparsers(dest="outbox_cmd", required=True)
    o = osub.add_parser("add", help="add an approved draft (after a leak check and secret check)")
    o.add_argument("bindle", help="the source bindle")
    o.add_argument("path", help="the draft: a memory or command .md file, or a skill folder")
    o.add_argument("--kind", choices=list(KINDS), default="memory")
    o.add_argument("--name", required=True, help="the item's slug, e.g. small-prs")
    o.add_argument("--description", default="", help="one line for the target's index")
    o.add_argument("--allow", action="append", default=[], metavar="TERM", help="a private term you've decided is fine to share (repeatable); pass it to collect again")
    o.set_defaults(fn=cmd_outbox_add)
    o = osub.add_parser("list", help="show a bindle's outbox, or every outbox with --all")
    o.add_argument("bindle", nargs="?")
    o.add_argument("--all", action="store_true", help="every bindle `bindle list` finds")
    o.set_defaults(fn=cmd_outbox_list)
    o = osub.add_parser("clean", help="remove items already collected (they're in the target and in git history)")
    o.add_argument("bindle")
    o.add_argument("--items", help="comma-separated item names (default: every collected item)")
    o.add_argument("--dry-run", action="store_true", help="show what would be removed")
    o.set_defaults(fn=cmd_outbox_clean)
    o = osub.add_parser("remove", help="drop named items, collected or not (e.g. an approval you changed your mind about)")
    o.add_argument("bindle")
    o.add_argument("--items", required=True, help="comma-separated item names")
    o.add_argument("--dry-run", action="store_true", help="show what would be removed")
    o.set_defaults(fn=cmd_outbox_remove)

    s = sub.add_parser("terms", help="suggest private terms for a bindle from the repos in its domain folder")
    s.add_argument("bindle", help="the bindle's name or path")
    s.add_argument("folder", nargs="?", help="the domain folder to look in (default: the folder a .bindle sits in, else here)")
    s.set_defaults(fn=cmd_terms)

    s = sub.add_parser("collect", help="move approved outbox items into another bindle")
    s.add_argument("source", help="the bindle whose outbox to collect from, by name or path")
    s.add_argument("--into", required=True, help="the target bindle")
    s.add_argument("--items", help="comma-separated item names")
    s.add_argument("--all", action="store_true", help="every item not yet in the target")
    s.add_argument("--allow", action="append", default=[], metavar="TERM",
                   help="a private term you've decided is fine to share (repeatable); an item's own record of allowed terms isn't trusted")
    s.add_argument("--dry-run", action="store_true", help="show each item's content and move nothing")
    s.set_defaults(fn=cmd_collect)
    return p


def main(argv=None):
    parser = build_parser()
    if not (sys.argv[1:] if argv is None else argv):
        parser.print_help()  # bare `bindle` shows every command rather than an error
        return 0
    args = parser.parse_args(argv)
    try:
        return args.fn(args) or 0
    except BindleError as e:
        print(f"bindle: {e}", file=sys.stderr)
        return 1
