"""bindle machine: which machine a session runs on, so Claude can judge whether a synced memory applies here.

The name is the one thing a person picks; it lives in ~/bindles/registry.json (per machine, never in a bindle,
which would sync it everywhere). Model, architecture and OS are detected. The line reaches every session and
subagent through bindle's block in the user CLAUDE.md (global_rules), which the session check keeps current.
"""
import platform
import re
import socket
import subprocess
from pathlib import Path

from .core import BindleError, read_json, registry_path, write_json

NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,39}")
PREFIX = "This machine: "
GUIDANCE = ("Memories sync to every machine: save what's true everywhere, and name the machine for a fact true "
            "on only one.")


def _run(*cmd):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=3)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (OSError, subprocess.SubprocessError):
        return ""


def _read(path):
    try:
        return Path(path).read_text(encoding="utf-8", errors="ignore").strip()
    except OSError:
        return ""


def detect():
    """[model, architecture, OS], leaving out what can't be read."""
    system, arch = platform.system(), platform.machine()
    if system == "Darwin":
        model = _run("sysctl", "-n", "hw.model")
        if _run("sysctl", "-n", "hw.optional.arm64") == "1":
            arch = "arm64"  # an x86 Python under Rosetta reports x86_64 on Apple silicon
        os_name = "macOS " + platform.mac_ver()[0]
    elif system == "Windows":
        model = ""
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"HARDWARE\DESCRIPTION\System\BIOS") as k:
                model = str(winreg.QueryValueEx(k, "SystemProductName")[0]).strip()
        except OSError:
            pass
        build = platform.version().split(".")[-1]
        # Python before 3.12 reports Windows 11 as release "10"; build 22000 is where 11 starts.
        os_name = "Windows " + ("11" if build.isdigit() and int(build) >= 22000 else platform.release())
    else:
        model = _read("/sys/devices/virtual/dmi/id/product_name")
        pretty = re.search(r'^PRETTY_NAME="?([^"\n]*)"?', _read("/etc/os-release"), re.M)
        os_name = pretty.group(1) if pretty else f"{system} {platform.release()}"
    return [p for p in (model, arch, os_name.strip()) if p]


def suggest_name():
    """A short default from the hostname ("Alexs-MacBook-Pro.local" -> "macbook-pro"); the person picks the real one."""
    host = socket.gethostname().split(".")[0].lower()
    slug = re.sub(r"[^a-z0-9]+", "-", host).strip("-")
    slug = re.sub(r"^[a-z]+s-(?=.)", "", slug)  # "alexs-macbook-pro": drop the owner's name
    return slug[:40] or "this-machine"


def _data():
    data = read_json(registry_path()).get("machine", {})
    return data if isinstance(data, dict) else {}


def _save(**fields):
    data = read_json(registry_path())
    machine = data.get("machine") if isinstance(data.get("machine"), dict) else {}
    machine.update(fields)
    data["machine"] = machine
    write_json(registry_path(), data)


def name():
    value = _data().get("name")
    return value if isinstance(value, str) and NAME.fullmatch(value) else None


def line():
    """The block's machine line, or None until the machine is named."""
    n = name()
    return f"{PREFIX}{n} ({', '.join(detect())}). {GUIDANCE}" if n else None


def ask_once():
    """The session check's one-time ask when no name is set; afterwards it stays quiet (the command still works)."""
    if name() or _data().get("asked"):
        return None
    _save(asked=True)
    return (f"bindle: this machine has no name yet. A name tells Claude which machine it's on, so it can tell whether "
            f"a synced memory applies here. Ask the person for a short one, suggesting `{suggest_name()}`, then set it "
            f"with the bindle `machine` tool (or `bindle machine <name>`). This is asked only once.")


def cmd_machine(args):
    from . import global_rules
    if not args.name:
        n = name()
        print(f"This machine: {n}" if n else f"This machine has no name yet; suggested: bindle machine {suggest_name()}")
        print(f"  detected: {', '.join(detect()) or 'nothing'}")
        return 0
    if not NAME.fullmatch(args.name):
        raise BindleError("A machine name is 1-40 letters, digits, dots, hyphens or underscores, starting with a "
                          "letter or digit (work-mac, personal-mac-2015).")
    _save(name=args.name, asked=True)
    path = global_rules.refresh_machine_line()
    print(f"This machine is {args.name}. {path} now says so in bindle's block, so every session and subagent knows "
          f"which machine it's on, from the next session.")
    return 0
