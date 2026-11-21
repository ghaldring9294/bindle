"""bindle: carry a Claude Code setup between machines, one git repo per domain. See README.md."""
from .cli import build_parser, main
from .core import BASE, LAYOUT, MANAGED, RULES_LIMIT, TEMPLATE, VERSION, git
