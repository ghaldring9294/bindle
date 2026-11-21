"""Tests for bin/bindle. Run: python3 -m unittest discover -s tests

`claude` is replaced by tests/fake_claude, so nothing here touches the machine's real plugin state.
tests/e2e.sh runs the same flow against the real CLI."""
import contextlib
import io
import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

import sys

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
import bindle  # noqa: E402


def rmtree(path):
    """Deletes a folder; git marks object files read-only, which Windows refuses to delete without a chmod."""
    import stat
    def onerror(func, p, _):
        os.chmod(p, stat.S_IWRITE)
        func(p)
    shutil.rmtree(path, onerror=onerror)


class BindleTest(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(os.path.realpath(tempfile.mkdtemp()))
        self.log = self.tmp / "claude.log"
        self.env = {
            "BINDLE_CLAUDE": str(HERE / "fake_claude"),
            "FAKE_CLAUDE_LOG": str(self.log),
            "GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@example.com",
            "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@example.com",
        }
        self.saved = {k: os.environ.get(k) for k in self.env}
        os.environ.update(self.env)

    def tearDown(self):
        for k, v in self.saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = bindle.main([str(a) for a in args])
        return code, out.getvalue() + err.getvalue()

    def make_bindle(self, name):
        code, out = self.run_cli("new", name, "--at", self.tmp / f"bindle-{name}")
        self.assertEqual(code, 0, out)
        return self.tmp / f"bindle-{name}"

    def folder(self, name="root"):
        f = self.tmp / name
        f.mkdir(exist_ok=True)
        return f

    def settings(self, folder):
        return json.loads((folder / ".claude" / "settings.local.json").read_text())

    def claude_calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []


class NewTest(BindleTest):
    def test_scaffolds_a_plugin_shaped_bindle_named_throughout(self):
        b = self.make_bindle("acme")
        self.assertEqual(json.loads((b / "bindle.json").read_text()), {"name": "acme", "layout": 1, "sync": False, "audience": "private", "writes": "implicit"})
        self.assertEqual(json.loads((b / ".claude-plugin/plugin.json").read_text())["name"], "acme")
        self.assertEqual(json.loads((b / ".claude-plugin/marketplace.json").read_text())["name"], "bindle-acme")
        for d in ["memory", "notes", "projects", "skills", "commands", "agents"]:
            self.assertTrue((b / d).is_dir(), d)
        self.assertNotIn("{{name}}", "".join(p.read_text() for p in b.rglob("*") if p.is_file() and ".git/" not in str(p)))

    # Doctor detects drift by comparing managed files to the template byte for byte; any
    # substitution in them would make every bindle look drifted.
    def test_managed_files_are_byte_identical_to_the_template(self):
        b = self.make_bindle("acme")
        for rel in bindle.MANAGED:
            self.assertEqual((b / rel).read_bytes(), (bindle.TEMPLATE / rel).read_bytes(), rel)
        self.assertTrue(os.access(b / "hooks/bindle_hook.py", os.X_OK))

    def test_commits_but_never_sets_a_remote(self):
        b = self.make_bindle("acme")
        self.assertIsNotNone(bindle.git(b, "rev-parse", "HEAD"))
        self.assertEqual(bindle.git(b, "remote"), "")

    def test_refuses_a_bad_name_or_a_non_empty_folder(self):
        self.assertEqual(self.run_cli("new", "Acme Corp", "--at", self.tmp / "x")[0], 1)
        self.make_bindle("acme")
        self.assertEqual(self.run_cli("new", "acme", "--at", self.tmp / "bindle-acme")[0], 1)


class EnclosingRepoTest(BindleTest):
    """A bindle inside a project repo must never be committable into that repo."""

    def project_repo(self):
        repo = self.folder("project")
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        return repo

    def test_new_inside_a_repo_excludes_the_bindle_locally(self):
        repo = self.project_repo()
        self.assertEqual(self.run_cli("new", "acme", "--at", repo / ".bindle")[0], 0)
        self.assertEqual(bindle.git(repo, "status", "--porcelain"), "")
        self.assertIn("/.bindle/", (repo / ".git/info/exclude").read_text())
        self.assertFalse((repo / ".gitignore").exists())

    def test_new_outside_a_repo_touches_nothing_else(self):
        self.make_bindle("acme")
        self.assertFalse((self.tmp / ".git").exists())

    def test_doctor_flags_a_bindle_the_repo_would_commit(self):
        repo = self.project_repo()
        self.run_cli("new", "acme", "--at", repo / ".bindle")
        (repo / ".git/info/exclude").write_text("")
        self.run_cli("attach", repo / ".bindle", repo, "--writable")
        code, out = self.run_cli("doctor", repo)
        self.assertEqual(code, 1)
        self.assertIn("not ignored there", out)

    def test_doctor_flags_a_bindle_the_repo_already_tracks(self):
        repo = self.project_repo()
        self.run_cli("new", "acme", "--at", repo / ".bindle")
        (repo / ".git/info/exclude").write_text("")
        rmtree(repo / ".bindle/.git")
        bindle.git(repo, "add", "-A")
        self.run_cli("attach", repo / ".bindle", repo)
        code, out = self.run_cli("doctor", repo)
        self.assertEqual(code, 1)
        self.assertIn("tracked by the repo", out)

    # The demo repo folds its bindle in on purpose; doctor must not cry wolf there.
    def test_a_demo_bindle_may_be_tracked(self):
        repo = self.project_repo()
        self.run_cli("new", "demo", "--at", repo / ".bindle")
        (repo / ".git/info/exclude").write_text("")
        rmtree(repo / ".bindle/.git")
        meta = json.loads((repo / ".bindle/bindle.json").read_text())
        meta["demo"] = True
        (repo / ".bindle/bindle.json").write_text(json.dumps(meta))
        bindle.git(repo, "add", "-A")
        self.run_cli("attach", repo / ".bindle", repo)
        code, out = self.run_cli("doctor", repo)
        self.assertEqual(code, 0, out)


class NotesTest(BindleTest):
    def test_scratch_notes_are_ignored_but_their_readme_is_kept(self):
        b = self.make_bindle("acme")
        self.assertIn("notes/scratch/README.md", bindle.git(b, "ls-files"))
        (b / "notes/scratch/dump.txt").write_text("throwaway\n")
        self.assertEqual(bindle.git(b, "status", "--porcelain"), "")

    def test_doctor_flags_a_secret_in_a_note(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        (b / "notes/logins.md").write_text("api_key = abcdefghijklmnopqrstuvwx\n")
        code, out = self.run_cli("doctor", f)
        self.assertEqual(code, 1)
        self.assertIn("notes/logins.md may hold a secret; move it to secure storage", out)

    # Ignored files never leave the machine; flagging them would only be noise.
    def test_doctor_ignores_secrets_in_files_git_ignores(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        (b / "notes/scratch/tmp.md").write_text("token: abcdefghijklmnopqrstuvwx\n")
        self.assertEqual(self.run_cli("doctor", f)[0], 0)

    def test_upgrade_adds_missing_ignore_rules_without_touching_the_bindles_own(self):
        b = self.make_bindle("acme")
        (b / ".gitignore").write_text("*.out\n")
        (b / ".gitattributes").unlink()
        (b / "notes/scratch/README.md").unlink()
        bindle.git(b, "add", "-A"); bindle.git(b, "commit", "-qm", "an old bindle")
        self.run_cli("upgrade", b)
        ignore = (b / ".gitignore").read_text()
        self.assertTrue(ignore.startswith("*.out\n"))
        self.assertIn("notes/scratch/*", ignore)
        self.assertIn("merge=union", (b / ".gitattributes").read_text())
        self.assertTrue((b / "notes/scratch/README.md").exists())
        self.assertEqual(bindle.git(b, "status", "--porcelain"), "")


class AttachTest(BindleTest):
    def test_attach_turns_the_plugin_on_without_making_it_writable(self):
        b, f = self.make_bindle("personal"), self.folder()
        self.assertEqual(self.run_cli("attach", b, f)[0], 0)
        s = self.settings(f)
        self.assertTrue(s["enabledPlugins"]["personal@bindle-personal"])
        self.assertEqual(s["extraKnownMarketplaces"]["bindle-personal"]["source"]["path"], str(b))
        self.assertNotIn("autoMemoryDirectory", s)

    def test_writable_points_auto_memory_at_the_bindle(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        self.assertEqual(self.settings(f)["autoMemoryDirectory"], str(b / "memory"))

    # One writable bindle per folder is what keeps a work session from writing into personal.
    def test_a_second_writable_bindle_is_refused(self):
        acme, personal, f = self.make_bindle("acme"), self.make_bindle("personal"), self.folder()
        self.run_cli("attach", acme, f, "--writable")
        code, out = self.run_cli("attach", personal, f, "--writable")
        self.assertEqual(code, 1)
        self.assertIn("one writable bindle", out)
        self.assertEqual(self.settings(f)["autoMemoryDirectory"], str(acme / "memory"))
        self.assertNotIn("personal@bindle-personal", self.settings(f).get("enabledPlugins", {}))

    def test_another_bindle_can_be_on_beside_the_writable_one(self):
        acme, personal, f = self.make_bindle("acme"), self.make_bindle("personal"), self.folder()
        self.run_cli("attach", acme, f, "--writable")
        self.assertEqual(self.run_cli("attach", personal, f)[0], 0)
        self.assertEqual(set(self.settings(f)["enabledPlugins"]), {"acme@bindle-acme", "personal@bindle-personal"})

    def test_attaching_twice_doesnt_call_claude_again(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f)
        calls = len(self.claude_calls())
        self.run_cli("attach", b, f)
        self.assertEqual(len(self.claude_calls()), calls)

    # Claude Code reads settings.local.json at the repo root, so attaching to a subfolder of a
    # repo would silently configure the whole repo instead.
    def test_refuses_a_folder_inside_someone_elses_git_repo(self):
        b, repo = self.make_bindle("acme"), self.folder("repo")
        subprocess.run(["git", "init", "-q", str(repo)], check=True)
        (repo / "sub").mkdir()
        code, out = self.run_cli("attach", b, repo / "sub")
        self.assertEqual(code, 1)
        self.assertIn("repo root", out)
        self.assertEqual(self.claude_calls(), [])

    def test_refuses_something_that_isnt_a_bindle(self):
        self.assertEqual(self.run_cli("attach", self.folder("plain"), self.folder())[0], 1)


class LockTest(BindleTest):
    """A read-only bindle must be impossible to edit from a session, not just discouraged."""

    def deny(self, f):
        return self.settings(f).get("permissions", {}).get("deny", [])

    def test_a_read_only_bindle_is_locked_against_edits(self):
        b, f = self.make_bindle("personal"), self.folder()
        self.run_cli("attach", b, f)
        self.assertEqual(self.deny(f), [f"Edit(/{b}/**)"])

    # Memories are written with the Write tool; locking the writable bindle would silently stop them.
    def test_the_writable_bindle_is_never_locked(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f)
        self.run_cli("attach", b, f, "--writable")
        self.assertEqual(self.deny(f), [])

    def test_reattaching_a_writable_bindle_without_the_flag_keeps_it_writable_and_unlocked(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        self.run_cli("attach", b, f)
        self.assertEqual(self.settings(f)["autoMemoryDirectory"], str(b / "memory"))
        self.assertEqual(self.deny(f), [])

    def test_detach_removes_the_lock_and_leaves_other_rules(self):
        b, f = self.make_bindle("personal"), self.folder()
        (f / ".claude").mkdir()
        (f / ".claude/settings.local.json").write_text(json.dumps({"permissions": {"deny": ["Bash(rm -rf:*)"]}}))
        self.run_cli("attach", b, f)
        self.run_cli("detach", "personal", f)
        self.assertEqual(self.deny(f), ["Bash(rm -rf:*)"])

    def test_doctor_flags_an_unlocked_read_only_bindle(self):
        b, f = self.make_bindle("personal"), self.folder()
        self.run_cli("attach", b, f)
        s = self.settings(f)
        del s["permissions"]
        (f / ".claude/settings.local.json").write_text(json.dumps(s))
        code, out = self.run_cli("doctor", f)
        self.assertEqual(code, 1)
        self.assertIn("not locked against edits", out)


class RulesTest(BindleTest):
    """Plugins can't carry a CLAUDE.md, so each bindle's rules reach the session through its own hook."""

    def run_rules(self, b, folder):
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(b), "CLAUDE_PROJECT_DIR": str(folder)}
        return subprocess.run([sys.executable, str(b / "hooks/bindle_hook.py"), "rules"], env=env, capture_output=True, text=True).stdout

    def test_rules_load_whether_the_bindle_is_writable_or_read_only(self):
        acme, personal, f = self.make_bindle("acme"), self.make_bindle("personal"), self.folder()
        (acme / "rules.md").write_text("Use Acme's ticket prefix.\n")
        (personal / "rules.md").write_text("Prefer small PRs.\n")
        self.run_cli("attach", acme, f, "--writable")
        self.run_cli("attach", personal, f)
        self.assertIn("Use Acme's ticket prefix.", self.run_rules(acme, f))
        self.assertIn("Follow them as you would CLAUDE.md", self.run_rules(acme, f))
        self.assertIn("Prefer small PRs.", self.run_rules(personal, f))

    # Past the hook cap, Claude Code shows only the first 2,000 characters and the rest is silently lost.
    def test_doctor_flags_rules_too_long_for_the_hook(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        (b / "rules.md").write_text("x" * (bindle.RULES_LIMIT + 1))
        code, out = self.run_cli("doctor", f)
        self.assertEqual(code, 1)
        self.assertIn("rules.md is over", out)


class DetachTest(BindleTest):
    def test_detach_turns_it_off_and_returns_memory_to_the_default(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        self.assertEqual(self.run_cli("detach", "acme", f)[0], 0)
        s = self.settings(f)
        self.assertNotIn("acme@bindle-acme", s.get("enabledPlugins", {}))
        self.assertNotIn("autoMemoryDirectory", s)

    def test_detaching_a_read_only_bindle_leaves_the_writable_one_alone(self):
        acme, personal, f = self.make_bindle("acme"), self.make_bindle("personal"), self.folder()
        self.run_cli("attach", acme, f, "--writable")
        self.run_cli("attach", personal, f)
        self.run_cli("detach", "personal", f)
        self.assertEqual(self.settings(f)["autoMemoryDirectory"], str(acme / "memory"))


class DoctorTest(BindleTest):
    def test_reports_which_bindles_are_on_and_which_is_writable(self):
        acme, personal, f = self.make_bindle("acme"), self.make_bindle("personal"), self.folder()
        self.run_cli("attach", acme, f, "--writable")
        self.run_cli("attach", personal, f)
        code, out = self.run_cli("doctor", f)
        self.assertEqual(code, 0, out)
        self.assertIn("acme: on, writable", out)
        self.assertIn("personal: on, read-only, sync off", out)

    def test_flags_a_hook_that_drifted_from_the_template(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f)
        with open(b / "hooks/bindle_hook.py", "a") as h:
            h.write("# local edit\n")
        code, out = self.run_cli("doctor", f)
        self.assertEqual(code, 1)
        self.assertIn("bindle_hook.py differs", out)
        self.assertIn(f"bindle upgrade {b}", out)
        self.assertNotIn("&& git -C", out)

    # Unsaved memories are the main way work gets lost between machines.
    def test_reports_uncommitted_memories_and_a_missing_remote(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        (b / "memory" / "fact.md").write_text("x")
        _, out = self.run_cli("doctor", f)
        self.assertIn("1 uncommitted change(s)", out)
        self.assertIn("no remote", out)

    # attach stores the bindle's absolute path, so moving the bindle silently breaks the folder;
    # doctor must say so instead of reporting nothing attached.
    def test_flags_a_bindle_that_moved_after_attaching(self):
        b, f = self.make_bindle("personal"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        b.rename(self.tmp / "moved")
        code, out = self.run_cli("doctor", f)
        self.assertEqual(code, 1)
        self.assertIn("bindle-personal: was on, but nothing is at", out)
        self.assertIn("attach it from its new path", out)
        self.assertIn("bindle detach bindle-personal", out)
        self.assertIn("doesn't exist", out)
        self.assertNotIn("No bindles attached", out)

    def test_an_empty_folder_has_nothing_attached(self):
        _, out = self.run_cli("doctor", self.folder())
        self.assertIn("No bindles attached", out)
        self.assertIn("default folder", out)


class InstallTest(BindleTest):
    def setUp(self):
        super().setUp()
        self.home = self.tmp / "home"
        self.home.mkdir()
        self.saved_home = {k: os.environ.get(k) for k in ("HOME", "USERPROFILE")}
        for k in self.saved_home:  # Path.home() reads USERPROFILE on Windows, HOME elsewhere
            os.environ[k] = str(self.home)

    def tearDown(self):
        for k, v in self.saved_home.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v
        super().tearDown()

    def test_installs_the_cli_and_the_command_and_nothing_else(self):
        self.assertEqual(self.run_cli("install")[0], 0)
        if bindle.core.WINDOWS:
            self.assertIn(str(bindle.BASE / "bin" / "bindle"), (self.home / ".local/bin/bindle.cmd").read_text())
        else:
            self.assertEqual(os.readlink(self.home / ".local/bin/bindle"), str(bindle.BASE / "bin/bindle"))
        self.assertIn("bindle", (self.home / ".claude/commands/bindle.md").read_text())
        self.assertTrue((self.home / ".claude/skills/bindle-promote/SKILL.md").exists())
        self.assertEqual(sorted(p.name for p in (self.home / ".claude").iterdir()), ["commands", "skills"])

    def test_installing_twice_is_fine(self):
        self.run_cli("install")
        self.assertEqual(self.run_cli("install")[0], 0)

    # A real file there is the person's own; replacing it would lose their work.
    def test_refuses_to_replace_a_real_file(self):
        (self.home / ".claude/commands").mkdir(parents=True)
        (self.home / ".claude/commands/bindle.md").write_text("mine")
        self.assertEqual(self.run_cli("install")[0], 1)
        self.assertEqual((self.home / ".claude/commands/bindle.md").read_text(), "mine")
        self.assertFalse((self.home / ".local/bin/bindle").exists())


class DocsTest(unittest.TestCase):
    # The README is how people learn the commands; a command it doesn't list is one nobody finds.
    def test_readme_lists_every_command(self):
        readme = (bindle.BASE / "README.md").read_text()
        parser_cmds = ["install", "new", "attach", "detach", "doctor", "sync", "upgrade", "outbox add", "outbox list", "collect"]
        import argparse
        sub = next(a for a in bindle.build_parser()._actions if isinstance(a, argparse._SubParsersAction))
        self.assertEqual(sorted(sub.choices), sorted({c.split()[0] for c in parser_cmds}))
        for c in parser_cmds:
            self.assertIn(f"`bindle {c}", readme, c)


class UpgradeTest(BindleTest):
    """Base updates reach existing bindles only through upgrade, since each bindle carries its own copies."""

    def test_brings_a_drifted_or_old_bindle_up_to_date_and_commits(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f)
        (b / "hooks/bindle_hook.py").write_text("# old\n")
        (b / "hooks/lib.sh").write_text("# obsolete\n")
        (b / "AGENTS.md").unlink()
        bindle.git(b, "add", "-A")
        bindle.git(b, "commit", "-qm", "an old bindle")
        self.assertEqual(self.run_cli("upgrade", b)[0], 0)
        self.assertEqual((b / "hooks/bindle_hook.py").read_bytes(), (bindle.TEMPLATE / "hooks/bindle_hook.py").read_bytes())
        self.assertFalse((b / "hooks/lib.sh").exists())
        self.assertIn("acme bindle", (b / "AGENTS.md").read_text())
        self.assertEqual(bindle.git(b, "status", "--porcelain"), "")
        self.assertEqual(self.run_cli("doctor", f)[0], 0)

    # Upgrade owns only its files; a person's own edits must stay theirs.
    def test_never_overwrites_or_commits_the_bindles_own_files(self):
        b = self.make_bindle("acme")
        (b / "README.md").write_text("my readme\n")
        (b / "memory/fact.md").write_text("unsaved\n")
        (b / "hooks/bindle_hook.py").write_text("# old\n")
        self.run_cli("upgrade", b)
        self.assertEqual((b / "README.md").read_text(), "my readme\n")
        status = bindle.git(b, "status", "--porcelain")
        self.assertIn("README.md", status)
        self.assertIn("memory/fact.md", status)
        self.assertNotIn("bindle_hook.py", status)

    def test_dry_run_changes_nothing(self):
        b = self.make_bindle("acme")
        (b / "hooks/bindle_hook.py").write_text("# old\n")
        code, out = self.run_cli("upgrade", b, "--dry-run")
        self.assertIn("update hooks/bindle_hook.py", out)
        self.assertEqual((b / "hooks/bindle_hook.py").read_text(), "# old\n")

    def test_an_up_to_date_bindle_gets_no_commit(self):
        b = self.make_bindle("acme")
        head = bindle.git(b, "rev-parse", "HEAD")
        _, out = self.run_cli("upgrade", b)
        self.assertIn("up to date", out)
        self.assertEqual(bindle.git(b, "rev-parse", "HEAD"), head)

    def test_refuses_a_bindle_from_a_newer_version(self):
        b = self.make_bindle("acme")
        meta = json.loads((b / "bindle.json").read_text())
        meta["layout"] = bindle.LAYOUT + 1
        (b / "bindle.json").write_text(json.dumps(meta))
        code, out = self.run_cli("upgrade", b)
        self.assertEqual(code, 1)
        self.assertIn("git pull bindle", out)

    # The fix for a bindle with a remote includes the push, so the other machines get it too.
    def test_doctor_offers_a_copy_paste_fix_that_pushes(self):
        b, f = self.make_bindle("craft"), self.folder()
        remote = self.tmp / "craft.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(b), str(remote)], check=True)
        bindle.git(b, "remote", "add", "origin", str(remote)); bindle.git(b, "fetch", "-q", "origin")
        bindle.git(b, "branch", "-q", "-u", "origin/" + bindle.git(b, "rev-parse", "--abbrev-ref", "HEAD"))
        self.run_cli("attach", b, f)
        (b / "hooks/bindle_hook.py").write_text("# old\n")
        (b / "hooks/hooks.json").write_text("{}\n")
        _, out = self.run_cli("doctor", f)
        self.assertIn(f"bindle upgrade {b} && git -C {b} push", out)
        self.assertEqual(out.count(f"bindle upgrade {b}"), 1)

    def test_upgrades_every_bindle_attached_to_the_current_folder(self):
        acme, personal, f = self.make_bindle("acme"), self.make_bindle("personal"), self.folder()
        self.run_cli("attach", acme, f, "--writable")
        self.run_cli("attach", personal, f)
        for b in (acme, personal):
            (b / "hooks/bindle_hook.py").write_text("# old\n")
        cwd = os.getcwd()
        os.chdir(f)
        try:
            self.run_cli("upgrade")
        finally:
            os.chdir(cwd)
        for b in (acme, personal):
            self.assertEqual((b / "hooks/bindle_hook.py").read_bytes(), (bindle.TEMPLATE / "hooks/bindle_hook.py").read_bytes())


class PromotionTest(BindleTest):
    """Material crosses between bindles only as reviewed, general text, through the source's outbox."""

    def setUp(self):
        super().setUp()
        self.acme = self.make_bindle("acme")
        self.personal = self.make_bindle("personal")
        (self.acme / "private-terms.txt").write_text("# terms\nAcme\nACME-\nwidgetd\n")
        bindle.git(self.acme, "commit", "-qam", "terms")
        self.draft = self.tmp / "draft.md"
        self.draft.write_text("---\nname: small-prs\ndescription: keep PRs small\ntype: feedback\nboundary: craft\n---\nKeep PRs small.\n")

    def add(self, *extra):
        return self.run_cli("outbox", "add", self.acme, self.draft, "--name", "small-prs", "--description", "keep PRs small", *extra)

    def test_an_approved_memory_reaches_the_target_with_an_index_line(self):
        self.assertEqual(self.add()[0], 0)
        code, out = self.run_cli("collect", self.acme, "--into", self.personal, "--items", "small-prs")
        self.assertEqual(code, 0, out)
        self.assertIn("Keep PRs small.", (self.personal / "memory/small-prs.md").read_text())
        self.assertIn("(small-prs.md) — keep PRs small", (self.personal / "memory/MEMORY.md").read_text())
        item = json.loads((self.acme / "outbox/small-prs/item.json").read_text())
        self.assertEqual((item["status"], item["collected_into"]), ("collected", ["personal"]))
        self.assertEqual(bindle.git(self.personal, "status", "--porcelain"), "")
        self.assertEqual(bindle.git(self.acme, "status", "--porcelain"), "")

    # The leak check is the structural guard: a draft that still names the domain never enters the outbox.
    def test_a_draft_naming_the_domain_is_refused(self):
        self.draft.write_text("Keep PRs small, like we do on widgetd.\n")
        code, out = self.add()
        self.assertEqual(code, 1)
        self.assertIn("widgetd", out)
        self.assertFalse((self.acme / "outbox/small-prs").exists())

    def test_terms_match_whole_words_case_insensitively(self):
        self.draft.write_text("Ticket ACME-123 taught us this.\n")
        self.assertEqual(self.add()[0], 1)
        self.draft.write_text("Acmeological reasoning is fine.\n")
        self.assertEqual(self.add()[0], 0)

    def test_a_ticket_prefix_term_matches_ticket_keys(self):
        (self.acme / "private-terms.txt").write_text("PROJ-\n")
        self.draft.write_text("Fixed in PROJ-4512.\n")
        self.assertEqual(self.add()[0], 1)

    def test_a_draft_that_looks_like_a_secret_is_refused(self):
        self.draft.write_text("token: abcdefghijklmnopqrstuvwxyz123456\n")
        code, out = self.add()
        self.assertEqual(code, 1)
        self.assertIn("possible secret", out)

    # The outbox could be edited after approval; collect checks again at the moment of crossing.
    def test_collect_rechecks_an_outbox_item_edited_after_approval(self):
        self.add()
        (self.acme / "outbox/small-prs/memory.md").write_text("Edited later to mention Acme.\n")
        code, out = self.run_cli("collect", self.acme, "--into", self.personal, "--items", "small-prs")
        self.assertEqual(code, 1)
        self.assertFalse((self.personal / "memory/small-prs.md").exists())

    # Naming the items puts them in Claude Code's permission prompt, which is the person's gate.
    def test_collect_needs_named_items_or_all(self):
        self.add()
        code, out = self.run_cli("collect", self.acme, "--into", self.personal)
        self.assertEqual(code, 1)
        self.assertIn("--items", out)

    def test_collecting_twice_moves_nothing_the_second_time(self):
        self.add()
        self.run_cli("collect", self.acme, "--into", self.personal, "--items", "small-prs")
        _, out = self.run_cli("collect", self.acme, "--into", self.personal, "--items", "small-prs")
        self.assertIn("already in personal", out)
        lines = [l for l in (self.personal / "memory/MEMORY.md").read_text().splitlines() if "small-prs" in l]
        self.assertEqual(len(lines), 1)

    def test_a_skill_moves_as_a_folder(self):
        skill = self.tmp / "review-checklist"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: review-checklist\ndescription: x\n---\nCheck tests first.\n")
        self.assertEqual(self.run_cli("outbox", "add", self.acme, skill, "--kind", "skill", "--name", "review-checklist")[0], 0)
        self.assertEqual(self.run_cli("collect", self.acme, "--into", self.personal, "--items", "review-checklist")[0], 0)
        self.assertIn("Check tests first.", (self.personal / "skills/review-checklist/SKILL.md").read_text())

    def test_never_overwrites_something_already_in_the_target(self):
        self.add()
        (self.personal / "memory/small-prs.md").write_text("mine\n")
        code, _ = self.run_cli("collect", self.acme, "--into", self.personal, "--items", "small-prs")
        self.assertEqual(code, 1)
        self.assertEqual((self.personal / "memory/small-prs.md").read_text(), "mine\n")


class AudienceWritesTest(BindleTest):
    def test_new_records_audience_and_writes(self):
        self.run_cli("new", "craft", "--at", self.tmp / "craft", "--audience", "shared", "--writes", "explicit")
        meta = json.loads((self.tmp / "craft/bindle.json").read_text())
        self.assertEqual((meta["audience"], meta["writes"]), ("shared", "explicit"))

    # An explicit bindle only takes reviewed material; letting sessions write memories into it would bypass that.
    def test_an_explicit_bindle_cannot_be_writable(self):
        self.run_cli("new", "craft", "--at", self.tmp / "craft", "--writes", "explicit")
        code, out = self.run_cli("attach", self.tmp / "craft", self.folder(), "--writable")
        self.assertEqual(code, 1)
        self.assertIn("explicit writes only", out)
        self.assertEqual(self.claude_calls(), [])

    def test_doctor_shows_a_non_default_audience(self):
        self.run_cli("new", "craft", "--at", self.tmp / "craft", "--audience", "shared", "--writes", "explicit")
        f = self.folder()
        self.run_cli("attach", self.tmp / "craft", f)
        self.assertIn("craft: on, read-only, shared, explicit writes, sync off", self.run_cli("doctor", f)[1])


class ReviewRegressionTest(BindleTest):
    """Each test reproduces a finding from the 2026-11-21 independent review."""

    def hook(self, b, folder, command):
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(b), "CLAUDE_PROJECT_DIR": str(folder)}
        return subprocess.run([sys.executable, str(b / "hooks/bindle_hook.py"), command], env=env, capture_output=True, text=True)

    def with_remote(self, b):
        remote = self.tmp / f"{b.name}.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(b), str(remote)], check=True)
        bindle.git(b, "remote", "add", "origin", str(remote))
        bindle.git(b, "push", "-q", "-u", "origin", "HEAD")
        return remote

    # Writable detection used a regex built from the path: accents and brackets made it fail silently.
    def test_writable_is_detected_for_paths_with_accents_brackets_and_spaces(self):
        b = self.tmp / "José [1] x" / "bindle"
        b.parent.mkdir()
        self.assertEqual(self.run_cli("new", "acme", "--at", b)[0], 0)
        f = self.folder()
        self.run_cli("attach", b, f, "--writable")
        self.assertIn("is on and writable", self.hook(b, f, "session-start").stdout)

    # A crafted item.json could point collect at the source's private memories.
    def test_collect_refuses_an_item_pointing_outside_its_folder(self):
        acme, personal = self.make_bindle("acme"), self.make_bindle("personal")
        (acme / "memory/private.md").write_text("private context\n")
        item = acme / "outbox/evil"
        item.mkdir(parents=True)
        (item / "item.json").write_text(json.dumps({"kind": "memory", "file": "../../memory/private.md", "status": "approved"}))
        code, out = self.run_cli("collect", acme, "--into", personal, "--items", "evil")
        self.assertEqual(code, 1)
        self.assertFalse((personal / "memory/evil.md").exists())

    def test_collect_refuses_an_item_that_was_never_approved(self):
        acme, personal = self.make_bindle("acme"), self.make_bindle("personal")
        draft = self.tmp / "d.md"; draft.write_text("general\n")
        self.run_cli("outbox", "add", acme, draft, "--name", "lesson")
        meta = json.loads((acme / "outbox/lesson/item.json").read_text()); meta["status"] = "draft"
        (acme / "outbox/lesson/item.json").write_text(json.dumps(meta))
        code, out = self.run_cli("collect", acme, "--into", personal, "--items", "lesson")
        self.assertEqual(code, 1)
        self.assertIn("not approved", out)

    # copytree followed links that the leak check skipped, carrying a whole memory folder across.
    def test_a_draft_containing_a_symlink_is_refused(self):
        acme = self.make_bindle("acme")
        skill = self.tmp / "review"; skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: review\ndescription: x\n---\nok\n")
        try:
            (skill / "ref").symlink_to(acme / "memory", target_is_directory=True)
        except OSError:
            self.skipTest("symlinks aren't allowed here (Windows without developer mode)")
        code, out = self.run_cli("outbox", "add", acme, skill, "--kind", "skill", "--name", "review")
        self.assertEqual(code, 1)
        self.assertIn("symlink", out)

    # The leak check read only file contents; names and descriptions crossed unchecked.
    def test_the_leak_check_covers_name_description_and_file_names(self):
        acme = self.make_bindle("acme")
        (acme / "private-terms.txt").write_text("widgetd\n")
        draft = self.tmp / "d.md"; draft.write_text("general\n")
        self.assertEqual(self.run_cli("outbox", "add", acme, draft, "--name", "widgetd-prs")[0], 1)
        self.assertEqual(self.run_cli("outbox", "add", acme, draft, "--name", "prs", "--description", "how widgetd ships")[0], 1)
        skill = self.tmp / "deploy"; skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: deploy\ndescription: x\n---\nok\n")
        (skill / "widgetd-runbook.md").write_text("steps\n")
        self.assertEqual(self.run_cli("outbox", "add", acme, skill, "--kind", "skill", "--name", "deploy")[0], 1)

    # The secret check was case-sensitive and missed common formats.
    def test_the_secret_check_catches_common_credential_formats(self):
        h = bindle.core.hooks()
        for text in ["API_KEY=abcdefghijklmnopqrstuvwx1234", "AWS_SECRET_ACCESS_KEY=wJalrXUtnFEMIK7MDENGbPxRfiCYEXAMPLEKEY",
                     "password: Tr0ub4dor&3-horse!battery", "github_pat_11ABCDEFG0123456789abcdefghij",
                     "AIzaSyA1234567890abcdefghijklmnopqrstuv"]:
            self.assertTrue(h.looks_secret(text), text)
        for text in ["password: (in 1Password)", "token: ${SONAR_TOKEN}", "the API key lives in the vault"]:
            self.assertFalse(h.looks_secret(text), text)

    def test_sync_refuses_an_uppercase_api_key(self):
        b, f = self.make_bindle("acme"), self.folder()
        meta = json.loads((b / "bindle.json").read_text()); meta["sync"] = True
        (b / "bindle.json").write_text(json.dumps(meta)); bindle.git(b, "commit", "-qam", "sync on")
        self.run_cli("attach", b, f, "--writable")
        (b / "memory/k.md").write_text("API_KEY=abcdefghijklmnopqrstuvwx1234\n")
        head = bindle.git(b, "rev-parse", "HEAD")
        self.hook(b, f, "session-end")
        self.assertEqual(bindle.git(b, "rev-parse", "HEAD"), head)

    # git quotes non-ASCII names by default, so the check couldn't open them.
    def test_doctor_checks_notes_with_non_ascii_names(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        (b / "notes/café.md").write_text("token: abcdefghijklmnopqrstuvwx\n")
        code, out = self.run_cli("doctor", f)
        self.assertIn("café.md may hold a secret", out)

    # Following the "add a remote" hint without -u left sync silently local forever.
    def test_doctor_flags_a_remote_without_an_upstream(self):
        b, f = self.make_bindle("acme"), self.folder()
        remote = self.tmp / "r.git"
        subprocess.run(["git", "init", "-q", "--bare", str(remote)], check=True)
        bindle.git(b, "remote", "add", "origin", str(remote))
        self.run_cli("attach", b, f, "--writable")
        code, out = self.run_cli("doctor", f)
        self.assertEqual(code, 1)
        self.assertIn("push -u origin HEAD", out)

    def test_upgrade_stamps_a_missing_layout_instead_of_crashing(self):
        b = self.make_bindle("acme")
        meta = json.loads((b / "bindle.json").read_text()); del meta["layout"]
        (b / "bindle.json").write_text(json.dumps(meta)); bindle.git(b, "commit", "-qam", "old")
        self.assertEqual(self.run_cli("upgrade", b)[0], 0)
        self.assertEqual(json.loads((b / "bindle.json").read_text())["layout"], bindle.LAYOUT)

    # `git add -- memory outbox` failed when outbox/ was missing, so memories never synced.
    def test_memories_sync_when_the_outbox_folder_is_missing(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.with_remote(b)
        meta = json.loads((b / "bindle.json").read_text()); meta["sync"] = True
        (b / "bindle.json").write_text(json.dumps(meta))
        bindle.git(b, "rm", "-rq", "outbox"); bindle.git(b, "commit", "-qam", "no outbox"); bindle.git(b, "push", "-q")
        self.run_cli("attach", b, f, "--writable")
        (b / "memory/fact.md").write_text("x\n")
        self.hook(b, f, "session-end")
        self.assertEqual(bindle.git(b, "status", "--porcelain"), "")
        self.assertEqual(bindle.git(b, "rev-list", "--count", "@{upstream}..HEAD"), "0")

    # The sync log was hard-coded under .git/, which is a file in a worktree.
    def test_sync_works_in_a_worktree(self):
        main = self.make_bindle("acme")
        meta = json.loads((main / "bindle.json").read_text()); meta["sync"] = True
        (main / "bindle.json").write_text(json.dumps(meta)); bindle.git(main, "commit", "-qam", "sync on")
        wt = self.tmp / "acme-wt"
        bindle.git(main, "worktree", "add", "-q", "-b", "wt", str(wt))
        f = self.folder()
        self.run_cli("attach", wt, f, "--writable")
        (wt / "memory/fact.md").write_text("x\n")
        self.hook(wt, f, "session-end")
        self.assertEqual(bindle.git(wt, "status", "--porcelain"), "")

    # A folder in the current directory with the bindle's name made detach treat the name as a path.
    def test_detach_prefers_an_attached_name_over_a_folder_of_that_name(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f)
        (self.tmp / "acme").mkdir()
        cwd = os.getcwd(); os.chdir(self.tmp)
        try:
            code, out = self.run_cli("detach", "acme", f)
        finally:
            os.chdir(cwd)
        self.assertEqual(code, 0, out)

    def test_a_moved_bindle_can_be_detached_by_name(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        b.rename(self.tmp / "moved")
        code, out = self.run_cli("detach", "acme", f)
        self.assertEqual(code, 0, out)
        s = self.settings(f)
        self.assertNotIn("bindle-acme", s.get("extraKnownMarketplaces", {}))
        self.assertNotIn("autoMemoryDirectory", s)

    # A failure partway through collect left some items copied and marked collected.
    def test_collect_writes_nothing_when_any_item_fails(self):
        acme, personal = self.make_bindle("acme"), self.make_bindle("personal")
        for n in ("one", "two"):
            d = self.tmp / f"{n}.md"; d.write_text(f"{n}\n")
            self.run_cli("outbox", "add", acme, d, "--name", n)
        (acme / "outbox/two/memory.md").write_text("edited after approval\n")
        code, _ = self.run_cli("collect", acme, "--into", personal, "--items", "one,two")
        self.assertEqual(code, 1)
        self.assertFalse((personal / "memory/one.md").exists())
        self.assertEqual(json.loads((acme / "outbox/one/item.json").read_text())["status"], "approved")

    def test_a_command_must_be_a_file(self):
        acme = self.make_bindle("acme")
        folder = self.tmp / "cmd"; folder.mkdir()
        self.assertEqual(self.run_cli("outbox", "add", acme, folder, "--kind", "command", "--name", "c")[0], 1)

    def test_collect_with_a_missing_item_file_fails_cleanly(self):
        acme, personal = self.make_bindle("acme"), self.make_bindle("personal")
        d = self.tmp / "d.md"; d.write_text("x\n")
        self.run_cli("outbox", "add", acme, d, "--name", "gone")
        (acme / "outbox/gone/memory.md").unlink()
        code, out = self.run_cli("collect", acme, "--into", personal, "--items", "gone")
        self.assertEqual(code, 1)
        self.assertIn("missing", out)

    # Sync committed into a rebase the person was in the middle of.
    def test_sync_skips_while_a_rebase_is_in_progress(self):
        b, f = self.make_bindle("acme"), self.folder()
        meta = json.loads((b / "bindle.json").read_text()); meta["sync"] = True
        (b / "bindle.json").write_text(json.dumps(meta)); bindle.git(b, "commit", "-qam", "sync on")
        self.run_cli("attach", b, f, "--writable")
        (Path(bindle.git(b, "rev-parse", "--absolute-git-dir")) / "rebase-merge").mkdir()
        (b / "memory/fact.md").write_text("x\n")
        head = bindle.git(b, "rev-parse", "HEAD")
        self.hook(b, f, "session-end")
        self.assertEqual(bindle.git(b, "rev-parse", "HEAD"), head)

    def test_doctor_quotes_paths_in_its_fix_commands(self):
        b = self.tmp / "my bindles" / "acme"
        b.parent.mkdir()
        self.run_cli("new", "acme", "--at", b)
        f = self.folder()
        self.run_cli("attach", b, f)
        (b / "hooks/bindle_hook.py").write_text("# old\n")
        _, out = self.run_cli("doctor", f)
        self.assertIn(f"bindle upgrade '{b}'", out)


class PortabilityTest(BindleTest):
    # Claude Code normalizes Windows paths to POSIX form before matching permission rules: C:\\x -> /c/x.
    def test_lock_rules_use_claude_codes_path_form(self):
        self.assertEqual(bindle.core.rule_path("C:\\Users\\me\\bindle"), "/c/Users/me/bindle")
        self.assertEqual(bindle.core.rule_path("/Users/me/bindle"), "/Users/me/bindle")
        self.assertEqual(bindle.core.lock_rules("D:/x"), ["Edit(//d/x/**)"])

    # The hook command finds a working Python itself, since `python3` may be missing or a stub on Windows.
    def test_the_launcher_runs_the_hook(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(b), "CLAUDE_PROJECT_DIR": str(f)}
        out = subprocess.run(["bash", str(b / "hooks/run"), "session-start"], env=env, capture_output=True, text=True)
        self.assertIn("is on and writable", out.stdout, out.stderr)


class TrustTest(BindleTest):
    """A bindle's hooks and servers run with the person's permissions; code they didn't write deserves a look.
    Warnings, not refusals: the person decides (guardrails, not gates)."""

    def test_doctor_warns_about_extra_code_in_a_read_only_bindle_without_failing(self):
        b, f = self.make_bindle("craft"), self.folder()
        (b / "hooks/telemetry.sh").write_text("curl example.com\n")
        (b / ".mcp.json").write_text("{}\n")
        self.run_cli("attach", b, f)
        code, out = self.run_cli("doctor", f)
        self.assertEqual(code, 0, out)
        self.assertIn("Warnings", out)
        self.assertIn("hooks/telemetry.sh", out)
        self.assertIn(".mcp.json", out)

    def test_plugin_json_hooks_and_servers_count_as_code(self):
        b = self.make_bindle("craft")
        manifest = json.loads((b / ".claude-plugin/plugin.json").read_text())
        manifest["mcpServers"] = {"x": {"command": "x"}}
        (b / ".claude-plugin/plugin.json").write_text(json.dumps(manifest))
        self.assertIn("plugin.json declares mcpServers", bindle.core.extra_code(bindle.core.load_bindle(b)))

    # Your own writable bindle may carry your own tools; warning there would only be noise.
    def test_no_warning_for_the_writable_bindle(self):
        b, f = self.make_bindle("personal"), self.folder()
        (b / "hooks/pixel.sh").write_text("echo hi\n")
        self.run_cli("attach", b, f, "--writable")
        self.assertNotIn("Warnings", self.run_cli("doctor", f)[1])

    def test_a_template_bindle_has_no_extra_code(self):
        self.assertEqual(bindle.core.extra_code(bindle.core.load_bindle(self.make_bindle("acme"))), [])

    def test_attach_warns_and_still_attaches(self):
        b, f = self.make_bindle("craft"), self.folder()
        (b / "hooks/extra.sh").write_text("echo\n")
        code, out = self.run_cli("attach", b, f)
        self.assertEqual(code, 0)
        self.assertIn("runs code on this machine", out)
        self.assertTrue(self.settings(f)["enabledPlugins"]["craft@bindle-craft"])

    # Someone with push access changes a shared bindle's hooks; the next session start says so before they run.
    def test_session_start_warns_when_a_pull_changes_code(self):
        b = self.make_bindle("craft")
        meta = json.loads((b / "bindle.json").read_text()); meta["sync"] = True
        (b / "bindle.json").write_text(json.dumps(meta)); bindle.git(b, "commit", "-qam", "sync on")
        remote = self.tmp / "craft.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(b), str(remote)], check=True)
        bindle.git(b, "remote", "add", "origin", str(remote)); bindle.git(b, "fetch", "-q", "origin")
        bindle.git(b, "branch", "-q", "-u", "origin/" + bindle.git(b, "rev-parse", "--abbrev-ref", "HEAD"))
        other = self.tmp / "other"
        subprocess.run(["git", "clone", "-q", str(remote), str(other)], check=True)
        (other / "hooks/new.sh").write_text("echo surprise\n")
        bindle.git(other, "add", "-A"); bindle.git(other, "commit", "-qm", "new hook"); bindle.git(other, "push", "-q")
        f = self.folder()
        self.run_cli("attach", b, f)
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(b), "CLAUDE_PROJECT_DIR": str(f)}
        out = subprocess.run([sys.executable, str(b / "hooks/bindle_hook.py"), "session-start"], env=env, capture_output=True, text=True).stdout
        self.assertIn("just pulled changes to files that run code", out)
        self.assertIn("hooks/new.sh", out)


class MemoryHookTest(BindleTest):
    """Runs the real hook script: it decides whether a session sees this bindle's memory twice."""

    def run_hook(self, b, folder):
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(b), "CLAUDE_PROJECT_DIR": str(folder)}
        return subprocess.run([sys.executable, str(b / "hooks/bindle_hook.py"), "session-start"], env=env, capture_output=True, text=True).stdout

    def test_prints_the_index_where_the_bindle_is_read_only(self):
        b, f = self.make_bindle("personal"), self.folder()
        (b / "memory/MEMORY.md").write_text("- [Fact](fact.md) — a personal fact\n")
        self.run_cli("attach", b, f)
        out = self.run_hook(b, f)
        self.assertIn("Memory index from the personal bindle", out)
        self.assertIn("read-only in this folder", out)
        self.assertIn("a personal fact", out)

    # Where it's writable, Claude Code loads the index itself; printing it again would duplicate it.
    def test_says_writable_without_repeating_the_index(self):
        b, f = self.make_bindle("personal"), self.folder()
        (b / "memory/MEMORY.md").write_text("- [Fact](fact.md) — a personal fact\n")
        self.run_cli("attach", b, f, "--writable")
        out = self.run_hook(b, f)
        self.assertIn("Bindle personal is on and writable", out)
        self.assertIn("projects/<project>/", out)
        self.assertNotIn("a personal fact", out)

    # Notes aren't loaded; the session only needs to know where they are, and only where the bindle is writable.
    def test_points_to_notes_where_writable(self):
        b, f = self.make_bindle("acme"), self.folder()
        (b / "notes/README.md").write_text("# Notes\n")
        self.run_cli("attach", b, f, "--writable")
        out = self.run_hook(b, f)
        self.assertIn("Notes for this domain are in", out)
        self.assertIn("notes/README.md", out)
        g = self.folder("elsewhere")
        self.run_cli("attach", b, g)
        self.assertNotIn("Notes for this domain", self.run_hook(b, g))

    # Notes, rules and skills are committed by hand; work left uncommitted is lost if the machine is.
    def test_reminds_about_uncommitted_notes_where_writable(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        (b / "notes/todo.md").write_text("draft\n")
        out = self.run_hook(b, f)
        self.assertIn("1 uncommitted change(s) (1 in notes)", out)

    # With sync on, memory/ commits itself at session end; reminding about it would be noise.
    def test_doesnt_count_what_sync_commits(self):
        b, f = self.make_bindle("acme"), self.folder()
        meta = json.loads((b / "bindle.json").read_text()); meta["sync"] = True
        (b / "bindle.json").write_text(json.dumps(meta)); bindle.git(b, "commit", "-qam", "sync on")
        self.run_cli("attach", b, f, "--writable")
        (b / "memory/fact.md").write_text("x\n")
        self.assertNotIn("uncommitted", self.run_hook(b, f))
        (b / "rules.md").write_text("a rule\n")
        self.assertIn("1 uncommitted change(s)", self.run_hook(b, f))

    def test_no_reminder_when_everything_is_committed(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        self.assertNotIn("uncommitted", self.run_hook(b, f))

    # Notes are committed by hand, so a secret could ride along with `git add -A`; flag it first.
    def test_flags_a_secret_in_an_uncommitted_note(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        (b / "notes/logins.md").write_text("password: abcdefghijklmnopqrstuvwx\n")
        self.assertIn("notes/logins.md may hold a secret", self.run_hook(b, f))

    def test_says_nothing_about_notes_when_there_are_none(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        self.assertNotIn("Notes for this domain", self.run_hook(b, f))

    # An agent has to know not to edit a read-only bindle even before it holds any memories.
    def test_tells_the_session_a_read_only_bindle_is_off_limits(self):
        b, f = self.make_bindle("personal"), self.folder()
        self.run_cli("attach", b, f)
        out = self.run_hook(b, f)
        self.assertIn("read-only in this folder", out)
        self.assertIn("don't edit its files", out)
        self.assertNotIn("Memory index", out)


class SyncTest(BindleTest):
    """Two clones of one bare repo stand in for two machines sharing a bindle."""

    def setUp(self):
        super().setUp()
        b = self.make_bindle_with("personal", "--sync")
        self.remote = self.tmp / "remote.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(b), str(self.remote)], check=True)
        subprocess.run(["git", "-C", str(b), "remote", "add", "origin", str(self.remote)], check=True)
        subprocess.run(["git", "-C", str(b), "fetch", "-q", "origin"], check=True)
        subprocess.run(["git", "-C", str(b), "branch", "-q", "-u", "origin/" + self.branch(b)], check=True)
        self.laptop = b
        self.desktop = self.tmp / "desktop-personal"
        subprocess.run(["git", "clone", "-q", str(self.remote), str(self.desktop)], check=True)
        self.laptop_folder, self.desktop_folder = self.folder("laptop"), self.folder("desktop")
        self.run_cli("attach", self.laptop, self.laptop_folder, "--writable")
        self.run_cli("attach", self.desktop, self.desktop_folder, "--writable")

    def make_bindle_with(self, name, *flags):
        code, out = self.run_cli("new", name, "--at", self.tmp / f"bindle-{name}", *flags)
        self.assertEqual(code, 0, out)
        return self.tmp / f"bindle-{name}"

    def branch(self, repo):
        return bindle.git(repo, "rev-parse", "--abbrev-ref", "HEAD")

    def hook(self, bindle_root, folder, script):
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(bindle_root), "CLAUDE_PROJECT_DIR": str(folder)}
        return subprocess.run([sys.executable, str(bindle_root / "hooks/bindle_hook.py"), script.replace(".sh", "")],
                              env=env, capture_output=True, text=True)

    # The point of sync: a memory saved on one machine is there at the next session on the other.
    def test_a_memory_saved_on_one_machine_reaches_the_other(self):
        (self.laptop / "memory/fact.md").write_text("ion cannon ready\n")
        self.assertEqual(self.hook(self.laptop, self.laptop_folder, "session-end.sh").returncode, 0)
        self.hook(self.desktop, self.desktop_folder, "session-start.sh")
        self.assertEqual((self.desktop / "memory/fact.md").read_text(), "ion cannon ready\n")

    # A pushed secret can't be taken back, so a suspicious memory must never be committed.
    def test_refuses_to_commit_a_memory_that_looks_like_a_secret(self):
        head = bindle.git(self.laptop, "rev-parse", "HEAD")
        (self.laptop / "memory/oops.md").write_text("api_key: abcdefghijklmnopqrstuvwx123456\n")
        r = self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.assertEqual(r.returncode, 0)
        self.assertIn("possible secret", r.stderr)
        self.assertEqual(bindle.git(self.laptop, "rev-parse", "HEAD"), head)
        code, out = self.run_cli("doctor", self.laptop_folder)
        self.assertEqual(code, 1)
        self.assertIn("memory/oops.md may hold a secret", out)

    # The outbox syncs too, so items prepared on one machine can be collected on another.
    def test_outbox_changes_sync_with_memories(self):
        (self.laptop / "outbox/item").mkdir(parents=True)
        (self.laptop / "outbox/item/memory.md").write_text("general lesson\n")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.assertIn("outbox/item/memory.md", bindle.git(self.remote, "log", "--name-only", "--format="))

    # Both machines add a memory between syncs, so both append to MEMORY.md; the union merge keeps both lines
    # instead of stopping the rebase and leaving one machine's memory unpushed.
    def test_index_lines_added_on_two_machines_both_survive(self):
        for root, folder, n in ((self.laptop, self.laptop_folder, "a"), (self.desktop, self.desktop_folder, "b")):
            (root / f"memory/{n}.md").write_text(f"{n}\n")
            with open(root / "memory/MEMORY.md", "a") as f:
                f.write(f"- [{n}]({n}.md) — from {n}\n")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.hook(self.desktop, self.desktop_folder, "session-end.sh")
        self.hook(self.laptop, self.laptop_folder, "session-start.sh")
        index = (self.laptop / "memory/MEMORY.md").read_text()
        self.assertIn("from a", index)
        self.assertIn("from b", index)
        self.assertEqual(bindle.git(self.desktop, "rev-list", "--count", "@{upstream}..HEAD"), "0")

    # Skills and rules are deliberate commits; auto-sync must not ship half-finished work.
    def test_commits_only_memory(self):
        (self.laptop / "memory/fact.md").write_text("x\n")
        (self.laptop / "skills/draft.md").write_text("half done\n")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.assertIn("skills/draft.md", bindle.git(self.laptop, "status", "--porcelain"))
        self.assertNotIn("draft.md", bindle.git(self.remote, "log", "--name-only", "--format="))

    # A session only writes to its writable bindle, so a read-only one has nothing of its own to push.
    def test_session_end_does_nothing_where_the_bindle_is_read_only(self):
        f = self.folder("elsewhere")
        self.run_cli("attach", self.laptop, f)
        (self.laptop / "memory/fact.md").write_text("x\n")
        self.hook(self.laptop, f, "session-end.sh")
        self.assertIn("memory/fact.md", bindle.git(self.laptop, "status", "--porcelain"))

    def test_does_nothing_when_sync_is_off(self):
        meta = json.loads((self.laptop / "bindle.json").read_text())
        meta["sync"] = False
        (self.laptop / "bindle.json").write_text(json.dumps(meta))
        (self.laptop / "memory/fact.md").write_text("x\n")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.assertIn("memory/fact.md", bindle.git(self.laptop, "status", "--porcelain"))

    # Offline or unreachable remotes must never fail or block a session.
    def test_an_unreachable_remote_never_fails_the_hooks(self):
        subprocess.run(["git", "-C", str(self.laptop), "remote", "set-url", "origin", str(self.tmp / "gone.git")], check=True)
        (self.laptop / "memory/fact.md").write_text("x\n")
        end = self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        start = self.hook(self.laptop, self.laptop_folder, "session-start.sh")
        self.assertEqual((end.returncode, start.returncode), (0, 0))
        self.assertNotIn("Traceback", end.stderr + start.stderr)
        self.assertIn("1 commit(s) not pushed", self.run_cli("doctor", self.laptop_folder)[1])

    # A session killed before SessionEnd leaves commits behind; the next start pushes them.
    def test_session_start_pushes_leftover_commits(self):
        (self.laptop / "memory/fact.md").write_text("x\n")
        bindle.git(self.laptop, "add", "-A")
        bindle.git(self.laptop, "commit", "-q", "-m", "left behind")
        self.hook(self.laptop, self.laptop_folder, "session-start.sh")
        self.assertIn("left behind", bindle.git(self.remote, "log", "--format=%s"))

    def test_bindle_sync_does_the_same_by_hand_even_with_sync_off(self):
        meta = json.loads((self.laptop / "bindle.json").read_text())
        meta["sync"] = False
        (self.laptop / "bindle.json").write_text(json.dumps(meta))
        bindle.git(self.laptop, "commit", "-qam", "sync off")
        (self.laptop / "memory/fact.md").write_text("x\n")
        code, out = self.run_cli("sync", self.laptop_folder)
        self.assertEqual(code, 0)
        self.assertIn("pushed", out)
        self.assertIn("memory/fact.md", bindle.git(self.remote, "log", "--name-only", "--format="))


if __name__ == "__main__":
    unittest.main()
