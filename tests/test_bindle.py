"""Tests for bin/bindle. Run: python3 -m unittest discover -s tests

`claude` is replaced by tests/fake_claude, so nothing here touches the machine's real plugin state.
tests/e2e.sh runs the same flow against the real CLI."""
import contextlib
import importlib.machinery
import importlib.util
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HERE = Path(__file__).resolve().parent
loader = importlib.machinery.SourceFileLoader("bindle_cli", str(HERE.parent / "bin" / "bindle"))
spec = importlib.util.spec_from_loader("bindle_cli", loader)
bindle = importlib.util.module_from_spec(spec)
loader.exec_module(bindle)


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
        self.assertEqual(json.loads((b / "bindle.json").read_text()), {"name": "acme", "layout": 1})
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
        self.assertTrue(os.access(b / "hooks/print-memory.sh", os.X_OK))

    def test_commits_but_never_sets_a_remote(self):
        b = self.make_bindle("acme")
        self.assertIsNotNone(bindle.git(b, "rev-parse", "HEAD"))
        self.assertEqual(bindle.git(b, "remote"), "")

    def test_refuses_a_bad_name_or_a_non_empty_folder(self):
        self.assertEqual(self.run_cli("new", "Acme Corp", "--at", self.tmp / "x")[0], 1)
        self.make_bindle("acme")
        self.assertEqual(self.run_cli("new", "acme", "--at", self.tmp / "bindle-acme")[0], 1)


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

    def test_accepts_the_writeable_spelling_too(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.assertEqual(self.run_cli("attach", b, f, "--writeable")[0], 0)
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
        self.assertIn("personal: on\n", out)

    def test_flags_a_hook_that_drifted_from_the_template(self):
        b, f = self.make_bindle("acme"), self.folder()
        self.run_cli("attach", b, f)
        with open(b / "hooks/print-memory.sh", "a") as h:
            h.write("# local edit\n")
        code, out = self.run_cli("doctor", f)
        self.assertEqual(code, 1)
        self.assertIn("print-memory.sh differs", out)

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
        self.assertIn("attach it again", out)
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
        self.saved_home = os.environ.get("HOME")
        os.environ["HOME"] = str(self.home)

    def tearDown(self):
        os.environ["HOME"] = self.saved_home
        super().tearDown()

    def test_links_the_cli_and_the_command_and_nothing_else(self):
        self.assertEqual(self.run_cli("install")[0], 0)
        self.assertEqual(os.readlink(self.home / ".local/bin/bindle"), str(bindle.BASE / "bin/bindle"))
        self.assertTrue((self.home / ".claude/commands/bindle.md").is_symlink())
        self.assertEqual(sorted(p.name for p in (self.home / ".claude").iterdir()), ["commands"])

    # A real file there is the person's own; replacing it would lose their work.
    def test_refuses_to_replace_a_real_file(self):
        (self.home / ".claude/commands").mkdir(parents=True)
        (self.home / ".claude/commands/bindle.md").write_text("mine")
        self.assertEqual(self.run_cli("install")[0], 1)
        self.assertEqual((self.home / ".claude/commands/bindle.md").read_text(), "mine")
        self.assertFalse((self.home / ".local/bin/bindle").exists())


class MemoryHookTest(BindleTest):
    """Runs the real hook script: it decides whether a session sees this bindle's memory twice."""

    def run_hook(self, b, folder):
        env = {**os.environ, "CLAUDE_PLUGIN_ROOT": str(b), "CLAUDE_PROJECT_DIR": str(folder)}
        return subprocess.run([str(b / "hooks/print-memory.sh")], env=env, capture_output=True, text=True).stdout

    def test_prints_the_index_where_the_bindle_is_read_only(self):
        b, f = self.make_bindle("personal"), self.folder()
        (b / "memory/MEMORY.md").write_text("- [Fact](fact.md) — a personal fact\n")
        self.run_cli("attach", b, f)
        out = self.run_hook(b, f)
        self.assertIn("Memory index from the personal bindle", out)
        self.assertIn("a personal fact", out)

    def test_stays_quiet_where_the_bindle_is_writable(self):
        b, f = self.make_bindle("personal"), self.folder()
        (b / "memory/MEMORY.md").write_text("- [Fact](fact.md) — a personal fact\n")
        self.run_cli("attach", b, f, "--writable")
        self.assertEqual(self.run_hook(b, f), "")

    def test_stays_quiet_when_there_are_no_memories(self):
        b, f = self.make_bindle("personal"), self.folder()
        self.run_cli("attach", b, f)
        self.assertEqual(self.run_hook(b, f), "")


if __name__ == "__main__":
    unittest.main()
