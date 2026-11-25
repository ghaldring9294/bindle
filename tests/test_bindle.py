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
import bindle.global_rules  # noqa: E402


def git_bash():
    """The bash Claude Code runs hooks with: Git Bash on Windows (not WSL's bash.exe, which comes first on PATH)."""
    if os.name == "nt":
        for p in (Path(os.environ.get("ProgramFiles", r"C:\\Program Files")) / "Git" / "bin" / "bash.exe",):
            if p.exists():
                return str(p)
    return "bash"


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
            "BINDLE_HOME": str(self.tmp / "bindles"),  # never the real ~/bindles
            "BINDLE_UPDATE_CHECK": "off",  # never fetch from the network; ReleaseCheckTest covers it against a local remote
            "CLAUDE_CONFIG_DIR": str(self.tmp / "claude-config"),  # never the real user CLAUDE.md
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
        return json.loads((folder / ".claude" / "settings.local.json").read_text(encoding="utf-8"))

    def claude_calls(self):
        return self.log.read_text(encoding="utf-8").splitlines() if self.log.exists() else []


class NewTest(BindleTest):
    def test_scaffolds_a_plugin_shaped_bindle_named_throughout(self):
        b = self.make_bindle("acme")
        self.assertEqual(json.loads((b / "bindle.json").read_text(encoding="utf-8")), {"name": "acme", "layout": 1, "sync": False, "audience": "private", "writes": "implicit",
                                                                   "bindle_version": bindle.core.VERSION})
        self.assertEqual(json.loads((b / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))["name"], "acme")
        self.assertEqual(json.loads((b / ".claude-plugin/marketplace.json").read_text(encoding="utf-8"))["name"], "bindle-acme")
        for d in ["memory", "notes", "projects", "skills", "commands", "agents"]:
            self.assertTrue((b / d).is_dir(), d)
        self.assertNotIn("{{name}}", "".join(p.read_text(encoding="utf-8") for p in b.rglob("*") if p.is_file() and ".git" not in p.parts))

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


class OwnFolderTest(BindleTest):
    # Attaching another bindle to a bindle's own folder (sp read-only in craft, to read real patterns while writing
    # general skills) writes that bindle's paths and name there; the bindle's repo must never commit them.
    def test_a_bindle_ignores_attach_settings_in_its_own_folder(self):
        craft, sp = self.make_bindle("craft"), self.make_bindle("sp")
        self.run_cli("attach", sp, craft)
        # Without the person's global excludes, which may happen to cover it: the bindle's own .gitignore must.
        status = bindle.git(craft, "-c", "core.excludesFile=" + os.devnull, "status", "--porcelain")
        self.assertNotIn(".claude", status or "")


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
        self.assertIn("/.bindle/", (repo / ".git/info/exclude").read_text(encoding="utf-8"))
        self.assertFalse((repo / ".gitignore").exists())

    def test_new_outside_a_repo_touches_nothing_else(self):
        self.make_bindle("acme")
        self.assertFalse((self.tmp / ".git").exists())

    def test_doctor_flags_a_bindle_the_repo_would_commit(self):
        repo = self.project_repo()
        self.run_cli("new", "acme", "--at", repo / ".bindle")
        (repo / ".git/info/exclude").write_text("", encoding="utf-8")
        self.run_cli("attach", repo / ".bindle", repo, "--writable")
        code, out = self.run_cli("doctor", repo)
        self.assertEqual(code, 1)
        self.assertIn("not ignored there", out)

    def test_doctor_flags_a_bindle_the_repo_already_tracks(self):
        repo = self.project_repo()
        self.run_cli("new", "acme", "--at", repo / ".bindle")
        (repo / ".git/info/exclude").write_text("", encoding="utf-8")
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
        (repo / ".git/info/exclude").write_text("", encoding="utf-8")
        rmtree(repo / ".bindle/.git")
        meta = json.loads((repo / ".bindle/bindle.json").read_text(encoding="utf-8"))
        meta["demo"] = True
        (repo / ".bindle/bindle.json").write_text(json.dumps(meta), encoding="utf-8")
        bindle.git(repo, "add", "-A")
        self.run_cli("attach", repo / ".bindle", repo)
        code, out = self.run_cli("doctor", repo)
        self.assertEqual(code, 0, out)


class NotesTest(BindleTest):
    def test_scratch_notes_are_ignored_but_their_readme_is_kept(self):
        b = self.make_bindle("acme")
        self.assertIn("notes/scratch/README.md", bindle.git(b, "ls-files"))
        (b / "notes/scratch/dump.txt").write_text("throwaway\n", encoding="utf-8")
        self.assertEqual(bindle.git(b, "status", "--porcelain"), "")

    def test_doctor_flags_a_secret_in_a_note(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        (b / "notes/logins.md").write_text("api_key = abcdefghijklmnopqrstuvwx\n", encoding="utf-8")
        code, out = self.run_cli("doctor", f)
        self.assertEqual(code, 1)
        self.assertIn("notes/logins.md may hold a secret; move it to secure storage", out)

    # Ignored files never leave the machine; flagging them would only be noise.
    def test_doctor_ignores_secrets_in_files_git_ignores(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        (b / "notes/scratch/tmp.md").write_text("token: abcdefghijklmnopqrstuvwx\n", encoding="utf-8")
        self.assertEqual(self.run_cli("doctor", f)[0], 0)

    def test_upgrade_adds_missing_ignore_rules_without_touching_the_bindles_own(self):
        b = self.make_bindle("acme")
        (b / ".gitignore").write_text("*.out\n", encoding="utf-8")
        (b / ".gitattributes").unlink()
        (b / "notes/scratch/README.md").unlink()  # made before these existed: never in its history
        bindle.git(b, "add", "-A"); bindle.git(b, "commit", "-q", "--amend", "-m", "an old bindle")
        self.run_cli("upgrade", b)
        ignore = (b / ".gitignore").read_text(encoding="utf-8")
        self.assertTrue(ignore.startswith("*.out\n"))
        self.assertIn("notes/scratch/*", ignore)
        self.assertIn("merge=union", (b / ".gitattributes").read_text(encoding="utf-8"))
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

    # Typing a bindle's full path on every attach is the friction this removes.
    def test_a_bare_name_finds_the_bindle_in_bindle_home(self):
        self.run_cli("new", "craft", "--at", self.tmp / "bindles" / "craft")
        f = self.folder()
        self.assertEqual(self.run_cli("attach", "craft", f)[0], 0)
        self.assertEqual(self.settings(f)["extraKnownMarketplaces"]["bindle-craft"]["source"]["path"],
                         str(self.tmp / "bindles" / "craft"))

    # A path that exists means what it says, even if a bindle with that name is in the home folder.
    def test_an_existing_path_wins_over_a_name_in_bindle_home(self):
        self.run_cli("new", "craft", "--at", self.tmp / "bindles" / "craft")
        here = self.tmp / "work" / "craft"
        self.run_cli("new", "craft", "--at", here)
        f = self.folder()
        cwd = os.getcwd()
        os.chdir(here.parent)
        try:
            self.assertEqual(self.run_cli("attach", "craft", f)[0], 0)
        finally:
            os.chdir(cwd)
        self.assertEqual(self.settings(f)["extraKnownMarketplaces"]["bindle-craft"]["source"]["path"], str(here))

    def test_an_unknown_name_says_where_it_looked(self):
        code, out = self.run_cli("attach", "nope", self.folder())
        self.assertEqual(code, 1)
        self.assertIn(str(self.tmp / "bindles"), out)
        self.assertIn("BINDLE_HOME", out)

    def test_bindle_home_defaults_to_bindles_in_the_home_folder(self):
        saved = {k: os.environ.get(k) for k in ("BINDLE_HOME", "HOME", "USERPROFILE")}
        os.environ.pop("BINDLE_HOME")
        os.environ["HOME"] = os.environ["USERPROFILE"] = str(self.tmp)  # USERPROFILE is Path.home() on Windows
        try:
            self.assertEqual(bindle.core.bindles_home(), self.tmp / "bindles")
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)

    # detach keeps the marketplace declaration, so a bindle moved after detaching was declared at its old
    # path; attaching from the new path must re-point it, or the install looks in an empty folder.
    def test_attach_after_detach_and_move_uses_the_new_path(self):
        b, f = self.make_bindle("craft"), self.folder()
        self.run_cli("attach", b, f)
        self.run_cli("detach", "craft", f)
        moved = self.tmp / "bindles" / "craft"
        moved.parent.mkdir(exist_ok=True)
        b.rename(moved)
        code, out = self.run_cli("attach", "craft", f)
        self.assertEqual(code, 0, out)
        s = self.settings(f)
        self.assertEqual(s["extraKnownMarketplaces"]["bindle-craft"]["source"]["path"], str(moved))
        self.assertTrue(s["enabledPlugins"]["craft@bindle-craft"])
        self.assertEqual(s["permissions"]["deny"], bindle.core.lock_rules(moved))

    def test_attaching_twice_doesnt_call_claude_again(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f)
        calls = len(self.claude_calls())
        self.run_cli("attach", b, f)
        self.assertEqual(len(self.claude_calls()), calls)

    # Claude Code reads settings.local.json at the repo root, so attaching to a subfolder of a
    # repo would silently configure the whole repo instead.
    @unittest.skipIf(os.name == "nt", "on Windows, Claude Code reads settings in the launch folder, so a subfolder is fine")
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
        self.assertEqual(self.deny(f), [f"Edit(/{bindle.core.rule_path(b)}/**)"])

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
        (f / ".claude/settings.local.json").write_text(json.dumps({"permissions": {"deny": ["Bash(rm -rf:*)"]}}), encoding="utf-8")
        self.run_cli("attach", b, f)
        self.run_cli("detach", "personal", f)
        self.assertEqual(self.deny(f), ["Bash(rm -rf:*)"])

    def test_doctor_flags_an_unlocked_read_only_bindle(self):
        b, f = self.make_bindle("personal"), self.folder()
        self.run_cli("attach", b, f)
        s = self.settings(f)
        del s["permissions"]
        (f / ".claude/settings.local.json").write_text(json.dumps(s), encoding="utf-8")
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
        (acme / "rules.md").write_text("Use Acme's ticket prefix.\n", encoding="utf-8")
        (personal / "rules.md").write_text("Prefer small PRs.\n", encoding="utf-8")
        self.run_cli("attach", acme, f, "--writable")
        self.run_cli("attach", personal, f)
        self.assertIn("Use Acme's ticket prefix.", self.run_rules(acme, f))
        self.assertIn("Follow them as you would CLAUDE.md", self.run_rules(acme, f))
        self.assertIn("Prefer small PRs.", self.run_rules(personal, f))

    # Past the hook cap, Claude Code shows only the first 2,000 characters and the rest is silently lost.
    def test_doctor_flags_rules_too_long_for_the_hook(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        (b / "rules.md").write_text("x" * (bindle.RULES_LIMIT + 1), encoding="utf-8")
        code, out = self.run_cli("doctor", f)
        self.assertEqual(code, 1)
        self.assertIn("rules.md is over", out)


class ReposTest(BindleTest):
    """A session started in a repo reads only that repo's settings, so a domain attach alone leaves it without
    the bindle and writing memories to Claude Code's default folder instead of the domain's."""

    def domain(self):
        d = self.folder("acme-work")
        for name in ("web", "api"):
            (d / name).mkdir()
            subprocess.run(["git", "init", "-q", str(d / name)], check=True)
        (d / "docs").mkdir()  # not a repo
        return d

    def test_attach_repos_makes_the_bindle_writable_in_every_repo(self):
        b, d = self.make_bindle("acme"), self.domain()
        self.assertEqual(self.run_cli("attach", b, d, "--writable", "--repos")[0], 0)
        for f in (d, d / "web", d / "api"):
            self.assertEqual(self.settings(f)["autoMemoryDirectory"], str(b / "memory"), f)
        self.assertFalse((d / "docs" / ".claude").exists())

    # A half-applied attach would leave some repos writing to one bindle and some to another.
    def test_a_writable_conflict_in_one_repo_changes_nothing(self):
        acme, personal, d = self.make_bindle("acme"), self.make_bindle("personal"), self.domain()
        self.run_cli("attach", personal, d / "web", "--writable")
        code, out = self.run_cli("attach", acme, d, "--writable", "--repos")
        self.assertEqual(code, 1)
        self.assertIn("one writable bindle", out)
        self.assertFalse((d / ".claude").exists())
        self.assertFalse((d / "api" / ".claude").exists())

    # The trust warning is about the bindle, not the folder; repeated once per repo it gets skimmed.
    def test_the_trust_warning_shows_once_across_repos(self):
        b, d = self.make_bindle("craft"), self.domain()
        (b / ".mcp.json").write_text("{}\n", encoding="utf-8")
        code, out = self.run_cli("attach", b, d, "--repos")
        self.assertEqual(code, 0, out)
        self.assertEqual(out.count("runs code on this machine"), 1, out)

    # A command that names the bindle reads (and pastes) better than a long path; the name must find this bindle.
    def test_doctors_fix_names_the_bindle(self):
        b, d = self.make_bindle("acme"), self.domain()
        self.run_cli("attach", b, d, "--writable")
        self.assertIn(f"bindle attach acme {d} --writable --repos", self.run_cli("doctor", d)[1])

    # A bindle repo in the domain folder holds its own memory; making acme writable there would mix domains.
    def test_attach_repos_skips_bindles_inside_the_folder(self):
        d = self.domain()
        craft = self.make_bindle("craft")
        shutil.move(str(craft), str(d / "craft"))
        acme = self.make_bindle("acme")
        self.run_cli("attach", acme, d, "--writable", "--repos")
        self.assertFalse((d / "craft" / ".claude" / "settings.local.json").exists())

    # A malformed settings file found partway through would otherwise leave some folders attached and some not.
    def test_bad_settings_in_one_repo_changes_nothing(self):
        b, d = self.make_bindle("acme"), self.domain()
        (d / "web" / ".claude").mkdir()
        (d / "web" / ".claude" / "settings.local.json").write_text("{not json", encoding="utf-8")
        code, out = self.run_cli("attach", b, d, "--repos")
        self.assertEqual(code, 1)
        self.assertIn("isn't valid JSON", out)
        self.assertFalse((d / ".claude").exists())
        self.assertFalse((d / "api" / ".claude").exists())

    # Given a path, detach must still leave alone the repos that never had the bindle (no stray settings file).
    def test_detach_repos_by_path_leaves_other_repos_untouched(self):
        b, d = self.make_bindle("acme"), self.domain()
        self.run_cli("attach", b, d / "web", "--writable")
        self.assertEqual(self.run_cli("detach", b, d, "--repos")[0], 0)
        self.assertNotIn("autoMemoryDirectory", self.settings(d / "web"))
        self.assertFalse((d / "api" / ".claude").exists())

    # A bindle that moved leaves dead settings in every repo; detach must clear them all, not only the domain folder.
    def test_detach_repos_clears_a_moved_bindle_from_every_repo(self):
        b, d = self.make_bindle("acme"), self.domain()
        self.run_cli("attach", b, d, "--writable", "--repos")
        shutil.move(str(b), str(self.tmp / "elsewhere"))
        self.assertEqual(self.run_cli("detach", "acme", d, "--repos")[0], 0)
        for f in (d, d / "web", d / "api"):
            self.assertNotIn("bindle-acme", self.settings(f).get("extraKnownMarketplaces", {}), f)
            self.assertNotIn("autoMemoryDirectory", self.settings(f), f)

    # Without the warning, memories from repo sessions silently go to Claude Code's default folder, not the domain.
    def test_doctor_names_repos_that_would_miss_the_domain_and_the_fix_clears_it(self):
        b, d = self.make_bindle("acme"), self.domain()
        self.run_cli("attach", b, d, "--writable")
        code, out = self.run_cli("doctor", d)
        self.assertEqual(code, 0, out)  # a warning: launching only from the domain folder is fine
        self.assertIn("api, web won't load acme", out)
        self.assertIn("--writable --repos", out)
        self.run_cli("attach", b, d, "--writable", "--repos")
        self.assertNotIn("won't load", self.run_cli("doctor", d)[1])

    # --repos refuses when a repo writes to another bindle, so the suggested fix must not be one that fails.
    def test_a_repo_writing_elsewhere_is_left_alone_and_the_fix_names_each_repo(self):
        acme, personal, d = self.make_bindle("acme"), self.make_bindle("personal"), self.domain()
        self.run_cli("attach", acme, d, "--writable")
        self.run_cli("attach", personal, d / "web", "--writable")
        out = self.run_cli("doctor", d)[1]
        self.assertIn("api won't load acme", out)
        self.assertNotIn("--repos", out)
        self.assertIn(f"{d / 'api'} --writable", out)

    def test_doctor_is_quiet_about_repos_when_the_folder_has_no_writable_bindle(self):
        b, d = self.make_bindle("craft"), self.domain()
        self.run_cli("attach", b, d)
        self.assertNotIn("won't load", self.run_cli("doctor", d)[1])

    def test_detach_repos_turns_it_off_everywhere_and_skips_repos_without_it(self):
        b, d = self.make_bindle("acme"), self.domain()
        self.run_cli("attach", b, d, "--writable")
        self.run_cli("attach", b, d / "web", "--writable")
        self.assertEqual(self.run_cli("detach", "acme", d, "--repos")[0], 0)
        for f in (d, d / "web"):
            self.assertNotIn("autoMemoryDirectory", self.settings(f), f)
        self.assertFalse((d / "api" / ".claude").exists())


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
        with open(b / "hooks/bindle_hook.py", "a", encoding="utf-8") as h:
            h.write("# local edit\n")
        code, out = self.run_cli("doctor", f)
        self.assertEqual(code, 1)
        self.assertIn("bindle_hook.py differs", out)
        self.assertIn("bindle upgrade acme", out)  # by name: attach registered it
        self.assertNotIn("&& git -C", out)

    # Unsaved memories are the main way work gets lost between machines.
    def test_reports_uncommitted_memories_and_a_missing_remote(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        (b / "memory" / "fact.md").write_text("x", encoding="utf-8")
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

    # Without terms, promotion's leak check passes everything, so a new domain bindle should say so.
    def test_warns_when_the_writable_bindle_has_no_private_terms(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        code, out = self.run_cli("doctor", f)
        self.assertEqual(code, 0, out)  # a warning, not a problem: a personal bindle may have nothing private
        self.assertIn("private-terms.txt lists no terms", out)
        with open(b / "private-terms.txt", "a", encoding="utf-8") as t:
            t.write("Acme\n")
        self.assertNotIn("private-terms.txt lists no terms", self.run_cli("doctor", f)[1])

    # Promotion leaves from the writable bindle, so a read-only one without terms isn't worth a warning.
    def test_no_terms_warning_for_a_read_only_bindle(self):
        b, f = self.make_bindle("craft"), self.folder()
        self.run_cli("attach", b, f)
        self.assertNotIn("private-terms.txt", self.run_cli("doctor", f)[1])

    # A half-done hand rename leaves the three names disagreeing; attach and detach then fail confusingly.
    def test_flags_names_that_disagree(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f)
        self.assertNotIn("make the names agree", self.run_cli("doctor", f)[1])
        plugin = b / ".claude-plugin/plugin.json"
        plugin.write_text(plugin.read_text(encoding="utf-8").replace('"acme"', '"acme2"'), encoding="utf-8")
        code, out = self.run_cli("doctor", f)
        self.assertEqual(code, 1)
        self.assertIn("plugin.json has name 'acme2'", out)

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

    def test_installs_the_cli_on_path(self):
        self.assertEqual(self.run_cli("install")[0], 0)
        if bindle.core.WINDOWS:
            self.assertIn(str(bindle.BASE / "bin" / "bindle"), (self.home / ".local/bin/bindle.cmd").read_text(encoding="utf-8"))
        else:
            self.assertEqual(os.readlink(self.home / ".local/bin/bindle"), str(bindle.BASE / "bin/bindle"))
        self.assertFalse((self.home / ".claude/commands/bindle.md").exists(),
                         "install no longer links commands; the plugin provides them")

    def test_installing_twice_is_fine(self):
        self.run_cli("install")
        self.assertEqual(self.run_cli("install")[0], 0)

    # A real file there is the person's own; replacing it would lose their work.
    def test_refuses_to_replace_a_real_file(self):
        (self.home / ".local/bin").mkdir(parents=True)
        (self.home / ".local/bin/bindle").write_text("mine", encoding="utf-8")
        self.assertEqual(self.run_cli("install")[0], 1)
        self.assertEqual((self.home / ".local/bin/bindle").read_text(encoding="utf-8"), "mine")

    def link(self, dest, target):
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            dest.symlink_to(target)
        except OSError:
            self.skipTest("symlinks aren't available")

    # The plugin move emptied global/, so the old links dangle; if cleanup misses them, /bindle stays a dead link.
    def test_cleanup_removes_old_links_whose_target_is_gone(self):
        cmd, skill = self.home / ".claude/commands/bindle.md", self.home / ".claude/skills/bindle-promote"
        self.link(cmd, self.tmp / "old/global/commands/bindle.md")
        self.link(skill, self.tmp / "old/global/skills/bindle-promote")
        self.assertEqual(self.run_cli("install", "--cleanup")[0], 0)
        self.assertFalse(cmd.is_symlink() or skill.is_symlink())

    # A link the person made there themselves is theirs; cleanup must not delete it.
    def test_cleanup_keeps_a_link_bindle_didnt_make(self):
        cmd = self.home / ".claude/commands/bindle.md"
        self.link(cmd, self.tmp / "mine/bindle.md")
        self.run_cli("install", "--cleanup")
        self.assertTrue(cmd.is_symlink())

    # Adding bindle's marketplace looks like an install but isn't; without a warning, /bindle is just missing.
    def test_doctor_warns_when_bindles_plugin_isnt_installed(self):
        f = self.folder()
        self.assertIn("claude plugin install bindle@bindle", self.run_cli("doctor", f)[1])
        (self.home / ".claude").mkdir(exist_ok=True)
        (self.home / ".claude/settings.json").write_text(json.dumps({"enabledPlugins": {"bindle@bindle": True}}), encoding="utf-8")
        self.assertNotIn("bindle@bindle", self.run_cli("doctor", f)[1])

    def test_doctor_points_old_links_to_cleanup(self):
        self.link(self.home / ".claude/commands/bindle.md", self.tmp / "old/global/commands/bindle.md")
        self.assertIn("bindle install --cleanup", self.run_cli("doctor", self.folder())[1])


class NewerFilesTest(BindleTest):
    """A bindle upgraded on another machine by a newer bindle looks "drifted" to an older copy here; upgrading
    from here would put the old hooks back, and sync would spread the downgrade to every machine."""

    def test_an_older_bindle_refuses_to_upgrade_and_says_to_pull_instead(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        meta = json.loads((b / "bindle.json").read_text(encoding="utf-8")); meta["bindle_version"] = "99.0.0"
        (b / "bindle.json").write_text(json.dumps(meta), encoding="utf-8")
        with open(b / "hooks/run", "a", encoding="utf-8") as fh:
            fh.write("# from bindle 99\n")
        newer = (b / "hooks/run").read_text(encoding="utf-8")
        code, out = self.run_cli("doctor", f)
        self.assertIn("newer than this copy", out)
        self.assertNotIn("bindle upgrade acme", out)
        other = self.make_bindle("zeta")  # sorts after acme: a skip mustn't stop the rest
        with open(other / "hooks/run", "a", encoding="utf-8") as fh:
            fh.write("# drifted\n")
        code, out = self.run_cli("upgrade", "--all")
        self.assertNotEqual(code, 0)  # skipping is reported, not silent
        self.assertEqual((b / "hooks/run").read_text(encoding="utf-8"), newer)
        self.assertEqual((other / "hooks/run").read_bytes(), (bindle.TEMPLATE / "hooks/run").read_bytes())
        self.assertIn("were upgraded by a newer bindle elsewhere", self.run_cli("session-check", f)[1])

    def test_upgrade_records_the_version_that_wrote_the_files(self):
        b = self.make_bindle("acme")
        with open(b / "hooks/run", "a", encoding="utf-8") as fh:
            fh.write("# drifted\n")
        self.run_cli("upgrade", b)
        self.assertEqual(json.loads((b / "bindle.json").read_text(encoding="utf-8"))["bindle_version"], bindle.core.VERSION)


class McpLaunchTest(unittest.TestCase):
    # Claude Code starts MCP servers from the system PATH (cmd.exe on Windows), not Git Bash, and Git for
    # Windows doesn't put bash on PATH: a command of "bash" there means the bindle tools never load and
    # /bindle:onboard can't call them. bin/py must run on its own (shebang, exec bit) and have a Windows twin.
    def test_mcp_server_starts_without_bash_on_path(self):
        cfg = json.loads((bindle.BASE / ".mcp.json").read_text(encoding="utf-8"))["mcpServers"]["bindle"]
        self.assertEqual(cfg["command"], "${CLAUDE_PLUGIN_ROOT}/bin/py")
        self.assertTrue((bindle.BASE / "bin" / "py.cmd").is_file(), "no bin/py.cmd for Windows to find through PATHEXT")
        self.assertTrue((bindle.BASE / "bin" / "py").read_text(encoding="utf-8").startswith("#!"))
        mode = subprocess.run(["git", "-C", str(bindle.BASE), "ls-files", "-s", "bin/py"],
                              capture_output=True, text=True).stdout.split()
        if mode:  # in a git checkout: the exec bit is what lets macOS and Linux run bin/py directly
            self.assertEqual(mode[0], "100755")

    @unittest.skipUnless(os.name == "nt", "cmd.exe only")
    def test_mcp_server_answers_initialize_through_cmd(self):
        init = json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05", "capabilities": {}, "clientInfo": {"name": "t", "version": "0"}}})
        root = str(bindle.BASE)
        out = subprocess.run(f'cmd /d /s /c "{root}/bin/py {root}/bin/bindle-server"', input=init + "\n",
                             capture_output=True, text=True, timeout=30).stdout
        self.assertIn('"serverInfo"', out)

class SecretShapesTest(unittest.TestCase):
    # The check runs in a 20s session-start hook; one long line (a hash, a minified blob) once took 40s.
    def test_a_long_line_is_checked_quickly(self):
        import time
        hook = bindle.core.hooks()
        started = time.time()
        hook.looks_secret("A" * 40000)
        self.assertLess(time.time() - started, 1)

    # A file saved as UTF-16 hid any secret in it from a byte-oriented check.
    def test_a_utf16_file_is_checked_like_any_other(self):
        hook = bindle.core.hooks()
        self.assertTrue(hook.looks_secret(hook.as_text("api_key = abcdefghijklmnop1234".encode("utf-16"))))


class TemplateSecretTest(BindleTest):
    # Sync's secret check reads every file a push sends, bindle's own included; a template file that looked like
    # a credential would block sync for everyone after each upgrade.
    def test_no_template_file_looks_like_a_secret(self):
        hook = bindle.core.hooks()
        for f in bindle.TEMPLATE.rglob("*"):
            if f.is_file() and "__pycache__" not in f.parts:
                self.assertFalse(hook.looks_secret(f.read_bytes().decode("utf-8", errors="ignore")), f)


class ReleaseCheckTest(BindleTest):
    """Nobody runs `git pull` in bindle unprompted, so a fix that shipped never arrives. The check must also never
    make a session wait on the network, or fetch at every start."""

    def test_a_new_tag_is_fetched_in_the_background_once_a_day_and_named(self):
        from bindle import commands
        origin, clone = self.tmp / "origin", self.tmp / "clone"
        subprocess.run(["git", "init", "-q", str(origin)], check=True)
        subprocess.run(["git", "-C", str(origin), "commit", "-q", "--allow-empty", "-m", "first"], check=True)
        subprocess.run(["git", "-C", str(origin), "tag", "v0.0.1"], check=True)
        subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
        self.assertIsNone(commands.newer_release(clone))  # an older tag isn't an update
        subprocess.run(["git", "-C", str(origin), "tag", "v99.0.0"], check=True)
        self.assertIsNone(commands.newer_release(clone))  # not fetched yet: nothing local says so
        fetch = commands.refresh_tags(clone)
        self.assertIsNotNone(fetch)
        self.assertEqual(fetch.wait(timeout=30), 0)
        self.assertEqual(commands.newer_release(clone), "99.0.0")
        self.assertIsNone(commands.refresh_tags(clone))  # fetched today: no second fetch


class UpdateTest(InstallTest):
    """`bindle update` is the one step people remember; it must pull bindle safely and leave every bindle current."""

    def clone_pair(self):
        origin, clone = self.tmp / "origin", self.tmp / "clone"
        subprocess.run(["git", "init", "-q", str(origin)], check=True)
        (origin / "f.txt").write_text("1\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(origin), "add", "-A"], check=True)
        subprocess.run(["git", "-C", str(origin), "commit", "-qm", "one"], check=True)
        subprocess.run(["git", "clone", "-q", str(origin), str(clone)], check=True)
        return origin, clone

    # Pulling bindle must never merge over someone's own edits to it.
    def test_pull_fast_forwards_a_clean_clone_and_refuses_a_dirty_one(self):
        from bindle import upgrade
        origin, clone = self.clone_pair()
        (origin / "f.txt").write_text("2\n", encoding="utf-8")
        subprocess.run(["git", "-C", str(origin), "commit", "-qam", "two"], check=True)
        self.assertTrue(upgrade.pull_bindle(clone))
        self.assertEqual((clone / "f.txt").read_text(encoding="utf-8"), "2\n")
        self.assertFalse(upgrade.pull_bindle(clone))  # nothing new
        (clone / "f.txt").write_text("mine\n", encoding="utf-8")
        with self.assertRaises(bindle.core.BindleError):
            upgrade.pull_bindle(clone)
        self.assertEqual((clone / "f.txt").read_text(encoding="utf-8"), "mine\n")

    # The first thing update says is whether bindle itself changed; buffered, it once came out after everything else.
    def test_update_reports_its_own_pull_before_the_upgrade_output(self):
        self.make_bindle("acme")
        script = ("import sys; sys.path.insert(0, sys.argv[1]); from bindle import upgrade, cli; "
                  "upgrade.pull_bindle = lambda repo: False; sys.exit(cli.main(['update']))")
        out = subprocess.run([sys.executable, "-c", script, str(bindle.BASE)], capture_output=True, text=True,
                             env=os.environ).stdout
        self.assertTrue(out.startswith("bindle: already up to date"), out)

    # After the pull: the install is refreshed, every bindle is upgraded, and pushing stays the person's call
    # unless they pass --push.
    def test_after_the_pull_it_upgrades_every_bindle_and_pushes_only_when_asked(self):
        b = self.make_bindle("acme")
        remote = self.tmp / "acme.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(b), str(remote)], check=True)
        bindle.git(b, "remote", "add", "origin", str(remote))
        bindle.git(b, "push", "-q", "-u", "origin", "HEAD")
        with open(b / "hooks/run", "a", encoding="utf-8") as f:
            f.write("# older\n")
        bindle.git(b, "commit", "-qam", "older hook"); bindle.git(b, "push", "-q")
        head = bindle.git(remote, "rev-parse", "HEAD")
        code, out = self.run_cli("update", "--after-pull")
        self.assertEqual(code, 0, out)
        self.assertEqual((b / "hooks/run").read_bytes(), (bindle.TEMPLATE / "hooks/run").read_bytes())
        self.assertIn(f"git -C {b} push", out)
        self.assertEqual(bindle.git(remote, "rev-parse", "HEAD"), head)  # not pushed without --push
        with open(b / "hooks/run", "a", encoding="utf-8") as f:
            f.write("# older again\n")
        bindle.git(b, "commit", "-qam", "older again")
        code, out = self.run_cli("update", "--after-pull", "--push")
        self.assertEqual(code, 0, out)
        self.assertEqual(bindle.git(remote, "rev-parse", "HEAD"), bindle.git(b, "rev-parse", "HEAD"))


class UpdatePullsFirstTest(InstallTest):
    """Two machines share a bindle. If each upgrades its own copy, they make competing commits of the same change and
    neither can pull the other's; so update pulls each bindle first and upgrades only one that's current."""

    def setUp(self):
        super().setUp()
        self.laptop = self.make_bindle("acme")
        self.remote = self.tmp / "acme.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(self.laptop), str(self.remote)], check=True)
        bindle.git(self.laptop, "remote", "add", "origin", str(self.remote))
        bindle.git(self.laptop, "push", "-q", "-u", "origin", "HEAD")
        with open(self.laptop / "hooks/run", "a", encoding="utf-8") as f:
            f.write("# older\n")
        bindle.git(self.laptop, "commit", "-qam", "older hook"); bindle.git(self.laptop, "push", "-q")
        self.pc_home = self.tmp / "pc-bindles"
        self.pc_home.mkdir()
        self.pc = self.pc_home / "acme"
        subprocess.run(["git", "clone", "-q", str(self.remote), str(self.pc)], check=True)

    def update_on_pc(self):
        os.environ["BINDLE_HOME"] = str(self.pc_home)
        try:
            return self.run_cli("update", "--after-pull", "--push")
        finally:
            os.environ["BINDLE_HOME"] = self.env["BINDLE_HOME"]

    def test_a_second_machine_takes_the_upgrade_instead_of_making_its_own(self):
        self.assertEqual(self.run_cli("update", "--after-pull", "--push")[0], 0)
        upgraded = bindle.git(self.remote, "rev-parse", "HEAD")
        code, out = self.update_on_pc()
        self.assertEqual(code, 0, out)
        self.assertEqual(bindle.git(self.pc, "rev-parse", "HEAD"), upgraded)
        self.assertEqual(bindle.git(self.remote, "rev-parse", "HEAD"), upgraded)  # no competing commit
        self.assertEqual((self.pc / "hooks/run").read_bytes(), (bindle.TEMPLATE / "hooks/run").read_bytes())

    def test_a_bindle_that_cant_be_brought_up_to_date_isnt_upgraded(self):
        self.run_cli("update", "--after-pull", "--push")
        (self.pc / "notes" / "pc.md").write_text("pc only\n", encoding="utf-8")
        bindle.git(self.pc, "add", "-A"); bindle.git(self.pc, "commit", "-qm", "pc note")  # diverged from the remote
        code, out = self.update_on_pc()
        self.assertEqual(code, 1)
        self.assertIn("acme: not upgraded", out)
        self.assertNotEqual((self.pc / "hooks/run").read_bytes(), (bindle.TEMPLATE / "hooks/run").read_bytes())

    # An uncommitted edit is someone's work in progress: a pull that would overwrite it must stop, leave it exactly
    # as it was, and skip the upgrade; an edit the pull doesn't touch is kept and doesn't block anything.
    def test_uncommitted_changes_are_kept_and_one_the_pull_would_overwrite_stops_the_upgrade(self):
        (self.laptop / "rules.md").write_text("Laptop rule.\n", encoding="utf-8")
        bindle.git(self.laptop, "commit", "-qam", "laptop rule"); bindle.git(self.laptop, "push", "-q")
        (self.pc / "rules.md").write_text("PC draft, not committed.\n", encoding="utf-8")
        code, out = self.update_on_pc()
        self.assertEqual(code, 1)
        self.assertIn("acme: not upgraded", out)
        self.assertEqual((self.pc / "rules.md").read_text(encoding="utf-8"), "PC draft, not committed.\n")
        (self.pc / "rules.md").write_text((self.laptop / "rules.md").read_text(encoding="utf-8"), encoding="utf-8")  # resolved by hand
        bindle.git(self.pc, "checkout", "-q", "--", "rules.md")
        (self.pc / "notes" / "draft.md").write_text("unrelated, not committed\n", encoding="utf-8")
        code, out = self.update_on_pc()
        self.assertEqual(code, 0, out)
        self.assertEqual((self.pc / "notes" / "draft.md").read_text(encoding="utf-8"), "unrelated, not committed\n")
        self.assertEqual((self.pc / "rules.md").read_text(encoding="utf-8"), "Laptop rule.\n")


class SessionCheckTest(InstallTest):
    """A session started in a repo inside a domain folder reads only that repo's settings; without a warning, its
    memories silently go to Claude Code's default folder instead of the domain's bindle."""

    def setUp(self):
        super().setUp()
        self.acme = self.make_bindle("acme")
        self.domain = self.folder("acme-work")
        for name in ("web", "api"):
            subprocess.run(["git", "init", "-q", str(self.domain / name)], check=True)
        self.run_cli("attach", self.acme, self.domain, "--writable")

    def user_settings(self):
        return json.loads((self.home / ".claude" / "settings.json").read_text(encoding="utf-8"))

    def hook(self, cwd):
        """Runs the installed hook command the way Claude Code does: through bash, with the session's JSON on stdin."""
        command = self.user_settings()["hooks"]["SessionStart"][-1]["hooks"][0]["command"]
        return subprocess.run([git_bash(), "-c", command], input=json.dumps({"cwd": str(cwd)}),
                              capture_output=True, text=True, env=os.environ)

    # ~/.claude/settings.json is the person's own; bindle may add its one hook but must leave the rest exactly.
    def test_install_adds_one_hook_and_removing_it_leaves_everything_else(self):
        (self.home / ".claude").mkdir()
        mine = {"model": "opus", "hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": "echo mine"}]}]}}
        (self.home / ".claude" / "settings.json").write_text(json.dumps(mine), encoding="utf-8")
        self.run_cli("install", "--session-check")
        self.run_cli("install", "--session-check")  # again: still one
        groups = self.user_settings()["hooks"]["SessionStart"]
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0], mine["hooks"]["SessionStart"][0])
        self.run_cli("install", "--no-session-check")
        self.assertEqual(self.user_settings(), mine)

    def test_plain_install_never_touches_user_settings(self):
        self.run_cli("install")
        self.assertFalse((self.home / ".claude" / "settings.json").exists())

    def test_the_hook_warns_in_a_repo_without_the_bindle_and_the_fix_quiets_it(self):
        self.run_cli("install", "--session-check")
        out = self.hook(self.domain / "web")
        self.assertEqual(out.returncode, 0, out.stderr)
        message = json.loads(out.stdout)["systemMessage"]
        self.assertIn("won't load acme", message)
        self.assertIn(f"bindle attach acme {self.domain / 'web'} --writable", message)
        self.run_cli("attach", "acme", self.domain / "web", "--writable")
        self.assertEqual(self.hook(self.domain / "web").stdout, "")

    # Folders outside any domain stay silent, or the warning becomes noise people learn to skip.
    def test_silent_outside_domains_in_the_domain_itself_and_after_detach(self):
        self.run_cli("install", "--session-check")
        self.assertEqual(self.hook(self.folder("downloads")).stdout, "")
        self.assertEqual(self.hook(self.domain).stdout, "")
        self.run_cli("detach", "acme", self.domain)
        self.assertEqual(self.hook(self.domain / "web").stdout, "")

    # A hook that errors would show up in every session; a broken settings file is the person's to fix, not a crash.
    def test_a_broken_settings_file_keeps_the_hook_quiet(self):
        self.run_cli("install", "--session-check")
        (self.domain / "web" / ".claude").mkdir()
        (self.domain / "web" / ".claude" / "settings.local.json").write_text("{not json", encoding="utf-8")
        out = self.hook(self.domain / "web")
        self.assertEqual((out.returncode, out.stdout), (0, ""))

    # After `git pull` in bindle, every bindle keeps running its old hooks until upgraded; people forget that step.
    def test_every_session_names_bindles_due_for_an_upgrade_until_upgraded(self):
        self.run_cli("install", "--session-check")
        with open(self.acme / "hooks/run", "a", encoding="utf-8") as f:
            f.write("# older copy\n")
        message = json.loads(self.hook(self.folder("downloads")).stdout)["systemMessage"]
        self.assertIn("bindle: acme needs an upgrade; bindle upgrade --all", message)
        self.run_cli("upgrade", "--all")
        self.assertEqual(self.hook(self.folder("downloads")).stdout, "")

    # Writable attaches made before domains were recorded are invisible to the check until attached again.
    def test_doctor_asks_for_a_reattach_when_the_domain_isnt_recorded(self):
        self.run_cli("install", "--session-check")
        registry = self.tmp / "bindles" / "registry.json"
        data = json.loads(registry.read_text(encoding="utf-8"))
        data.pop("domains")
        registry.write_text(json.dumps(data), encoding="utf-8")
        self.assertIn("doesn't know", self.run_cli("doctor", self.domain)[1])
        self.run_cli("attach", self.acme, self.domain, "--writable")
        self.assertNotIn("doesn't know", self.run_cli("doctor", self.domain)[1])


class OnboardingPromptTest(BindleTest):
    """A fresh user with no bindles gets a nudge toward /bindle:onboard; once any bindle exists, it's gone."""

    def test_session_check_offers_onboarding_when_no_bindles_exist(self):
        out = self.run_cli("session-check", self.folder())[1]
        self.assertIn("/bindle:onboard", out)

    def test_onboarding_line_disappears_once_a_bindle_exists(self):
        self.make_bindle("craft")
        out = self.run_cli("session-check", self.folder())[1]
        self.assertNotIn("/bindle:onboard", out)


def all_options(parser, prefix=""):
    """(command, --option) for every subcommand, nested ones included (outbox add)."""
    import argparse
    for action in parser._actions:
        if isinstance(action, argparse._SubParsersAction):
            for name, sub in action.choices.items():
                yield from all_options(sub, f"{prefix} {name}".strip())
        elif prefix and action.help != argparse.SUPPRESS:  # hidden options are internal, not for docs
            for option in action.option_strings:
                if option.startswith("--") and option != "--help":
                    yield prefix, option


def example_commands(text):
    """`bindle ...` commands inside fenced code blocks, split at && and ; (placeholders like <folder> are fine)."""
    import re
    for block in re.findall(r"```[^\n]*\n(.*?)```", text, re.S):
        for line in block.splitlines():
            for part in re.split(r"&&|;", line):
                part = part.strip()
                if part.startswith("bindle ") or part == "bindle":
                    yield part


class DocsTest(unittest.TestCase):
    # The README is how people learn the commands; a command it doesn't list is one nobody finds.
    def test_readme_lists_every_command(self):
        readme = (bindle.BASE / "README.md").read_text(encoding="utf-8")
        parser_cmds = ["install", "new", "attach", "detach", "doctor", "sync", "update", "upgrade", "outbox add", "outbox list", "collect", "terms", "outbox clean", "outbox remove", "list", "promote", "session-check", "global"]
        import argparse
        sub = next(a for a in bindle.build_parser()._actions if isinstance(a, argparse._SubParsersAction))
        self.assertEqual(sorted(sub.choices), sorted({c.split()[0] for c in parser_cmds}))
        for c in parser_cmds:
            self.assertIn(f"`bindle {c}", readme, c)

    # AGENTS.md is how an agent finds its way around this repo; a module or script it doesn't name gets
    # reimplemented or missed, and a path that no longer exists sends it looking in the wrong place.
    def test_agents_md_names_every_module_and_script_and_only_real_paths(self):
        import re
        agents = (bindle.BASE / "AGENTS.md").read_text(encoding="utf-8")
        named = set(re.findall(r"`([^`]+)`", agents))
        for module in (bindle.BASE / "bindle").glob("*.py"):
            if module.name != "__init__.py":
                self.assertTrue({module.name, f"bindle/{module.name}"} & named, f"AGENTS.md doesn't name {module.name}")
        for script in (bindle.BASE / "bin").iterdir():
            if script.is_file():
                self.assertIn(f"bin/{script.name}", named, f"AGENTS.md doesn't name bin/{script.name}")
        for term in named:
            # Paths in this repo: a top-level part that exists here (memory/ and notes/ describe a bindle, not this repo).
            if "/" in term and " " not in term and not term.startswith(("~", ".", "/")) \
                    and (bindle.BASE / term.split("/")[0]).exists():
                self.assertTrue((bindle.BASE / term).exists(), f"AGENTS.md names {term}, which doesn't exist")
            elif term.endswith(".py") and "/" not in term:
                self.assertTrue((bindle.BASE / "bindle" / term).exists(), f"AGENTS.md names {term}, which doesn't exist")

    # An option that the README doesn't mention is one people never use. The /bindle command uses MCP tool
    # args (not --option format), so it's checked separately above.
    def test_every_option_is_in_the_readme(self):
        readme = (bindle.BASE / "README.md").read_text(encoding="utf-8")
        missing = [f"README.md doesn't mention `bindle {command} {option}`"
                   for command, option in all_options(bindle.build_parser())
                   if option not in readme]
        self.assertEqual(missing, [])

    # Example commands are what people and agents copy; one the CLI no longer accepts fails at the worst moment.
    # The /bindle command and promote skill use MCP tools now, not CLI syntax, so they aren't checked here.
    def test_every_example_command_parses(self):
        import shlex
        files = ["README.md", "MIGRATION.md"]
        for rel in files:
            for line in example_commands((bindle.BASE / rel).read_text(encoding="utf-8")):
                with self.subTest(file=rel, line=line):
                    err = io.StringIO()
                    try:
                        with contextlib.redirect_stderr(err):
                            bindle.build_parser().parse_args(shlex.split(line, comments=True)[1:])
                    except SystemExit:
                        error = err.getvalue().strip().splitlines()[-1]
                        # A template like `--kind memory|skill|note` or `--kind …` names a real option with a placeholder value.
                        if "invalid choice" in error and any(c in error.split("'")[1] for c in "|…<"):
                            continue
                        self.fail(f"{rel}: `{line}` doesn't parse: {error}")

    # People read the changelog to decide whether to run `bindle upgrade`; a release without its entry hides that.
    def test_the_newest_changelog_entry_is_this_version(self):
        changelog = (bindle.BASE / "CHANGELOG.md").read_text(encoding="utf-8")
        newest = next(line for line in changelog.splitlines() if line.startswith("## "))
        self.assertTrue(newest.startswith(f"## {bindle.VERSION} "), f"{newest!r} isn't version {bindle.VERSION}")

    # Typing `bindle` alone is how people discover the commands; an error there is a dead end.
    def test_bare_bindle_prints_every_command(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            self.assertEqual(bindle.main([]), 0)
        for c in ("attach", "detach", "list", "doctor", "outbox", "collect", "terms"):
            self.assertIn(c, out.getvalue())

    # /bindle is what Claude reads to operate bindle for someone; an operation missing there is one Claude
    # guesses at or doesn't know to offer. MCP tools cover most commands; install and session-check are CLI-only.
    def test_the_bindle_command_tells_claude_every_operation(self):
        guide = (bindle.BASE / "commands" / "bindle.md").read_text(encoding="utf-8")
        import argparse
        sub = next(a for a in bindle.build_parser()._actions if isinstance(a, argparse._SubParsersAction))
        mcp_tool_names = {"list", "doctor", "attach", "detach", "new", "sync", "update", "upgrade",
                          "promote", "terms", "collect", "global"}
        cli_only = {"install", "session-check"}
        for c in sub.choices:
            if c == "outbox":
                for sub_cmd in ("add", "list", "clean", "remove"):
                    self.assertIn(f"outbox_{sub_cmd}", guide, f"outbox_{sub_cmd}")
            elif c in mcp_tool_names:
                self.assertIn(f"**{c}**", guide, c)
            elif c in cli_only:
                self.assertIn(f"`bindle {c}", guide, c)
            else:
                self.fail(f"command {c!r} not accounted for in MCP tools or CLI-only")


class UpgradeTest(BindleTest):
    """Base updates reach existing bindles only through upgrade, since each bindle carries its own copies."""

    def test_brings_a_drifted_or_old_bindle_up_to_date_and_commits(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f)
        (b / "hooks/bindle_hook.py").write_text("# old\n", encoding="utf-8")
        (b / "hooks/lib.sh").write_text("# obsolete\n", encoding="utf-8")
        (b / "AGENTS.md").unlink()  # made before AGENTS.md existed: never in its history
        bindle.git(b, "add", "-A")
        bindle.git(b, "commit", "-q", "--amend", "-m", "an old bindle")
        self.assertEqual(bindle.git(b, "rev-list", "--count", "HEAD"), "1")
        self.assertEqual(self.run_cli("upgrade", b)[0], 0)
        self.assertEqual((b / "hooks/bindle_hook.py").read_bytes(), (bindle.TEMPLATE / "hooks/bindle_hook.py").read_bytes())
        self.assertFalse((b / "hooks/lib.sh").exists())
        self.assertIn("acme bindle", (b / "AGENTS.md").read_text(encoding="utf-8"))
        self.assertEqual(bindle.git(b, "status", "--porcelain"), "")
        self.assertEqual(self.run_cli("doctor", f)[0], 0)

    # Upgrade owns only its files; a person's own edits must stay theirs.
    def test_never_overwrites_or_commits_the_bindles_own_files(self):
        b = self.make_bindle("acme")
        (b / "README.md").write_text("my readme\n", encoding="utf-8")
        (b / "memory/fact.md").write_text("unsaved\n", encoding="utf-8")
        (b / "hooks/bindle_hook.py").write_text("# old\n", encoding="utf-8")
        self.run_cli("upgrade", b)
        self.assertEqual((b / "README.md").read_text(encoding="utf-8"), "my readme\n")
        status = bindle.git(b, "status", "--porcelain")
        self.assertIn("README.md", status)
        self.assertIn("memory/fact.md", status)
        self.assertNotIn("bindle_hook.py", status)

    def test_dry_run_changes_nothing(self):
        b = self.make_bindle("acme")
        (b / "hooks/bindle_hook.py").write_text("# old\n", encoding="utf-8")
        code, out = self.run_cli("upgrade", b, "--dry-run")
        self.assertIn("update hooks/bindle_hook.py", out)
        self.assertEqual((b / "hooks/bindle_hook.py").read_text(encoding="utf-8"), "# old\n")

    def test_an_up_to_date_bindle_gets_no_commit(self):
        b = self.make_bindle("acme")
        head = bindle.git(b, "rev-parse", "HEAD")
        _, out = self.run_cli("upgrade", b)
        self.assertIn("up to date", out)
        self.assertEqual(bindle.git(b, "rev-parse", "HEAD"), head)

    def test_refuses_a_bindle_from_a_newer_version(self):
        b = self.make_bindle("acme")
        meta = json.loads((b / "bindle.json").read_text(encoding="utf-8"))
        meta["layout"] = bindle.LAYOUT + 1
        (b / "bindle.json").write_text(json.dumps(meta), encoding="utf-8")
        code, out = self.run_cli("upgrade", b)
        self.assertEqual(code, 1)
        self.assertIn("Run bindle update", out)

    # The fix for a bindle with a remote includes the push, so the other machines get it too.
    def test_doctor_offers_a_copy_paste_fix_that_pushes(self):
        b, f = self.make_bindle("craft"), self.folder()
        remote = self.tmp / "craft.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(b), str(remote)], check=True)
        bindle.git(b, "remote", "add", "origin", str(remote)); bindle.git(b, "fetch", "-q", "origin")
        bindle.git(b, "branch", "-q", "-u", "origin/" + bindle.git(b, "rev-parse", "--abbrev-ref", "HEAD"))
        self.run_cli("attach", b, f)
        (b / "hooks/bindle_hook.py").write_text("# old\n", encoding="utf-8")
        (b / "hooks/hooks.json").write_text("{}\n", encoding="utf-8")
        _, out = self.run_cli("doctor", f)
        self.assertIn(f"bindle upgrade craft && git -C {bindle.commands.quote(b)} push", out)
        self.assertEqual(out.count("bindle upgrade craft"), 1)

    def test_upgrades_every_bindle_attached_to_the_current_folder(self):
        acme, personal, f = self.make_bindle("acme"), self.make_bindle("personal"), self.folder()
        self.run_cli("attach", acme, f, "--writable")
        self.run_cli("attach", personal, f)
        for b in (acme, personal):
            (b / "hooks/bindle_hook.py").write_text("# old\n", encoding="utf-8")
        cwd = os.getcwd()
        os.chdir(f)
        try:
            self.run_cli("upgrade")
        finally:
            os.chdir(cwd)
        for b in (acme, personal):
            self.assertEqual((b / "hooks/bindle_hook.py").read_bytes(), (bindle.TEMPLATE / "hooks/bindle_hook.py").read_bytes())


class UpgradeKeepsDeletionsTest(BindleTest):
    # Someone who deleted rules.md or a README they didn't want shouldn't find it back after every upgrade.
    def test_a_template_file_deleted_on_purpose_stays_deleted(self):
        b = self.make_bindle("acme")
        (b / "rules.md").unlink()
        bindle.git(b, "commit", "-qam", "no rules here")
        with open(b / "hooks/run", "a", encoding="utf-8") as fh:
            fh.write("# drifted\n")
        self.run_cli("upgrade", b)
        self.assertFalse((b / "rules.md").exists())


class UpgradeAllTest(BindleTest):
    # With several bindles, upgrading each by path after every bindle release is the chore the registry removes.
    def test_all_upgrades_home_and_registered_bindles(self):
        self.run_cli("new", "craft", "--at", self.tmp / "bindles" / "craft")
        self.run_cli("new", "acme", "--at", self.tmp / "acme" / ".bindle")
        for root in (self.tmp / "bindles" / "craft", self.tmp / "acme" / ".bindle"):
            with open(root / "hooks/bindle_hook.py", "a", encoding="utf-8") as h:
                h.write("# stale\n")
        code, out = self.run_cli("upgrade", "--all")
        self.assertEqual(code, 0, out)
        for root in (self.tmp / "bindles" / "craft", self.tmp / "acme" / ".bindle"):
            self.assertNotIn("# stale", (root / "hooks/bindle_hook.py").read_text(encoding="utf-8"))

    def test_all_and_a_path_together_is_refused(self):
        self.assertEqual(self.run_cli("upgrade", "--all", self.tmp)[0], 1)


class SyncAllTest(BindleTest):
    # Several bindles, several remotes: one command should bring every one up to date and save every memory.
    def test_all_pulls_every_bindle_and_pushes_memories_only_where_sessions_write(self):
        roots = {"acme": self.tmp / "acme" / ".bindle", "craft": self.tmp / "bindles" / "craft"}
        self.run_cli("new", "acme", "--at", roots["acme"])
        self.run_cli("new", "craft", "--at", roots["craft"], "--writes", "explicit")
        for name, root in roots.items():
            remote = self.tmp / f"{name}-remote.git"
            bindle.git(self.tmp, "clone", "-q", "--bare", str(root), str(remote))
            bindle.git(root, "remote", "add", "origin", str(remote))
            bindle.git(root, "fetch", "-q", "origin")
            bindle.git(root, "branch", "-q", "-u", "origin/" + bindle.git(root, "rev-parse", "--abbrev-ref", "HEAD"))
            (root / "memory" / "fact.md").write_text("a fact\n", encoding="utf-8")
        code, out = self.run_cli("sync", "--all")
        self.assertEqual(code, 0, out)
        self.assertEqual(bindle.git(roots["acme"], "status", "--porcelain"), "")  # committed
        self.assertEqual(bindle.git(roots["acme"], "rev-list", "--count", "@{upstream}..HEAD"), "0")  # pushed
        self.assertIn("memory/fact.md", bindle.git(roots["craft"], "status", "--porcelain"))  # explicit: untouched

    def test_all_and_a_folder_together_is_refused(self):
        self.assertEqual(self.run_cli("sync", "--all", self.folder())[0], 1)


class PromotionTest(BindleTest):
    """Material crosses between bindles only as reviewed, general text, through the source's outbox."""

    def setUp(self):
        super().setUp()
        self.acme = self.make_bindle("acme")
        self.personal = self.make_bindle("personal")
        (self.acme / "private-terms.txt").write_text("# terms\nAcme\nACME-\nwidgetd\n", encoding="utf-8")
        bindle.git(self.acme, "commit", "-qam", "terms")
        self.draft = self.tmp / "draft.md"
        self.draft.write_text("---\nname: small-prs\ndescription: keep PRs small\ntype: feedback\nboundary: craft\n---\nKeep PRs small.\n", encoding="utf-8")

    def add(self, *extra):
        return self.run_cli("outbox", "add", self.acme, self.draft, "--name", "small-prs", "--description", "keep PRs small", *extra)

    def test_an_approved_memory_reaches_the_target_with_an_index_line(self):
        self.assertEqual(self.add()[0], 0)
        code, out = self.run_cli("collect", self.acme, "--into", self.personal, "--items", "small-prs")
        self.assertEqual(code, 0, out)
        self.assertIn("Keep PRs small.", (self.personal / "memory/small-prs.md").read_text(encoding="utf-8"))
        self.assertIn("(small-prs.md) — keep PRs small", (self.personal / "memory/MEMORY.md").read_text(encoding="utf-8"))
        self.assertFalse((self.acme / "outbox/small-prs").exists())  # delivered: the outbox holds only what's waiting
        self.assertEqual(bindle.git(self.personal, "status", "--porcelain"), "")
        self.assertEqual(bindle.git(self.acme, "status", "--porcelain"), "")

    # Collected items pile up otherwise; they're already in the target and in git history.
    # Before 0.14, collect left delivered items in the outbox marked "collected"; clean removes those.
    def test_clean_removes_collected_items_and_keeps_waiting_ones(self):
        self.add()
        item = self.acme / "outbox/small-prs/item.json"
        item.write_text(json.dumps({**json.loads(item.read_text(encoding="utf-8")), "status": "collected", "collected_into": ["personal"]}), encoding="utf-8")
        bindle.git(self.acme, "commit", "-qam", "an item collected by an older bindle")
        self.draft.write_text("Name things for what they do.\n", encoding="utf-8")
        self.run_cli("outbox", "add", self.acme, self.draft, "--name", "naming")
        self.assertIn("would remove small-prs", self.run_cli("outbox", "clean", self.acme, "--dry-run")[1])
        self.assertTrue((self.acme / "outbox/small-prs").exists())
        code, out = self.run_cli("outbox", "clean", self.acme)
        self.assertEqual(code, 0, out)
        self.assertFalse((self.acme / "outbox/small-prs").exists())
        self.assertTrue((self.acme / "outbox/naming").exists())  # not collected yet: still waiting
        self.assertNotIn("outbox/small-prs", bindle.git(self.acme, "status", "--porcelain"))  # removal committed

    # Approving isn't final: a person who changes their mind needs a way to drop an item before it's collected.
    def test_remove_drops_a_named_item_even_if_not_collected(self):
        self.add()
        code, out = self.run_cli("outbox", "remove", self.acme, "--items", "small-prs")
        self.assertEqual(code, 0, out)
        self.assertFalse((self.acme / "outbox/small-prs").exists())
        self.assertNotIn("outbox/", bindle.git(self.acme, "status", "--porcelain"))

    def test_remove_refuses_an_unknown_item_and_removes_nothing(self):
        self.add()
        code, out = self.run_cli("outbox", "remove", self.acme, "--items", "small-prs,typo")
        self.assertEqual(code, 1)
        self.assertIn("no item typo", out)
        self.assertTrue((self.acme / "outbox/small-prs").exists())

    # With several domains, what's waiting to be promoted is spread over many outboxes; one view finds it.
    def test_list_all_shows_every_outbox_with_items(self):
        globex = self.tmp / "globex" / ".bindle"
        self.run_cli("new", "globex", "--at", globex)  # registered
        self.run_cli("outbox", "add", globex, self.draft, "--name", "small-prs")
        self.run_cli("new", "craft", "--at", self.tmp / "bindles" / "craft")  # empty outbox: not shown
        code, out = self.run_cli("outbox", "list", "--all")
        self.assertEqual(code, 0, out)
        self.assertIn("globex (", out)
        self.assertIn("small-prs: memory, approved", out)
        self.assertNotIn("craft", out)

    # Naming an item that hasn't reached its target yet must not delete the only reviewed copy.
    def test_clean_refuses_a_named_item_not_yet_collected(self):
        self.add()
        code, out = self.run_cli("outbox", "clean", self.acme, "--items", "small-prs")
        self.assertEqual(code, 1)
        self.assertIn("hasn't been collected", out)
        self.assertTrue((self.acme / "outbox/small-prs").exists())

    # Promotion is one step when the target is here: approve, and it's in the other bindle.
    def test_promote_places_the_draft_in_the_target_in_one_step(self):
        code, out = self.run_cli("promote", self.acme, self.draft, "--into", self.personal,
                                 "--name", "small-prs", "--description", "keep PRs small")
        self.assertEqual(code, 0, out)
        self.assertIn("Keep PRs small.", (self.personal / "memory/small-prs.md").read_text(encoding="utf-8"))
        self.assertIn("(small-prs.md) — keep PRs small", (self.personal / "memory/MEMORY.md").read_text(encoding="utf-8"))
        self.assertEqual(bindle.git(self.personal, "status", "--porcelain"), "")  # committed in the target
        self.assertFalse((self.acme / "outbox/small-prs").exists())  # nothing left waiting
        self.assertEqual(bindle.git(self.acme, "status", "--porcelain"), "")  # source untouched

    # A reminder for another domain belongs in its notes, not its memory, and must not replace earlier ones.
    def test_a_note_is_appended_to_the_targets_inbox_with_where_it_came_from(self):
        note = self.tmp / "note.md"
        for slug, text in (("invoice", "Send the March invoice.\n"), ("call-back", "Call back about the renewal.\n")):
            note.write_text(text, encoding="utf-8")
            code, out = self.run_cli("promote", self.acme, note, "--into", self.personal, "--kind", "note", "--name", slug)
            self.assertEqual(code, 0, out)
        inbox = (self.personal / "notes/inbox.md").read_text(encoding="utf-8")
        self.assertEqual(inbox.count("## "), 2)
        self.assertIn("from acme · invoice", inbox)
        self.assertIn("Send the March invoice.", inbox)
        self.assertIn("Call back about the renewal.", inbox)
        self.assertNotIn("invoice", (self.personal / "memory/MEMORY.md").read_text(encoding="utf-8") if (self.personal / "memory/MEMORY.md").exists() else "")
        self.assertEqual(bindle.git(self.personal, "status", "--porcelain"), "")

    # A note is text written in the source's session, so it's the likeliest way for the source's specifics to leak.
    def test_a_note_naming_the_source_domain_is_refused(self):
        note = self.tmp / "note.md"
        note.write_text("Tell them how widgetd does retries.\n", encoding="utf-8")
        code, out = self.run_cli("promote", self.acme, note, "--into", self.personal, "--kind", "note", "--name", "retries")
        self.assertEqual(code, 1)
        self.assertFalse((self.personal / "notes/inbox.md").exists())

    # The target may be on another machine; the note waits in the outbox and is delivered there.
    def test_a_waiting_note_is_delivered_by_collect(self):
        note = self.tmp / "note.md"
        note.write_text("Renew the domain.\n", encoding="utf-8")
        self.run_cli("outbox", "add", self.acme, note, "--kind", "note", "--name", "renew")
        code, out = self.run_cli("collect", self.acme, "--into", self.personal, "--items", "renew")
        self.assertEqual(code, 0, out)
        self.assertIn("Renew the domain.", (self.personal / "notes/inbox.md").read_text(encoding="utf-8"))
        self.assertFalse((self.acme / "outbox/renew").exists())

    # The same guard as the outbox: a draft that still names the source domain never reaches another bindle.
    def test_promote_refuses_a_draft_naming_the_domain_and_writes_nothing(self):
        self.draft.write_text("Keep PRs small, like we do on widgetd.\n", encoding="utf-8")
        code, out = self.run_cli("promote", self.acme, self.draft, "--into", self.personal, "--name", "small-prs")
        self.assertEqual(code, 1)
        self.assertIn("widgetd", out)
        self.assertFalse((self.personal / "memory/small-prs.md").exists())

    # The check is for ourselves: a named term is a prompt to think, and the person can decide it's fine.
    def test_a_private_term_can_be_allowed_on_purpose_but_only_that_term(self):
        self.draft.write_text("Keep PRs small, like Acme does on widgetd.\n", encoding="utf-8")
        code, out = self.run_cli("promote", self.acme, self.draft, "--into", self.personal, "--name", "small-prs")
        self.assertEqual(code, 1)
        self.assertIn("--allow <term>", out)
        code, out = self.run_cli("promote", self.acme, self.draft, "--into", self.personal, "--name", "small-prs", "--allow", "acme")
        self.assertEqual(code, 1)  # widgetd is still listed and not allowed
        self.assertIn("widgetd", out)
        code, out = self.run_cli("promote", self.acme, self.draft, "--into", self.personal, "--name", "small-prs",
                                 "--allow", "acme", "--allow", "widgetd")
        self.assertEqual(code, 0, out)

    # A secret in git history can't be taken back, so it stays a hard stop whatever is allowed.
    def test_a_possible_secret_cannot_be_allowed(self):
        self.draft.write_text("token = ghp_" + "a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8" + "\n", encoding="utf-8")
        code, out = self.run_cli("promote", self.acme, self.draft, "--into", self.personal, "--name", "tok",
                                 "--allow", "possible secret")
        self.assertEqual(code, 1)
        self.assertIn("password manager or vault", out)
        self.assertFalse((self.personal / "memory/tok.md").exists())

    # An item's own record of allowed terms is a claim any file write can make, so collect needs the person's
    # --allow again; outbox add prints the collect command with it, so the approved item still goes through.
    def test_terms_allowed_at_approval_must_be_allowed_again_at_collect(self):
        self.draft.write_text("Keep PRs small, like Acme does.\n", encoding="utf-8")
        code, out = self.run_cli("outbox", "add", self.acme, self.draft, "--name", "small-prs", "--allow", "Acme")
        self.assertEqual(code, 0, out)
        self.assertIn("--items small-prs --allow Acme", out)
        code, out = self.run_cli("collect", self.acme, "--into", self.personal, "--items", "small-prs")
        self.assertEqual(code, 1)
        self.assertIn("--allow <term>", out)
        code, out = self.run_cli("collect", self.acme, "--into", self.personal, "--items", "small-prs", "--allow", "Acme")
        self.assertEqual(code, 0, out)
        self.assertIn("Keep PRs small, like Acme does.", out)  # the person sees exactly what crossed

    def test_promote_never_overwrites_something_in_the_target(self):
        (self.personal / "memory/small-prs.md").write_text("mine\n", encoding="utf-8")
        code, _ = self.run_cli("promote", self.acme, self.draft, "--into", self.personal, "--name", "small-prs")
        self.assertEqual(code, 1)
        self.assertEqual((self.personal / "memory/small-prs.md").read_text(encoding="utf-8"), "mine\n")

    # Improving a craft skill while using it in another domain is the natural moment; --replace allows it, on purpose only.
    def test_replace_updates_a_memory_without_a_second_index_line(self):
        self.run_cli("promote", self.acme, self.draft, "--into", self.personal, "--name", "small-prs", "--description", "keep PRs small")
        self.draft.write_text("---\nname: small-prs\ndescription: keep PRs small\ntype: feedback\nboundary: craft\n---\nKeep PRs small and focused.\n", encoding="utf-8")
        code, out = self.run_cli("promote", self.acme, self.draft, "--into", self.personal, "--name", "small-prs", "--replace")
        self.assertEqual(code, 0, out)
        self.assertIn("small and focused", (self.personal / "memory/small-prs.md").read_text(encoding="utf-8"))
        self.assertEqual((self.personal / "memory/MEMORY.md").read_text(encoding="utf-8").count("(small-prs.md)"), 1)
        self.assertEqual(bindle.git(self.personal, "status", "--porcelain"), "")
        self.assertIn("small and focused", bindle.git(self.personal, "show", "HEAD"))  # the update is its own commit

    # A file the new version of a skill dropped must not linger from the old one.
    def test_replace_swaps_a_whole_skill_folder(self):
        skill = self.tmp / "review" ; skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: review\ndescription: x\n---\nv1\n", encoding="utf-8")
        (skill / "old.md").write_text("gone in v2\n", encoding="utf-8")
        self.run_cli("promote", self.acme, skill, "--into", self.personal, "--kind", "skill", "--name", "review")
        (skill / "old.md").unlink()
        (skill / "SKILL.md").write_text("---\nname: review\ndescription: x\n---\nv2\n", encoding="utf-8")
        self.assertEqual(self.run_cli("promote", self.acme, skill, "--into", self.personal, "--kind", "skill", "--name", "review", "--replace")[0], 0)
        self.assertIn("v2", (self.personal / "skills/review/SKILL.md").read_text(encoding="utf-8"))
        self.assertFalse((self.personal / "skills/review/old.md").exists())

    # The person approves an update by seeing what changes; --dry-run gives Claude the exact diff to show.
    def test_dry_run_shows_the_diff_and_writes_nothing(self):
        self.run_cli("promote", self.acme, self.draft, "--into", self.personal, "--name", "small-prs")
        self.draft.write_text(self.draft.read_text(encoding="utf-8").replace("Keep PRs small.", "Keep PRs tiny."), encoding="utf-8")
        code, out = self.run_cli("promote", self.acme, self.draft, "--into", self.personal, "--name", "small-prs", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("-Keep PRs small.", out)
        self.assertIn("+Keep PRs tiny.", out)
        self.assertIn("Keep PRs small.", (self.personal / "memory/small-prs.md").read_text(encoding="utf-8"))

    # The replacement still crosses the boundary, so it's checked like a first promotion.
    def test_replace_is_still_leak_checked(self):
        self.run_cli("promote", self.acme, self.draft, "--into", self.personal, "--name", "small-prs")
        self.draft.write_text("Keep PRs small, as on widgetd.\n", encoding="utf-8")
        self.assertEqual(self.run_cli("promote", self.acme, self.draft, "--into", self.personal, "--name", "small-prs", "--replace")[0], 1)
        self.assertNotIn("widgetd", (self.personal / "memory/small-prs.md").read_text(encoding="utf-8"))

    def test_promote_finds_the_target_by_name(self):
        self.run_cli("new", "craft", "--at", self.tmp / "bindles" / "craft", "--writes", "explicit")
        code, out = self.run_cli("promote", self.acme, self.draft, "--into", "craft", "--name", "small-prs")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.tmp / "bindles/craft/memory/small-prs.md").exists())

    # Every command takes a bindle the same way; a source that only worked as a path tripped up the demo walkthrough.
    def test_promote_and_the_outbox_take_the_source_by_name(self):
        name = bindle.core.load_bindle(self.acme)["name"]
        code, out = self.run_cli("promote", name, self.draft, "--into", self.personal, "--name", "small-prs")
        self.assertEqual(code, 0, out)
        self.assertTrue((self.personal / "memory/small-prs.md").exists())
        code, out = self.run_cli("outbox", "add", name, self.draft, "--name", "tiny-prs")
        self.assertEqual(code, 0, out)
        self.assertIn(f"bindle collect {name} --into", out)  # the hint names it too

    # The leak check is the structural guard: a draft that still names the domain never enters the outbox.
    def test_a_draft_naming_the_domain_is_refused(self):
        self.draft.write_text("Keep PRs small, like we do on widgetd.\n", encoding="utf-8")
        code, out = self.add()
        self.assertEqual(code, 1)
        self.assertIn("widgetd", out)
        self.assertFalse((self.acme / "outbox/small-prs").exists())

    def test_terms_match_whole_words_case_insensitively(self):
        self.draft.write_text("Ticket ACME-123 taught us this.\n", encoding="utf-8")
        self.assertEqual(self.add()[0], 1)
        self.draft.write_text("Acmeological reasoning is fine.\n", encoding="utf-8")
        self.assertEqual(self.add()[0], 0)

    def test_a_ticket_prefix_term_matches_ticket_keys(self):
        (self.acme / "private-terms.txt").write_text("PROJ-\n", encoding="utf-8")
        self.draft.write_text("Fixed in PROJ-4512.\n", encoding="utf-8")
        self.assertEqual(self.add()[0], 1)

    def test_a_draft_that_looks_like_a_secret_is_refused(self):
        self.draft.write_text("token: abcdefghijklmnopqrstuvwxyz123456\n", encoding="utf-8")
        code, out = self.add()
        self.assertEqual(code, 1)
        self.assertIn("possible secret", out)

    # The outbox could be edited after approval; collect checks again at the moment of crossing.
    def test_collect_rechecks_an_outbox_item_edited_after_approval(self):
        self.add()
        (self.acme / "outbox/small-prs/memory.md").write_text("Edited later to mention Acme.\n", encoding="utf-8")
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
        code, out = self.run_cli("collect", self.acme, "--into", self.personal, "--items", "small-prs")
        self.assertEqual(code, 1)  # delivered items leave the outbox, so there's nothing to deliver twice
        self.assertIn("Not in acme's outbox", out)
        lines = [l for l in (self.personal / "memory/MEMORY.md").read_text(encoding="utf-8").splitlines() if "small-prs" in l]
        self.assertEqual(len(lines), 1)

    def test_a_skill_moves_as_a_folder(self):
        skill = self.tmp / "review-checklist"
        skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: review-checklist\ndescription: x\n---\nCheck tests first.\n", encoding="utf-8")
        self.assertEqual(self.run_cli("outbox", "add", self.acme, skill, "--kind", "skill", "--name", "review-checklist")[0], 0)
        self.assertEqual(self.run_cli("collect", self.acme, "--into", self.personal, "--items", "review-checklist")[0], 0)
        self.assertIn("Check tests first.", (self.personal / "skills/review-checklist/SKILL.md").read_text(encoding="utf-8"))

    def test_never_overwrites_something_already_in_the_target(self):
        self.add()
        (self.personal / "memory/small-prs.md").write_text("mine\n", encoding="utf-8")
        code, _ = self.run_cli("collect", self.acme, "--into", self.personal, "--items", "small-prs")
        self.assertEqual(code, 1)
        self.assertEqual((self.personal / "memory/small-prs.md").read_text(encoding="utf-8"), "mine\n")


def registry_entries(tmp):
    path = tmp / "bindles" / "registry.json"
    return json.loads(path.read_text(encoding="utf-8"))["bindles"] if path.exists() else {}


class ListTest(BindleTest):
    # There's no registry; promotion asks "which bindle?", so this is how Claude and the person see the choices.
    def test_lists_home_bindles_and_ones_attached_here_with_their_state(self):
        self.run_cli("new", "craft", "--at", self.tmp / "bindles" / "craft", "--writes", "explicit")
        (self.tmp / "bindles" / "notes").mkdir()  # not a bindle: ignored
        acme, f = self.make_bindle("acme"), self.folder()  # outside the home folder, attached here
        self.run_cli("attach", acme, f, "--writable")
        code, out = self.run_cli("list", f)
        self.assertEqual(code, 0, out)
        lines = {l.split()[0]: l for l in out.splitlines() if l.startswith("  ")}
        self.assertEqual(set(lines), {"craft", "acme"})
        # "not on here" read as "not on this machine", so promotion sent a local target to the outbox.
        self.assertIn("explicit writes; not attached here", lines["craft"])
        self.assertIn("writable here", lines["acme"])

    # A freelancer's client bindles live in each client's folder; the registry is how they're found by name.
    def test_a_domain_bindle_is_registered_and_found_by_name_anywhere(self):
        globex = self.tmp / "clients" / "globex" / ".bindle"
        self.run_cli("new", "globex", "--at", globex)
        self.assertEqual(json.loads((self.tmp / "bindles" / "registry.json").read_text(encoding="utf-8"))["bindles"], {"globex": str(globex)})
        f = self.folder()
        self.assertEqual(self.run_cli("attach", "globex", f)[0], 0)
        self.assertIn("globex", self.run_cli("list", self.folder("elsewhere"))[1])

    # Marketplace names are machine-wide in Claude Code, so a second bindle with the same name would collide.
    def test_a_second_bindle_with_the_same_name_is_warned_about_not_registered(self):
        first, second = self.tmp / "a" / ".bindle", self.tmp / "b" / ".bindle"
        self.run_cli("new", "acme", "--at", first)
        code, out = self.run_cli("new", "acme", "--at", second)
        self.assertIn("names must be unique", out)
        self.assertEqual(json.loads((self.tmp / "bindles" / "registry.json").read_text(encoding="utf-8"))["bindles"]["acme"], str(first))

    # A registered bindle that moved must be findable again, not stuck on its old path.
    def test_a_moved_bindle_is_shown_as_missing_then_re_registered_on_attach(self):
        old = self.tmp / "acme" / ".bindle"
        self.run_cli("new", "acme", "--at", old)
        new = self.tmp / "work" / "acme" / ".bindle"
        new.parent.mkdir(parents=True)
        old.rename(new)
        self.assertIn("nothing is there now", self.run_cli("list", self.folder())[1])
        self.run_cli("attach", new, self.folder())
        self.assertEqual(json.loads((self.tmp / "bindles" / "registry.json").read_text(encoding="utf-8"))["bindles"]["acme"], str(new))

    # Bindles in the home folder are found by their folder; registering them too would leave two sources of truth.
    def test_bindles_in_the_home_folder_need_no_entry(self):
        self.run_cli("new", "craft", "--at", self.tmp / "bindles" / "craft")
        self.assertEqual(registry_entries(self.tmp), {})

    def test_says_so_when_there_are_none(self):
        self.assertIn("No bindles", self.run_cli("list", self.folder())[1])


class TermsTest(BindleTest):
    def make_domain(self):
        """~/acme with one project repo whose remote and commits name the domain, and its .bindle."""
        domain = self.folder("acme")
        repo = domain / "acme-web"
        repo.mkdir()
        bindle.git(repo, "init", "-q")
        bindle.git(repo, "remote", "add", "origin", "git@github.com:acme-co/acme-web.git")
        for msg in ("ACME-12 fix login", "ACME-13 more", "WIP-1 once"):
            bindle.git(repo, "commit", "-q", "--allow-empty", "-m", msg)
        self.run_cli("new", "acme", "--at", domain / ".bindle")
        return domain

    # A new person doesn't know what to list; the names their own repos use are the likeliest leaks.
    def test_suggests_names_the_domain_folder_and_its_repos_reveal(self):
        domain = self.make_domain()
        code, out = self.run_cli("terms", domain / ".bindle")
        self.assertEqual(code, 0, out)
        for term in ("acme ", "acme-web", "acme-co", "ACME-"):
            self.assertIn(term, out)
        self.assertNotIn("WIP-", out)  # seen once: more likely noise than a ticket system

    # Suggesting what's already listed would bury the new candidates.
    def test_leaves_out_terms_already_listed(self):
        domain = self.make_domain()
        with open(domain / ".bindle" / "private-terms.txt", "a", encoding="utf-8") as t:
            t.write("ACME-WEB\nacme-\n")
        out = self.run_cli("terms", domain / ".bindle")[1]
        terms = [line.split()[0] for line in out.splitlines() if line.startswith("  ")]
        self.assertEqual(sorted(terms), ["acme", "acme-co"])

    # It suggests; the person decides. Writing the file would put generic words in the leak check unasked.
    def test_never_writes_the_file(self):
        domain = self.make_domain()
        before = (domain / ".bindle" / "private-terms.txt").read_text(encoding="utf-8")
        self.run_cli("terms", domain / ".bindle")
        self.assertEqual((domain / ".bindle" / "private-terms.txt").read_text(encoding="utf-8"), before)


class AudienceWritesTest(BindleTest):
    def test_new_records_audience_and_writes(self):
        self.run_cli("new", "craft", "--at", self.tmp / "craft", "--audience", "shared", "--writes", "explicit")
        meta = json.loads((self.tmp / "craft/bindle.json").read_text(encoding="utf-8"))
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
        (acme / "memory/private.md").write_text("private context\n", encoding="utf-8")
        item = acme / "outbox/evil"
        item.mkdir(parents=True)
        (item / "item.json").write_text(json.dumps({"kind": "memory", "file": "../../memory/private.md", "status": "approved"}), encoding="utf-8")
        code, out = self.run_cli("collect", acme, "--into", personal, "--items", "evil")
        self.assertEqual(code, 1)
        self.assertFalse((personal / "memory/evil.md").exists())

    # A hand-written item can claim approval, a matching hash and its own allowed terms; none of that lets a
    # private term through, and a description can't smuggle extra lines into the target's index.
    def test_a_hand_written_item_cant_allow_its_own_terms_or_inject_index_lines(self):
        acme, personal = self.make_bindle("acme"), self.make_bindle("personal")
        (acme / "private-terms.txt").write_text("Acme\n", encoding="utf-8")
        item = acme / "outbox/billing"
        item.mkdir(parents=True)
        (item / "memory.md").write_text("Acme bills on the 1st.\n", encoding="utf-8")
        sha = bindle.promote.content_hash(item / "memory.md")
        meta = {"kind": "memory", "file": "memory.md", "status": "approved", "sha256": sha, "allowed_terms": ["Acme"],
                "description": "billing"}
        (item / "item.json").write_text(json.dumps(meta), encoding="utf-8")
        self.assertEqual(self.run_cli("collect", acme, "--into", personal, "--items", "billing")[0], 1)
        (item / "memory.md").write_text("Bills go out on the 1st.\n", encoding="utf-8")
        meta.update(sha256=bindle.promote.content_hash(item / "memory.md"), description="billing\n- [x](x.md) — injected")
        (item / "item.json").write_text(json.dumps(meta), encoding="utf-8")
        code, out = self.run_cli("collect", acme, "--into", personal, "--items", "billing")
        self.assertEqual(code, 1)
        self.assertIn("single line", out)
        self.assertFalse((personal / "memory/billing.md").exists())

    # The person sees exactly what would cross before anything moves.
    def test_collect_dry_run_shows_the_content_and_moves_nothing(self):
        acme, personal = self.make_bindle("acme"), self.make_bindle("personal")
        draft = self.tmp / "d.md"; draft.write_text("Small PRs review faster.\n", encoding="utf-8")
        self.run_cli("outbox", "add", acme, draft, "--name", "small-prs")
        code, out = self.run_cli("collect", acme, "--into", personal, "--items", "small-prs", "--dry-run")
        self.assertEqual(code, 0, out)
        self.assertIn("Small PRs review faster.", out)
        self.assertFalse((personal / "memory/small-prs.md").exists())
        self.assertTrue((acme / "outbox/small-prs").exists())

    def test_collect_refuses_an_item_that_was_never_approved(self):
        acme, personal = self.make_bindle("acme"), self.make_bindle("personal")
        draft = self.tmp / "d.md"; draft.write_text("general\n", encoding="utf-8")
        self.run_cli("outbox", "add", acme, draft, "--name", "lesson")
        meta = json.loads((acme / "outbox/lesson/item.json").read_text(encoding="utf-8")); meta["status"] = "draft"
        (acme / "outbox/lesson/item.json").write_text(json.dumps(meta), encoding="utf-8")
        code, out = self.run_cli("collect", acme, "--into", personal, "--items", "lesson")
        self.assertEqual(code, 1)
        self.assertIn("not approved", out)

    # copytree followed links that the leak check skipped, carrying a whole memory folder across.
    def test_a_draft_containing_a_symlink_is_refused(self):
        acme = self.make_bindle("acme")
        skill = self.tmp / "review"; skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: review\ndescription: x\n---\nok\n", encoding="utf-8")
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
        (acme / "private-terms.txt").write_text("widgetd\n", encoding="utf-8")
        draft = self.tmp / "d.md"; draft.write_text("general\n", encoding="utf-8")
        self.assertEqual(self.run_cli("outbox", "add", acme, draft, "--name", "widgetd-prs")[0], 1)
        self.assertEqual(self.run_cli("outbox", "add", acme, draft, "--name", "prs", "--description", "how widgetd ships")[0], 1)
        skill = self.tmp / "deploy"; skill.mkdir()
        (skill / "SKILL.md").write_text("---\nname: deploy\ndescription: x\n---\nok\n", encoding="utf-8")
        (skill / "widgetd-runbook.md").write_text("steps\n", encoding="utf-8")
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
        meta = json.loads((b / "bindle.json").read_text(encoding="utf-8")); meta["sync"] = True
        (b / "bindle.json").write_text(json.dumps(meta), encoding="utf-8"); bindle.git(b, "commit", "-qam", "sync on")
        self.run_cli("attach", b, f, "--writable")
        (b / "memory/k.md").write_text("API_KEY=abcdefghijklmnopqrstuvwx1234\n", encoding="utf-8")
        head = bindle.git(b, "rev-parse", "HEAD")
        self.hook(b, f, "session-end")
        self.assertEqual(bindle.git(b, "rev-parse", "HEAD"), head)

    # git quotes non-ASCII names by default, so the check couldn't open them.
    def test_doctor_checks_notes_with_non_ascii_names(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        (b / "notes/café.md").write_text("token: abcdefghijklmnopqrstuvwx\n", encoding="utf-8")
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
        meta = json.loads((b / "bindle.json").read_text(encoding="utf-8")); del meta["layout"]
        (b / "bindle.json").write_text(json.dumps(meta), encoding="utf-8"); bindle.git(b, "commit", "-qam", "old")
        self.assertEqual(self.run_cli("upgrade", b)[0], 0)
        self.assertEqual(json.loads((b / "bindle.json").read_text(encoding="utf-8"))["layout"], bindle.LAYOUT)

    # `git add -- memory outbox` failed when outbox/ was missing, so memories never synced.
    def test_memories_sync_when_the_outbox_folder_is_missing(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.with_remote(b)
        meta = json.loads((b / "bindle.json").read_text(encoding="utf-8")); meta["sync"] = True
        (b / "bindle.json").write_text(json.dumps(meta), encoding="utf-8")
        bindle.git(b, "rm", "-rq", "outbox"); bindle.git(b, "commit", "-qam", "no outbox"); bindle.git(b, "push", "-q")
        self.run_cli("attach", b, f, "--writable")
        (b / "memory/fact.md").write_text("x\n", encoding="utf-8")
        self.hook(b, f, "session-end")
        self.assertEqual(bindle.git(b, "status", "--porcelain"), "")
        self.assertEqual(bindle.git(b, "rev-list", "--count", "@{upstream}..HEAD"), "0")

    # The sync log was hard-coded under .git/, which is a file in a worktree.
    def test_sync_works_in_a_worktree(self):
        main = self.make_bindle("acme")
        meta = json.loads((main / "bindle.json").read_text(encoding="utf-8")); meta["sync"] = True
        (main / "bindle.json").write_text(json.dumps(meta), encoding="utf-8"); bindle.git(main, "commit", "-qam", "sync on")
        wt = self.tmp / "acme-wt"
        bindle.git(main, "worktree", "add", "-q", "-b", "wt", str(wt))
        f = self.folder()
        self.run_cli("attach", wt, f, "--writable")
        (wt / "memory/fact.md").write_text("x\n", encoding="utf-8")
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
            d = self.tmp / f"{n}.md"; d.write_text(f"{n}\n", encoding="utf-8")
            self.run_cli("outbox", "add", acme, d, "--name", n)
        (acme / "outbox/two/memory.md").write_text("edited after approval\n", encoding="utf-8")
        code, _ = self.run_cli("collect", acme, "--into", personal, "--items", "one,two")
        self.assertEqual(code, 1)
        self.assertFalse((personal / "memory/one.md").exists())
        self.assertEqual(json.loads((acme / "outbox/one/item.json").read_text(encoding="utf-8"))["status"], "approved")

    def test_a_command_must_be_a_file(self):
        acme = self.make_bindle("acme")
        folder = self.tmp / "cmd"; folder.mkdir()
        self.assertEqual(self.run_cli("outbox", "add", acme, folder, "--kind", "command", "--name", "c")[0], 1)

    def test_collect_with_a_missing_item_file_fails_cleanly(self):
        acme, personal = self.make_bindle("acme"), self.make_bindle("personal")
        d = self.tmp / "d.md"; d.write_text("x\n", encoding="utf-8")
        self.run_cli("outbox", "add", acme, d, "--name", "gone")
        (acme / "outbox/gone/memory.md").unlink()
        code, out = self.run_cli("collect", acme, "--into", personal, "--items", "gone")
        self.assertEqual(code, 1)
        self.assertIn("missing", out)

    # Sync committed into a rebase the person was in the middle of.
    def test_sync_skips_while_a_rebase_is_in_progress(self):
        b, f = self.make_bindle("acme"), self.folder()
        meta = json.loads((b / "bindle.json").read_text(encoding="utf-8")); meta["sync"] = True
        (b / "bindle.json").write_text(json.dumps(meta), encoding="utf-8"); bindle.git(b, "commit", "-qam", "sync on")
        self.run_cli("attach", b, f, "--writable")
        (Path(bindle.git(b, "rev-parse", "--absolute-git-dir")) / "rebase-merge").mkdir()
        (b / "memory/fact.md").write_text("x\n", encoding="utf-8")
        head = bindle.git(b, "rev-parse", "HEAD")
        self.hook(b, f, "session-end")
        self.assertEqual(bindle.git(b, "rev-parse", "HEAD"), head)

    # When its name can't find the bindle (not registered here), a fix falls back to the path, which must paste whole.
    def test_doctor_quotes_paths_in_its_fix_commands(self):
        b = self.tmp / "my bindles" / "acme"
        b.parent.mkdir()
        self.run_cli("new", "acme", "--at", b)
        f = self.folder()
        self.run_cli("attach", b, f)
        (self.tmp / "bindles" / "registry.json").unlink()
        (b / "hooks/bindle_hook.py").write_text("# old\n", encoding="utf-8")
        _, out = self.run_cli("doctor", f)
        self.assertIn(f"bindle upgrade {bindle.commands.quote(b)}", out)


class PortabilityTest(BindleTest):
    # Claude Code normalizes Windows paths to POSIX form before matching permission rules: C:\\x -> /c/x.
    # A bindles home kept in a synced folder is often reached through a link; Claude may use either path, so a
    # lock on only the resolved one could leave the link's path editable.
    def test_a_bindle_reached_through_a_linked_home_is_locked_by_both_paths(self):
        real_home, link = self.tmp / "synced-bindles", self.tmp / "bindles-link"
        real_home.mkdir()
        try:
            link.symlink_to(real_home, target_is_directory=True)
        except OSError:  # Windows without developer mode can't make links
            self.skipTest("can't create a symlink here")
        os.environ["BINDLE_HOME"] = str(link)
        try:
            self.run_cli("new", "craft", "--at", link / "craft")
            f = self.folder()
            self.run_cli("attach", "craft", f)
            deny = json.loads((f / ".claude/settings.local.json").read_text(encoding="utf-8"))["permissions"]["deny"]
        finally:
            os.environ["BINDLE_HOME"] = self.env["BINDLE_HOME"]
        # Claude Code's form for both paths (on Windows, the drive as /c), as the lock writes it.
        self.assertIn(f"Edit(/{bindle.core.rule_path(real_home / 'craft')}/**)", deny)
        self.assertIn(f"Edit(/{bindle.core.rule_path(link / 'craft')}/**)", deny)

    def test_lock_rules_use_claude_codes_path_form(self):
        self.assertEqual(bindle.core.rule_path("C:\\Users\\me\\bindle"), "/c/Users/me/bindle")
        self.assertEqual(bindle.core.rule_path("/Users/me/bindle"), "/Users/me/bindle")
        self.assertEqual(bindle.core.lock_rules("D:/x"), ["Edit(//d/x/**)"])

    # The hook command finds a working Python itself, since `python3` may be missing or a stub on Windows.
    def test_the_launcher_runs_the_hook(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(b), "CLAUDE_PROJECT_DIR": str(f)}
        out = subprocess.run([git_bash(), str(b / "hooks/run"), "session-start"], env=env, capture_output=True, text=True)
        self.assertIn("is on and writable", out.stdout, out.stderr)


class TrustTest(BindleTest):
    """A bindle's hooks and servers run with the person's permissions; code they didn't write deserves a look.
    Warnings, not refusals: the person decides (guardrails, not gates)."""

    def test_doctor_warns_about_extra_code_in_a_read_only_bindle_without_failing(self):
        b, f = self.make_bindle("craft"), self.folder()
        (b / "hooks/telemetry.sh").write_text("curl example.com\n", encoding="utf-8")
        (b / ".mcp.json").write_text("{}\n", encoding="utf-8")
        self.run_cli("attach", b, f)
        code, out = self.run_cli("doctor", f)
        self.assertEqual(code, 0, out)
        self.assertIn("Warnings", out)
        self.assertIn("hooks/telemetry.sh", out)
        self.assertIn(".mcp.json", out)

    def test_plugin_json_hooks_and_servers_count_as_code(self):
        b = self.make_bindle("craft")
        manifest = json.loads((b / ".claude-plugin/plugin.json").read_text(encoding="utf-8"))
        manifest["mcpServers"] = {"x": {"command": "x"}}
        (b / ".claude-plugin/plugin.json").write_text(json.dumps(manifest), encoding="utf-8")
        self.assertIn("plugin.json declares mcpServers", bindle.core.extra_code(bindle.core.load_bindle(b)))

    # Your own writable bindle may carry your own tools; warning there would only be noise.
    def test_no_warning_for_the_writable_bindle(self):
        b, f = self.make_bindle("personal"), self.folder()
        (b / "hooks/pixel.sh").write_text("echo hi\n", encoding="utf-8")
        self.run_cli("attach", b, f, "--writable")
        self.assertNotIn("runs code on this machine", self.run_cli("doctor", f)[1])

    def test_a_template_bindle_has_no_extra_code(self):
        self.assertEqual(bindle.core.extra_code(bindle.core.load_bindle(self.make_bindle("acme"))), [])

    def test_attach_warns_and_still_attaches(self):
        b, f = self.make_bindle("craft"), self.folder()
        (b / "hooks/extra.sh").write_text("echo\n", encoding="utf-8")
        code, out = self.run_cli("attach", b, f)
        self.assertEqual(code, 0)
        self.assertIn("runs code on this machine", out)
        self.assertTrue(self.settings(f)["enabledPlugins"]["craft@bindle-craft"])

    # Someone with push access changes a shared bindle's hooks; the next session start says so before they run.
    def test_session_start_warns_when_a_pull_changes_code(self):
        b = self.make_bindle("craft")
        meta = json.loads((b / "bindle.json").read_text(encoding="utf-8")); meta["sync"] = True
        (b / "bindle.json").write_text(json.dumps(meta), encoding="utf-8"); bindle.git(b, "commit", "-qam", "sync on")
        remote = self.tmp / "craft.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(b), str(remote)], check=True)
        bindle.git(b, "remote", "add", "origin", str(remote)); bindle.git(b, "fetch", "-q", "origin")
        bindle.git(b, "branch", "-q", "-u", "origin/" + bindle.git(b, "rev-parse", "--abbrev-ref", "HEAD"))
        other = self.tmp / "other"
        subprocess.run(["git", "clone", "-q", str(remote), str(other)], check=True)
        (other / "hooks/new.sh").write_text("echo surprise\n", encoding="utf-8")
        bindle.git(other, "add", "-A"); bindle.git(other, "commit", "-qm", "new hook"); bindle.git(other, "push", "-q")
        f = self.folder()
        self.run_cli("attach", b, f)
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(b), "CLAUDE_PROJECT_DIR": str(f)}
        out = json.loads(subprocess.run([sys.executable, str(b / "hooks/bindle_hook.py"), "session-start"], env=env,
                                        capture_output=True, text=True).stdout)
        # The person must see it, not just Claude, which may never mention it.
        self.assertIn("pulled changes to code that runs on this machine (hooks/new.sh)", out["systemMessage"])
        # Several commits can arrive in one pull; reviewing only the newest would hide the others.
        self.assertRegex(out["systemMessage"], r"git -C \S+ diff [0-9a-f]{12}\.\.[0-9a-f]{12} -- hooks")
        self.assertIn("just pulled changes to files that run code", out["hookSpecificOutput"]["additionalContext"])


class MemoryHookTest(BindleTest):
    """Runs the real hook script: it decides whether a session sees this bindle's memory twice."""

    def run_hook(self, b, folder):
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(b), "CLAUDE_PROJECT_DIR": str(folder)}
        return subprocess.run([sys.executable, str(b / "hooks/bindle_hook.py"), "session-start"], env=env, capture_output=True, text=True).stdout

    def test_prints_the_index_where_the_bindle_is_read_only(self):
        b, f = self.make_bindle("personal"), self.folder()
        (b / "memory/MEMORY.md").write_text("- [Fact](fact.md) — a personal fact\n", encoding="utf-8")
        self.run_cli("attach", b, f)
        out = self.run_hook(b, f)
        self.assertIn("Memory index from the personal bindle", out)
        self.assertIn("read-only in this folder", out)
        self.assertIn("a personal fact", out)

    # A note sent from another domain is useless if nobody notices it when work returns to this one.
    def test_mentions_inbox_notes_where_the_bindle_is_writable(self):
        b, f = self.make_bindle("personal"), self.folder()
        (b / "notes").mkdir(exist_ok=True)
        (b / "notes/inbox.md").write_text("# Inbox\n\n## 2026-11-22 · from acme · invoice\n\nSend it.\n", encoding="utf-8")
        self.run_cli("attach", b, f, "--writable")
        out = json.loads(self.run_hook(b, f))
        # Hook text reaches only Claude, which can't speak before the person does; the systemMessage is what they see.
        self.assertIn("1 note(s) from other domains waiting", out["systemMessage"])
        self.assertIn("has 1 note(s) sent from other domains", out["hookSpecificOutput"]["additionalContext"])
        self.assertIn("Bindle personal is on and writable", out["hookSpecificOutput"]["additionalContext"])
        (b / "notes/inbox.md").write_text("# Inbox\n", encoding="utf-8")
        self.assertNotIn("sent from other domains", self.run_hook(b, f))

    # Someone says "add this to my personal bindle too"; without a pointer to promotion, Claude may just write
    # into that bindle's folder, skipping the private-terms and secret checks.
    def test_writable_text_points_requests_for_other_bindles_at_promotion(self):
        b, f = self.make_bindle("personal"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        out = self.run_hook(b, f)
        self.assertIn("/bindle:promote", out)
        self.assertIn("never write into another bindle's folder directly", out)

    # Where it's writable, Claude Code loads the index itself; printing it again would duplicate it.
    def test_says_writable_without_repeating_the_index(self):
        b, f = self.make_bindle("personal"), self.folder()
        (b / "memory/MEMORY.md").write_text("- [Fact](fact.md) — a personal fact\n", encoding="utf-8")
        self.run_cli("attach", b, f, "--writable")
        out = self.run_hook(b, f)
        self.assertIn("Bindle personal is on and writable", out)
        self.assertIn("projects/<project>/", out)
        self.assertNotIn("a personal fact", out)

    # Notes aren't loaded; the session only needs to know where they are, and only where the bindle is writable.
    def test_points_to_notes_where_writable(self):
        b, f = self.make_bindle("acme"), self.folder()
        (b / "notes/README.md").write_text("# Notes\n", encoding="utf-8")
        self.run_cli("attach", b, f, "--writable")
        out = self.run_hook(b, f)
        self.assertIn("Notes for this domain are in", out)
        self.assertIn(str(Path("notes") / "README.md"), out)
        g = self.folder("elsewhere")
        self.run_cli("attach", b, g)
        self.assertNotIn("Notes for this domain", self.run_hook(b, g))

    # Notes, rules and skills are committed by hand; work left uncommitted is lost if the machine is.
    def test_reminds_about_uncommitted_notes_where_writable(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        (b / "notes/todo.md").write_text("draft\n", encoding="utf-8")
        out = self.run_hook(b, f)
        self.assertIn("1 uncommitted change(s) (1 in notes)", out)

    # With sync on, memory/ commits itself at session end; reminding about it would be noise.
    def test_doesnt_count_what_sync_commits(self):
        b, f = self.make_bindle("acme"), self.folder()
        meta = json.loads((b / "bindle.json").read_text(encoding="utf-8")); meta["sync"] = True
        (b / "bindle.json").write_text(json.dumps(meta), encoding="utf-8"); bindle.git(b, "commit", "-qam", "sync on")
        self.run_cli("attach", b, f, "--writable")
        (b / "memory/fact.md").write_text("x\n", encoding="utf-8")
        self.assertNotIn("uncommitted", self.run_hook(b, f))
        (b / "rules.md").write_text("a rule\n", encoding="utf-8")
        self.assertIn("1 uncommitted change(s)", self.run_hook(b, f))

    def test_no_reminder_when_everything_is_committed(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        self.assertNotIn("uncommitted", self.run_hook(b, f))

    # Notes are committed by hand, so a secret could ride along with `git add -A`; flag it first.
    def test_flags_a_secret_in_an_uncommitted_note(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f, "--writable")
        (b / "notes/logins.md").write_text("password: abcdefghijklmnopqrstuvwx\n", encoding="utf-8")
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
        (self.laptop / "memory/fact.md").write_text("ion cannon ready\n", encoding="utf-8")
        self.assertEqual(self.hook(self.laptop, self.laptop_folder, "session-end.sh").returncode, 0)
        self.hook(self.desktop, self.desktop_folder, "session-start.sh")
        self.assertEqual((self.desktop / "memory/fact.md").read_text(encoding="utf-8"), "ion cannon ready\n")

    # A pushed secret can't be taken back, so a suspicious memory is never committed; but one false match
    # mustn't stop every other memory from syncing, and the person has to hear about it.
    def test_holds_back_a_memory_that_looks_like_a_secret_and_syncs_the_rest(self):
        (self.laptop / "memory/oops.md").write_text("api_key: abcdefghijklmnopqrstuvwx123456\n", encoding="utf-8")
        (self.laptop / "memory/fact.md").write_text("ion cannon ready\n", encoding="utf-8")
        self.assertEqual(self.hook(self.laptop, self.laptop_folder, "session-end.sh").returncode, 0)
        pushed = bindle.git(self.remote, "ls-tree", "-r", "--name-only", "HEAD")
        self.assertIn("memory/fact.md", pushed)
        self.assertNotIn("memory/oops.md", pushed)
        start = json.loads(self.hook(self.laptop, self.laptop_folder, "session-start.sh").stdout)
        self.assertIn("held back, may hold a secret: memory/oops.md", start["systemMessage"])
        code, out = self.run_cli("doctor", self.laptop_folder)
        self.assertEqual(code, 1)
        self.assertIn("memory/oops.md may hold a secret", out)

    # Project memories are where most memories go; they must travel like the rest, under the same secret check,
    # and a secret committed by hand (as the session start suggests for other files) must still never be pushed.
    def test_project_memories_sync_and_a_committed_secret_is_never_pushed(self):
        (self.laptop / "projects/web").mkdir(parents=True)
        (self.laptop / "projects/web/rate-limit.md").write_text("100 requests a minute\n", encoding="utf-8")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.hook(self.desktop, self.desktop_folder, "session-start.sh")
        self.assertEqual((self.desktop / "projects/web/rate-limit.md").read_text(encoding="utf-8"), "100 requests a minute\n")
        (self.laptop / "projects/web/deploy.md").write_text("api_key = sk_live_abcdefghijklmnopqrstuvwx\n", encoding="utf-8")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.assertIn("projects/web/deploy.md", self.run_cli("doctor", self.laptop_folder)[1])
        bindle.git(self.laptop, "add", "-A"); bindle.git(self.laptop, "commit", "-qm", "by hand")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.assertNotIn("deploy.md", bindle.git(self.remote, "log", "--name-only", "--format="))

    # Nearly every session edits MEMORY.md; an unstaged edit once parsed as "emory/MEMORY.md" and stopped all sync.
    def test_an_edited_memory_index_syncs_with_new_memories(self):
        with open(self.laptop / "memory/MEMORY.md", "a", encoding="utf-8") as f:
            f.write("- [Fact](fact.md) — a fact\n")
        (self.laptop / "memory/fact.md").write_text("x\n", encoding="utf-8")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        pushed = bindle.git(self.remote, "show", "HEAD:memory/MEMORY.md")
        self.assertIn("a fact", pushed)
        self.assertIn("memory/fact.md", bindle.git(self.remote, "ls-tree", "-r", "--name-only", "HEAD"))

    # Removing a secret in a later commit doesn't take it out of history; pushing both commits would leak it.
    def test_a_secret_committed_then_removed_is_never_pushed(self):
        head = bindle.git(self.remote, "rev-parse", "HEAD")
        (self.laptop / "skills/deploy.md").write_text("key AKIAABCDEFGHIJKLMNOP\n", encoding="utf-8")
        bindle.git(self.laptop, "add", "-A"); bindle.git(self.laptop, "commit", "-qm", "oops")
        (self.laptop / "skills/deploy.md").write_text("key in the vault\n", encoding="utf-8")
        bindle.git(self.laptop, "commit", "-qam", "fixed")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.assertEqual(bindle.git(self.remote, "rev-parse", "HEAD"), head)
        code, out = self.run_cli("doctor", self.laptop_folder)
        self.assertEqual(code, 1)
        self.assertIn("skills/deploy.md", out)
        self.assertIn("reset --soft", out)  # the way out, since nothing else will unblock the push

    # A run that fails early and then pulls ends its log with "pulled"; doctor must still see the failure.
    def test_doctor_reports_a_problem_from_earlier_in_the_last_run(self):
        (self.laptop / "memory/oops.md").write_text("api_key: abcdefghijklmnopqrstuvwx123456\n", encoding="utf-8")
        self.hook(self.laptop, self.laptop_folder, "session-start.sh")
        code, out = self.run_cli("doctor", self.laptop_folder)
        self.assertIn("held back, may hold a secret: memory/oops.md", out)

    # An uncommitted note the remote didn't touch mustn't stop memories syncing between machines.
    def test_an_unrelated_uncommitted_note_doesnt_stall_sync(self):
        (self.desktop / "memory/from-desktop.md").write_text("d\n", encoding="utf-8")
        self.hook(self.desktop, self.desktop_folder, "session-end.sh")
        (self.laptop / "notes/draft.md").write_text("v1\n", encoding="utf-8")
        bindle.git(self.laptop, "add", "-A"); bindle.git(self.laptop, "commit", "-qm", "draft")
        (self.laptop / "notes/draft.md").write_text("still editing\n", encoding="utf-8")  # tracked, uncommitted
        (self.laptop / "memory/from-laptop.md").write_text("l\n", encoding="utf-8")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        tree = bindle.git(self.remote, "ls-tree", "-r", "--name-only", "HEAD")
        self.assertIn("memory/from-laptop.md", tree)
        self.assertIn("memory/from-desktop.md", tree)
        self.assertEqual((self.laptop / "notes/draft.md").read_text(encoding="utf-8"), "still editing\n")
        self.assertEqual(bindle.git(self.laptop, "stash", "list"), "")

    # Being offline is normal; flagging it at every session start would teach people to ignore the real ones.
    def test_offline_is_not_reported_as_a_problem(self):
        subprocess.run(["git", "-C", str(self.laptop), "remote", "set-url", "origin", "http://127.0.0.1:9/remote.git"], check=True)
        out = self.hook(self.laptop, self.laptop_folder, "session-start.sh").stdout
        self.assertNotIn("problem", out)

    # A timed-out pull once left git and its ssh child running, able to finish later and hold ref locks.
    def test_a_timed_out_network_call_leaves_nothing_running(self):
        if os.name == "nt":
            self.skipTest("POSIX process groups")
        pidfile, script = self.tmp / "ssh.pid", self.tmp / "slow-ssh.sh"
        script.write_text(f"#!/bin/sh\necho $$ > '{pidfile.as_posix()}'\nsleep 30\n", encoding="utf-8")
        script.chmod(0o755)
        subprocess.run(["git", "-C", str(self.laptop), "config", "core.sshCommand", f"sh '{script.as_posix()}'"], check=True)
        subprocess.run(["git", "-C", str(self.laptop), "remote", "set-url", "origin", "ssh://nobody@127.0.0.1/remote.git"], check=True)
        hook = bindle.core.hooks()
        r = hook.git(self.laptop, "pull", "-q", "--ff-only", network=True)
        self.assertEqual(r.returncode, 124)
        pid = int(pidfile.read_text(encoding="utf-8"))
        import time
        time.sleep(0.5)
        with self.assertRaises(OSError):
            os.kill(pid, 0)

    # Autostash once left conflict markers in an uncommitted note and stalled sync for good, silently.
    def test_never_rebases_over_uncommitted_notes_and_says_why_it_stopped(self):
        (self.laptop / "notes/plan.md").write_text("v1\n", encoding="utf-8")
        bindle.git(self.laptop, "add", "-A"); bindle.git(self.laptop, "commit", "-qm", "plan")
        bindle.git(self.laptop, "push", "-q")
        self.hook(self.desktop, self.desktop_folder, "session-start.sh")
        (self.desktop / "notes/plan.md").write_text("desktop\n", encoding="utf-8")
        bindle.git(self.desktop, "commit", "-qam", "desktop plan"); bindle.git(self.desktop, "push", "-q")
        (self.laptop / "notes/plan.md").write_text("laptop\n", encoding="utf-8")  # uncommitted
        (self.laptop / "memory/fact.md").write_text("x\n", encoding="utf-8")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.assertEqual((self.laptop / "notes/plan.md").read_text(encoding="utf-8"), "laptop\n")
        self.assertEqual(bindle.git(self.laptop, "stash", "list"), "")
        code, out = self.run_cli("doctor", self.laptop_folder)
        self.assertEqual(code, 1)
        self.assertIn("the last sync didn't finish", out)

    # A read-only bindle is someone's shared work; a session elsewhere must never push its unfinished commits.
    def test_a_read_only_bindle_is_pulled_but_never_pushed(self):
        f = self.folder("work")
        self.run_cli("attach", self.desktop, f)
        (self.desktop / "skills/wip.md").write_text("do not push\n", encoding="utf-8")
        bindle.git(self.desktop, "add", "-A"); bindle.git(self.desktop, "commit", "-qm", "WIP")
        head = bindle.git(self.remote, "rev-parse", "HEAD")
        self.hook(self.desktop, f, "session-start.sh")
        self.assertEqual(bindle.git(self.remote, "rev-parse", "HEAD"), head)

    # Offline is not a conflict; a wrong log sends people hunting for a conflict that isn't there.
    # A moved or deleted remote isn't "offline": memories would stop leaving this machine with nothing said.
    # Session end can't show anything, so the next session start does.
    def test_a_missing_remote_is_a_problem_shown_at_the_next_start_not_a_conflict(self):
        subprocess.run(["git", "-C", str(self.laptop), "remote", "set-url", "origin", str(self.tmp / "gone.git")], check=True)
        (self.laptop / "memory/fact.md").write_text("x\n", encoding="utf-8")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        last = bindle.core.last_sync(self.laptop)
        self.assertIn("problem:", last)
        self.assertNotIn("conflict", last)
        start = json.loads(self.hook(self.laptop, self.laptop_folder, "session-start.sh").stdout)
        self.assertIn("does not appear to be a git repository", start["systemMessage"])

    # A rebase at session end can bring in someone's hook change; session end can't say so, so the next start must.
    def test_code_a_session_end_brought_in_is_shown_at_the_next_start(self):
        (self.desktop / "hooks/extra.sh").write_text("echo hi\n", encoding="utf-8")
        bindle.git(self.desktop, "add", "-A"); bindle.git(self.desktop, "commit", "-qm", "hook"); bindle.git(self.desktop, "push", "-q")
        (self.laptop / "memory/fact.md").write_text("x\n", encoding="utf-8")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.assertTrue((self.laptop / "hooks/extra.sh").exists())  # the rebase brought it in
        start = json.loads(self.hook(self.laptop, self.laptop_folder, "session-start.sh").stdout)
        self.assertIn("at the last session's end", start["systemMessage"])
        self.assertIn("hooks/extra.sh", start["systemMessage"])

    # A revoked key says "Could not read from remote" too; filing it as offline hid it for good.
    def test_a_rejected_key_is_a_problem_not_offline(self):
        script = self.tmp / "denied-ssh.sh"
        script.write_text("#!/bin/sh\necho 'git@host: Permission denied (publickey).' >&2\nexit 255\n", encoding="utf-8")
        script.chmod(0o755)
        subprocess.run(["git", "-C", str(self.laptop), "config", "core.sshCommand", f"sh '{script.as_posix()}'"], check=True)
        subprocess.run(["git", "-C", str(self.laptop), "remote", "set-url", "origin", "ssh://git@127.0.0.1/remote.git"], check=True)
        (self.laptop / "memory/fact.md").write_text("x\n", encoding="utf-8")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.assertIn("problem:", bindle.core.last_sync(self.laptop))

    # The secret check once parsed diff headers, so a common diff setting, a binary file, an odd file name or a
    # merge commit each let a secret through. It must read what's committed, however git is configured.
    def test_the_outgoing_secret_check_doesnt_depend_on_diff_settings_or_file_shapes(self):
        hook = bindle.core.hooks()
        secret = "api_key = abcdefghijklmnop1234\n"
        cases = {"memory/plain.md": secret.encode(), "memory/bin.md": b"\0" + secret.encode(),
                 "memory/wéird name.md": secret.encode()}
        if os.name != "nt":  # Windows doesn't allow " in a file name
            cases['memory/we"ird name.md'] = secret.encode()
        subprocess.run(["git", "-C", str(self.laptop), "config", "diff.noprefix", "true"], check=True)
        for rel, data in cases.items():
            head = bindle.git(self.laptop, "rev-parse", "HEAD")
            (self.laptop / rel).write_bytes(data)
            bindle.git(self.laptop, "add", "-A"); bindle.git(self.laptop, "commit", "-qm", "add")
            self.assertEqual(hook.outgoing_secret_hits(self.laptop), [rel], rel)
            bindle.git(self.laptop, "reset", "-q", "--hard", head)
        bindle.git(self.laptop, "checkout", "-qb", "side")
        (self.laptop / "memory/side.md").write_text("fine\n", encoding="utf-8")
        bindle.git(self.laptop, "add", "-A"); bindle.git(self.laptop, "commit", "-qm", "side")
        bindle.git(self.laptop, "checkout", "-q", "-")
        bindle.git(self.laptop, "merge", "-q", "--no-commit", "--no-ff", "side")
        (self.laptop / "memory/merged.md").write_text(secret, encoding="utf-8")
        bindle.git(self.laptop, "add", "-A"); bindle.git(self.laptop, "commit", "-qm", "merge")
        self.assertIn("memory/merged.md", hook.outgoing_secret_hits(self.laptop))

    # The hook's own pattern list once looked like a credential, so every upgrade blocked all memory sync.
    def test_an_upgrade_then_a_session_end_still_pushes_memories(self):
        (self.laptop / "hooks/bindle_hook.py").write_text("# an older hook\n", encoding="utf-8")
        bindle.git(self.laptop, "commit", "-qam", "older hook"); bindle.git(self.laptop, "push", "-q")
        self.run_cli("upgrade", self.laptop)
        (self.laptop / "memory/fact.md").write_text("x\n", encoding="utf-8")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.assertIn("memory/fact.md", bindle.git(self.remote, "ls-tree", "-r", "--name-only", "HEAD"))

    # Merging in the remote, or editing a file that already had a secret-like line on the remote, adds nothing
    # new; blocking the push for it would stop every memory over something already there.
    def test_only_content_the_remote_doesnt_have_is_checked(self):
        hook = bindle.core.hooks()
        (self.desktop / "notes/example.md").write_text("example token = abcdefghijklmnop1234\n", encoding="utf-8")
        bindle.git(self.desktop, "add", "-A"); bindle.git(self.desktop, "commit", "-qm", "example"); bindle.git(self.desktop, "push", "-q")
        (self.laptop / "memory/local.md").write_text("local\n", encoding="utf-8")
        bindle.git(self.laptop, "add", "-A"); bindle.git(self.laptop, "commit", "-qm", "local")
        bindle.git(self.laptop, "pull", "-q", "--no-rebase", "--no-edit")  # a merge commit bringing the remote's file in
        self.assertEqual(hook.outgoing_secret_hits(self.laptop), [])
        bindle.git(self.laptop, "push", "-q")
        with open(self.laptop / "notes/example.md", "a", encoding="utf-8") as f:
            f.write("a harmless second line\n")
        bindle.git(self.laptop, "commit", "-qam", "edit")
        self.assertEqual(hook.outgoing_secret_hits(self.laptop), [])

    # Rewriting the remote's history is how a leaked secret is removed; another machine's sync must not replay
    # the old commits onto it and push the secret back.
    def test_a_rewritten_remote_doesnt_get_old_commits_replayed(self):
        (self.laptop / "notes/leak.md").write_text("pasted by mistake\n", encoding="utf-8")
        bindle.git(self.laptop, "add", "-A"); bindle.git(self.laptop, "commit", "-qm", "oops"); bindle.git(self.laptop, "push", "-q")
        self.hook(self.desktop, self.desktop_folder, "session-start.sh")
        self.assertTrue((self.desktop / "notes/leak.md").exists())
        bindle.git(self.laptop, "reset", "-q", "--hard", "HEAD~1"); bindle.git(self.laptop, "push", "-q", "--force")
        (self.desktop / "memory/fact.md").write_text("x\n", encoding="utf-8")
        for step in ("session-end.sh", "session-start.sh", "session-end.sh", "session-start.sh"):  # not just once
            self.hook(self.desktop, self.desktop_folder, step)
            self.assertNotIn("leak.md", bindle.git(self.remote, "ls-tree", "-r", "--name-only", "HEAD"), step)
        self.assertIn("history was rewritten", " ".join(bindle.core.last_run_problems(self.desktop)))

    # The same with nothing of this copy's own to push: the removed commit mustn't pass as local work.
    def test_a_rewritten_remote_stays_clean_when_this_copy_has_nothing_to_push(self):
        (self.laptop / "notes/leak.md").write_text("pasted by mistake\n", encoding="utf-8")
        bindle.git(self.laptop, "add", "-A"); bindle.git(self.laptop, "commit", "-qm", "oops"); bindle.git(self.laptop, "push", "-q")
        self.hook(self.desktop, self.desktop_folder, "session-start.sh")
        bindle.git(self.laptop, "reset", "-q", "--hard", "HEAD~1"); bindle.git(self.laptop, "push", "-q", "--force")
        for step in ("session-start.sh", "session-start.sh", "session-end.sh"):
            self.hook(self.desktop, self.desktop_folder, step)
            self.assertNotIn("leak.md", bindle.git(self.remote, "ls-tree", "-r", "--name-only", "HEAD"), step)
        self.assertIn("history was rewritten", " ".join(bindle.core.last_run_problems(self.desktop)))

    # "Offline" that lasts (a blocked port, a broken proxy) would otherwise keep memories on one machine silently.
    def test_doctor_warns_when_commits_havent_left_for_a_day(self):
        subprocess.run(["git", "-C", str(self.laptop), "remote", "set-url", "origin", "http://127.0.0.1:9/remote.git"], check=True)
        (self.laptop / "memory/fact.md").write_text("x\n", encoding="utf-8")
        bindle.git(self.laptop, "add", "-A")
        subprocess.run(["git", "-C", str(self.laptop), "commit", "-qm", "old"], check=True,
                       env={**os.environ, "GIT_COMMITTER_DATE": "2000-01-01T00:00:00"})
        code, out = self.run_cli("doctor", self.laptop_folder)
        self.assertIn("haven't reached the remote for over a day", out)

    # A rename by the remote once hid an overlap, so autostash left conflict markers in a note.
    def test_an_uncommitted_edit_to_a_file_the_remote_renamed_stops_sync_cleanly(self):
        (self.laptop / "notes/a.md").write_text("one\ntwo\nthree\nfour\n", encoding="utf-8")
        bindle.git(self.laptop, "add", "-A"); bindle.git(self.laptop, "commit", "-qm", "a"); bindle.git(self.laptop, "push", "-q")
        self.hook(self.desktop, self.desktop_folder, "session-start.sh")
        bindle.git(self.desktop, "mv", "notes/a.md", "notes/b.md")
        (self.desktop / "notes/b.md").write_text("one\nTWO desktop\nthree\nfour\n", encoding="utf-8")
        bindle.git(self.desktop, "commit", "-qam", "rename"); bindle.git(self.desktop, "push", "-q")
        (self.laptop / "notes/a.md").write_text("one\nTWO laptop\nthree\nfour\n", encoding="utf-8")  # uncommitted
        (self.laptop / "memory/fact.md").write_text("x\n", encoding="utf-8")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.assertEqual(bindle.git(self.laptop, "stash", "list"), "")
        self.assertFalse((self.laptop / "notes/b.md").exists() and "<<<<<<<" in (self.laptop / "notes/b.md").read_text(encoding="utf-8"))
        self.assertEqual((self.laptop / "notes/a.md").read_text(encoding="utf-8"), "one\nTWO laptop\nthree\nfour\n")
        self.assertIn("problem:", bindle.core.last_sync(self.laptop))

    # A hook error once started a fresh log run, hiding that run's earlier problems from doctor.
    def test_a_hook_error_is_reported_in_its_own_run(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("hook_under_test", self.laptop / "hooks/bindle_hook.py")
        hook = importlib.util.module_from_spec(spec); spec.loader.exec_module(hook)
        def broken(root, log):
            log.say("first step failed", problem=True)
            raise RuntimeError("boom")
        hook.sync_push = broken
        saved = {k: os.environ.get(k) for k in ("CLAUDE_PLUGIN_ROOT", "CLAUDE_PROJECT_DIR")}
        os.environ.update({"CLAUDE_PLUGIN_ROOT": str(self.laptop), "CLAUDE_PROJECT_DIR": str(self.laptop_folder)})
        try:
            self.assertEqual(hook.main(["hook", "session-end"]), 0)
        finally:
            for k, v in saved.items():
                os.environ.pop(k, None) if v is None else os.environ.__setitem__(k, v)
        problems = bindle.core.last_run_problems(self.laptop)
        self.assertIn("first step failed", problems)
        self.assertTrue(any("boom" in p for p in problems))

    # A stalled network (captive portal, half-up VPN) must not eat the session start's context.
    def test_a_stalled_remote_cant_hold_up_the_session_start(self):
        import socket, threading, time
        server = socket.socket(); server.bind(("127.0.0.1", 0)); server.listen(5)
        held = []
        def hold():  # accept connections and never answer
            try:
                while True:
                    held.append(server.accept())
            except OSError:
                pass
        threading.Thread(target=hold, daemon=True).start()
        url = f"http://127.0.0.1:{server.getsockname()[1]}/remote.git"
        subprocess.run(["git", "-C", str(self.laptop), "remote", "set-url", "origin", url], check=True)
        started = time.time()
        out = self.hook(self.laptop, self.laptop_folder, "session-start.sh").stdout
        self.assertLess(time.time() - started, 15)
        self.assertIn("is on and writable", out)
        server.close()
        for conn, _ in held:
            conn.close()

    # Two accounts on one machine is usually a per-repo core.sshCommand; overriding it makes sync fail.
    def test_a_repos_own_ssh_command_is_used(self):
        marker, script = self.tmp / "ssh-used", self.tmp / "fake-ssh.sh"
        script.write_text(f"#!/bin/sh\ntouch '{marker.as_posix()}'\nexit 1\n", encoding="utf-8")
        script.chmod(0o755)
        subprocess.run(["git", "-C", str(self.laptop), "config", "core.sshCommand", f"sh '{script.as_posix()}'"], check=True)
        subprocess.run(["git", "-C", str(self.laptop), "remote", "set-url", "origin", "ssh://nobody@127.0.0.1/remote.git"], check=True)
        (self.laptop / "memory/fact.md").write_text("x\n", encoding="utf-8")
        env = {k: v for k, v in os.environ.items() if k != "GIT_SSH_COMMAND"}
        subprocess.run([sys.executable, str(self.laptop / "hooks/bindle_hook.py"), "session-end"], capture_output=True,
                       env={**env, "CLAUDE_PLUGIN_ROOT": str(self.laptop), "CLAUDE_PROJECT_DIR": str(self.laptop_folder)})
        self.assertTrue(marker.exists())

    # The outbox syncs too, so items prepared on one machine can be collected on another.
    def test_outbox_changes_sync_with_memories(self):
        (self.laptop / "outbox/item").mkdir(parents=True)
        (self.laptop / "outbox/item/memory.md").write_text("general lesson\n", encoding="utf-8")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.assertIn("outbox/item/memory.md", bindle.git(self.remote, "log", "--name-only", "--format="))

    # Both machines add a memory between syncs, so both append to MEMORY.md; the union merge keeps both lines
    # instead of stopping the rebase and leaving one machine's memory unpushed.
    def test_index_lines_added_on_two_machines_both_survive(self):
        for root, folder, n in ((self.laptop, self.laptop_folder, "a"), (self.desktop, self.desktop_folder, "b")):
            (root / f"memory/{n}.md").write_text(f"{n}\n", encoding="utf-8")
            with open(root / "memory/MEMORY.md", "a", encoding="utf-8") as f:
                f.write(f"- [{n}]({n}.md) — from {n}\n")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.hook(self.desktop, self.desktop_folder, "session-end.sh")
        self.hook(self.laptop, self.laptop_folder, "session-start.sh")
        index = (self.laptop / "memory/MEMORY.md").read_text(encoding="utf-8")
        self.assertIn("from a", index)
        self.assertIn("from b", index)
        self.assertEqual(bindle.git(self.desktop, "rev-list", "--count", "@{upstream}..HEAD"), "0")

    # Skills and rules are deliberate commits; auto-sync must not ship half-finished work.
    def test_commits_only_memory(self):
        (self.laptop / "memory/fact.md").write_text("x\n", encoding="utf-8")
        (self.laptop / "skills/draft.md").write_text("half done\n", encoding="utf-8")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.assertIn("skills/draft.md", bindle.git(self.laptop, "status", "--porcelain"))
        self.assertNotIn("draft.md", bindle.git(self.remote, "log", "--name-only", "--format="))

    # A session only writes to its writable bindle, so a read-only one has nothing of its own to push.
    def test_session_end_does_nothing_where_the_bindle_is_read_only(self):
        f = self.folder("elsewhere")
        self.run_cli("attach", self.laptop, f)
        (self.laptop / "memory/fact.md").write_text("x\n", encoding="utf-8")
        self.hook(self.laptop, f, "session-end.sh")
        self.assertIn("memory/fact.md", bindle.git(self.laptop, "status", "--porcelain"))

    def test_does_nothing_when_sync_is_off(self):
        meta = json.loads((self.laptop / "bindle.json").read_text(encoding="utf-8"))
        meta["sync"] = False
        (self.laptop / "bindle.json").write_text(json.dumps(meta), encoding="utf-8")
        (self.laptop / "memory/fact.md").write_text("x\n", encoding="utf-8")
        self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        self.assertIn("memory/fact.md", bindle.git(self.laptop, "status", "--porcelain"))

    # Offline or unreachable remotes must never fail or block a session.
    def test_an_unreachable_remote_never_fails_the_hooks(self):
        subprocess.run(["git", "-C", str(self.laptop), "remote", "set-url", "origin", str(self.tmp / "gone.git")], check=True)
        (self.laptop / "memory/fact.md").write_text("x\n", encoding="utf-8")
        end = self.hook(self.laptop, self.laptop_folder, "session-end.sh")
        start = self.hook(self.laptop, self.laptop_folder, "session-start.sh")
        self.assertEqual((end.returncode, start.returncode), (0, 0))
        self.assertNotIn("Traceback", end.stderr + start.stderr)
        self.assertIn("1 commit(s) not pushed", self.run_cli("doctor", self.laptop_folder)[1])

    # A session killed before SessionEnd leaves commits behind; the next start pushes them.
    def test_session_start_pushes_leftover_commits(self):
        (self.laptop / "memory/fact.md").write_text("x\n", encoding="utf-8")
        bindle.git(self.laptop, "add", "-A")
        bindle.git(self.laptop, "commit", "-q", "-m", "left behind")
        self.hook(self.laptop, self.laptop_folder, "session-start.sh")
        self.assertIn("left behind", bindle.git(self.remote, "log", "--format=%s"))

    # Closing the Claude app can skip SessionEnd; the next session start must not leave those memories behind.
    def test_session_start_commits_memories_a_skipped_session_end_left(self):
        (self.laptop / "memory/loose.md").write_text("written, never committed\n", encoding="utf-8")
        self.hook(self.laptop, self.laptop_folder, "session-start.sh")
        self.assertEqual(bindle.git(self.laptop, "status", "--porcelain"), "")
        self.assertIn("memory/loose.md", bindle.git(self.remote, "log", "--name-only", "--format="))

    def test_bindle_sync_does_the_same_by_hand_even_with_sync_off(self):
        meta = json.loads((self.laptop / "bindle.json").read_text(encoding="utf-8"))
        meta["sync"] = False
        (self.laptop / "bindle.json").write_text(json.dumps(meta), encoding="utf-8")
        bindle.git(self.laptop, "commit", "-qam", "sync off")
        (self.laptop / "memory/fact.md").write_text("x\n", encoding="utf-8")
        code, out = self.run_cli("sync", self.laptop_folder)
        self.assertEqual(code, 0)
        self.assertIn("pushed", out)
        self.assertIn("memory/fact.md", bindle.git(self.remote, "log", "--name-only", "--format="))



class GlobalRulesTest(BindleTest):
    """`bindle global` puts a bindle's rules.md into the user CLAUDE.md, the one place every session and subagent
    reads. That file is the person's own, so outside bindle's block it must never change."""

    def setUp(self):
        super().setUp()
        self.craft = self.make_bindle("craft")
        (self.craft / "rules.md").write_text("Prefer small PRs.\n", encoding="utf-8")
        self.md = self.tmp / "claude-config" / "CLAUDE.md"

    def imports(self):
        return bindle.core.hooks().global_imports(bindle.core.hooks().decode_text(self.md.read_bytes())[0])

    def roots(self):
        return bindle.core.hooks().global_roots(bindle.core.hooks().decode_text(self.md.read_bytes())[0])

    def run_rules(self, b, folder):
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(b), "CLAUDE_PROJECT_DIR": str(folder)}
        return subprocess.run([sys.executable, str(b / "hooks/bindle_hook.py"), "rules"], env=env,
                              capture_output=True, text=True).stdout

    # A first machine may have no user CLAUDE.md (or config folder) yet; global must still work there.
    def test_creates_the_file_when_missing(self):
        self.assertEqual(self.run_cli("global", "craft")[0], 0)
        # The index too: as-needed memories are only reachable when every session sees their index.
        self.assertEqual([str(p) for p in self.imports()],
                         [str(self.craft / "rules.md"), str(self.craft / "memory" / "MEMORY.md")])

    # The person's own instructions live in this file; losing or reformatting a byte of them is silent damage.
    def test_keeps_the_persons_text_byte_for_byte_and_off_restores_it(self):
        for original in ("# Mine\n\nBe brief. Café ✓\n", "# Mine\n\n", "x\n"):
            with self.subTest(original=original):
                self.md.parent.mkdir(exist_ok=True)
                self.md.write_bytes(original.encode("utf-8"))
                self.run_cli("global", "craft")
                self.assertTrue(self.md.read_bytes().startswith(original.encode("utf-8")))
                self.run_cli("global", "craft", "--off")
                self.assertEqual(self.md.read_bytes(), original.encode("utf-8"))

    # People run setup steps again on each machine; a second run must not add a second import or touch the file.
    def test_running_it_twice_changes_nothing(self):
        self.md.parent.mkdir()
        self.md.write_text("mine\n", encoding="utf-8")
        self.run_cli("global", "craft")
        once = self.md.read_bytes()
        code, out = self.run_cli("global", "craft")
        self.assertEqual((code, self.md.read_bytes()), (0, once))
        self.assertIn("already global", out)

    # Turning one bindle off must leave the other's rules loading everywhere.
    def test_two_bindles_share_one_block_and_off_removes_only_one(self):
        personal = self.make_bindle("personal")
        self.run_cli("global", "craft")
        self.run_cli("global", personal)
        self.assertEqual(self.roots(), [self.craft, personal])
        self.assertEqual(self.md.read_text(encoding="utf-8").count("bindle global: start"), 1)
        self.run_cli("global", "craft", "--off")
        self.assertEqual(self.roots(), [personal])

    # Windows editors write CRLF; mixing in LF lines makes the file look changed everywhere in a diff tool.
    def test_a_crlf_file_stays_crlf(self):
        self.md.parent.mkdir()
        self.md.write_bytes(b"one\r\ntwo\r\n")
        self.run_cli("global", "craft")
        data = self.md.read_bytes()
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))
        self.run_cli("global", "craft", "--off")
        self.assertEqual(self.md.read_bytes(), b"one\r\ntwo\r\n")

    # Some Windows editors save UTF-16 with a byte-order mark; rewriting it as UTF-8 would garble the person's text.
    def test_the_files_encoding_is_kept(self):
        self.md.parent.mkdir()
        original = b"\xff\xfe" + "mine é\r\n".encode("utf-16-le")
        self.md.write_bytes(original)
        self.run_cli("global", "craft")
        self.assertTrue(self.md.read_bytes().startswith(original))
        self.assertEqual(self.roots(), [self.craft])
        self.run_cli("global", "craft", "--off")
        self.assertEqual(self.md.read_bytes(), original)

    # A file bindle can't read as text could be anything; rewriting it would destroy it.
    def test_refuses_a_file_it_cant_read_or_a_broken_block(self):
        self.md.parent.mkdir()
        for content in (b"caf\xe9\n", b"<!-- bindle global: start -->\n<!-- bindle global: start -->\n<!-- bindle global: end -->\n"):
            with self.subTest(content=content):
                self.md.write_bytes(content)
                code, out = self.run_cli("global", "craft")
                self.assertEqual(code, 1, out)
                self.assertEqual(self.md.read_bytes(), content)

    # Many people keep ~/.claude/CLAUDE.md as a link into a dotfiles repo; replacing the link would cut it off.
    def test_writes_through_a_linked_claude_md(self):
        real_file = self.tmp / "dotfiles" / "CLAUDE.md"
        real_file.parent.mkdir()
        real_file.write_text("mine\n", encoding="utf-8")
        self.md.parent.mkdir()
        try:
            self.md.symlink_to(real_file)
        except OSError:
            self.skipTest("symlinks need extra rights here")
        self.run_cli("global", "craft")
        self.assertTrue(self.md.is_symlink())
        self.assertIn("craft", real_file.read_text(encoding="utf-8"))

    # A user name with a space (common on Windows) must still give an import Claude Code reads as one path.
    def test_a_path_with_a_space_round_trips(self):
        code, out = self.run_cli("new", "spaced", "--at", self.tmp / "my bindles" / "spaced")
        self.assertEqual(code, 0, out)
        self.run_cli("global", self.tmp / "my bindles" / "spaced")
        self.assertIn("my\\ bindles", self.md.read_text(encoding="utf-8"))
        self.assertTrue(bindle.core.hooks().imported_globally(self.tmp / "my bindles" / "spaced"))

    # Claude Code reads the user CLAUDE.md from $CLAUDE_CONFIG_DIR when it's set, else ~/.claude; writing anywhere
    # else would do nothing.
    def test_finds_the_user_claude_md_where_claude_code_does(self):
        self.assertEqual(bindle.core.hooks().user_claude_md(), self.md)
        os.environ["CLAUDE_CONFIG_DIR"] = ""
        try:
            self.assertEqual(bindle.core.hooks().user_claude_md(), Path.home() / ".claude" / "CLAUDE.md")
        finally:
            os.environ["CLAUDE_CONFIG_DIR"] = self.env["CLAUDE_CONFIG_DIR"]

    # Where a global bindle is also attached, its hook printing rules.md too would load every rule twice;
    # turning global off must bring the hook's copy back, or the rules vanish there.
    def test_the_hook_skips_rules_a_global_import_already_loads(self):
        f = self.folder()
        self.run_cli("attach", "craft", f)
        self.run_cli("global", "craft")
        self.assertEqual(self.run_rules(self.craft, f).strip(), "")
        self.run_cli("global", "craft", "--off")
        self.assertIn("Prefer small PRs.", self.run_rules(self.craft, f))

    # A bindle that moved leaves an import of nothing: its rules silently stop loading in every session.
    def test_doctor_flags_an_import_of_a_bindle_that_moved_and_off_by_path_clears_it(self):
        self.run_cli("global", "craft")
        moved = self.tmp / "bindles" / "craft"
        shutil.move(str(self.craft), str(moved))
        code, out = self.run_cli("doctor", self.folder())
        self.assertEqual(code, 1)
        self.assertIn(f"bindle global --off {bindle.core.quote(str(self.craft))}", out)
        self.assertIn("aren't loading", self.run_cli("session-check", self.folder())[1])
        self.run_cli("global", "--off", self.craft)
        self.assertEqual(self.imports(), [])

    # Where a global bindle is attached read-only, its hook showing the memory index too would load it twice.
    def test_the_hook_skips_a_memory_index_a_global_import_already_loads(self):
        f = self.folder()
        (self.craft / "memory" / "MEMORY.md").write_text("- [small-prs](small-prs.md) — keep PRs small\n", encoding="utf-8")
        self.run_cli("attach", "craft", f)
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(self.craft), "CLAUDE_PROJECT_DIR": str(f)}
        start = lambda: subprocess.run([sys.executable, str(self.craft / "hooks/bindle_hook.py"), "session-start"],
                                       env=env, capture_output=True, text=True).stdout
        self.assertIn("keep PRs small", start())
        self.run_cli("global", "craft")
        self.assertNotIn("keep PRs small", start())

    # 0.29 imported only rules.md; a block left from then keeps craft's memories out of every session, silently.
    def test_doctor_flags_a_block_from_an_older_bindle_and_running_global_again_fixes_it(self):
        self.md.parent.mkdir()
        self.md.write_text(f"mine\n\n{bindle.global_rules.HEADER}\n{bindle.core.hooks().import_line(self.craft / 'rules.md')}\n"
                           f"{bindle.core.hooks().GLOBAL_END}\n", encoding="utf-8")
        code, out = self.run_cli("doctor", self.folder())
        self.assertEqual(code, 1)
        self.assertIn("bindle global craft", out)
        self.run_cli("global", "craft")
        self.assertEqual(len(self.imports()), 2)
        self.assertTrue(self.md.read_text(encoding="utf-8").startswith("mine\n\n"))
        self.assertNotIn("isn't what this bindle writes", self.run_cli("doctor", self.folder())[1])

    # Global rules load into every session and subagent, so their size is paid many times over; but the hook's
    # 10k cap no longer applies, so the attached-rules problem mustn't fire for them.
    def test_doctor_warns_about_a_large_global_rules_md_instead_of_the_hook_cap(self):
        f = self.folder()
        self.run_cli("attach", "craft", f)
        (self.craft / "rules.md").write_text("x" * (bindle.global_rules.GLOBAL_RULES_WARN + 1), encoding="utf-8")
        self.run_cli("global", "craft")
        out = self.run_cli("doctor", f)[1]
        self.assertIn("every session and subagent loads them", out)
        self.assertNotIn("rules.md is over", out)


class GlobalSyncTest(BindleTest):
    """A global bindle's rules load in every folder, but its own hook (and so its pull) runs only where it's
    attached. The session check, which runs in every session, keeps it current, and never writes to it."""

    def setUp(self):
        super().setUp()
        code, out = self.run_cli("new", "craft", "--at", self.tmp / "bindles" / "craft", "--sync", "--writes", "explicit")
        self.assertEqual(code, 0, out)
        self.craft = self.tmp / "bindles" / "craft"
        self.remote = self.tmp / "craft.git"
        subprocess.run(["git", "clone", "-q", "--bare", str(self.craft), str(self.remote)], check=True)
        branch = bindle.git(self.craft, "rev-parse", "--abbrev-ref", "HEAD")
        subprocess.run(["git", "-C", str(self.craft), "remote", "add", "origin", str(self.remote)], check=True)
        subprocess.run(["git", "-C", str(self.craft), "fetch", "-q", "origin"], check=True)
        subprocess.run(["git", "-C", str(self.craft), "branch", "-q", "-u", f"origin/{branch}"], check=True)
        self.other = self.tmp / "other-machine"
        subprocess.run(["git", "clone", "-q", str(self.remote), str(self.other)], check=True)
        self.run_cli("global", "craft")
        self.elsewhere = self.folder("elsewhere")

    def push_rule_from_the_other_machine(self, text):
        (self.other / "rules.md").write_text(text, encoding="utf-8")
        bindle.git(self.other, "commit", "-qam", "new rule")
        bindle.git(self.other, "push", "-q")

    # Without this, a rule added on one machine never reaches the others' sessions until someone pulls by hand.
    def test_a_session_anywhere_pulls_a_global_bindle(self):
        self.push_rule_from_the_other_machine("Write tests first.\n")
        self.run_cli("session-check", self.elsewhere)
        self.assertEqual((self.craft / "rules.md").read_text(encoding="utf-8"), "Write tests first.\n")

    # An explicit-writes bindle is never anyone's writable bindle: the session check must not commit or push to it.
    def test_the_pull_never_commits_or_pushes(self):
        head, remote_head = bindle.git(self.craft, "rev-parse", "HEAD"), bindle.git(self.remote, "rev-parse", "HEAD")
        (self.craft / "memory" / "draft.md").write_text("half done\n", encoding="utf-8")
        self.run_cli("session-check", self.elsewhere)
        self.assertEqual(bindle.git(self.craft, "rev-parse", "HEAD"), head)
        self.assertEqual(bindle.git(self.remote, "rev-parse", "HEAD"), remote_head)

    # A pull that fails leaves old rules in every session; the person must see it in the terminal.
    def test_a_failed_pull_is_shown(self):
        self.push_rule_from_the_other_machine("Remote rule.\n")
        (self.craft / "rules.md").write_text("Local rule.\n", encoding="utf-8")
        bindle.git(self.craft, "commit", "-qam", "local")  # diverged: a fast-forward is impossible
        out = self.run_cli("session-check", self.elsewhere)[1]
        self.assertIn("craft (global) sync problem", out)

    # With sync off nothing pulls it, so the person has to hear that the rules every session follows are stale.
    def test_a_global_bindle_with_sync_off_that_is_behind_is_named(self):
        meta = json.loads((self.craft / "bindle.json").read_text(encoding="utf-8"))
        meta["sync"] = False
        (self.craft / "bindle.json").write_text(json.dumps(meta), encoding="utf-8")
        bindle.git(self.craft, "commit", "-qam", "sync off")
        bindle.git(self.craft, "push", "-q")
        bindle.git(self.other, "pull", "-q")
        self.push_rule_from_the_other_machine("Newer.\n")
        bindle.git(self.craft, "fetch", "-q")
        out = self.run_cli("session-check", self.elsewhere)[1]
        self.assertIn("craft (global) is 1 commit(s) behind", out)
        self.assertIn("behind its remote", self.run_cli("doctor", self.elsewhere)[1])

    # Where it's attached, its own hook pulls it in the same session; two pulls at once would fight over git's lock.
    def test_a_global_bindle_attached_here_is_left_to_its_own_hook(self):
        self.run_cli("attach", "craft", self.elsewhere)
        self.push_rule_from_the_other_machine("Not yet.\n")
        self.run_cli("session-check", self.elsewhere)
        self.assertNotEqual((self.craft / "rules.md").read_text(encoding="utf-8"), "Not yet.\n")


if __name__ == "__main__":
    unittest.main()
