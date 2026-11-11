"""Clean-source builds and the exact installable artifact, using owned temporary files."""

import hashlib
import importlib.util
from pathlib import Path
import subprocess
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("build_release", ROOT / "scripts/build-release.py")
BUILDER = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BUILDER)


class SourceSnapshotTests(unittest.TestCase):
    def setUp(self):
        self.owned = tempfile.TemporaryDirectory(prefix="askweft-source-fixture-")
        self.addCleanup(self.owned.cleanup)
        self.path = Path(self.owned.name)
        self.repository = self.path / "repository"
        self.repository.mkdir()
        self.git("init", "-q")
        self.git("config", "core.autocrlf", "false")
        (self.repository / ".gitattributes").write_bytes(b"* text eol=lf\n")
        (self.repository / ".gitignore").write_bytes(b"ignored*\n")
        (self.repository / "source.txt").write_bytes(b"Exact source bytes\n")
        self.commit()
        self.destination = self.path / "snapshot"
        self.destination.mkdir()

    def git(self, *arguments):
        return subprocess.check_output(
            ["git", *arguments], cwd=self.repository, stderr=subprocess.PIPE
        )

    def commit(self):
        self.git("add", ".")
        self.git(
            "-c",
            "user.name=Askweft test fixture",
            "-c",
            "user.email=248948303+bglglzd@users.noreply.github.com",
            "commit",
            "-q",
            "-m",
            "Synthetic source fixture",
        )

    def snapshot(self):
        with patch.object(BUILDER, "ROOT", self.repository):
            return BUILDER.snapshot(self.destination)

    def test_committed_inventory_ignores_local_ignored_files(self):
        (self.repository / "ignored-local.py").write_bytes(b"Not part of the source commit\n")
        sha, tree, rows = self.snapshot()
        self.assertEqual(sha, self.git("rev-parse", "HEAD").decode().strip())
        self.assertEqual(tree, self.git("rev-parse", "HEAD^{tree}").decode().strip())
        self.assertEqual(
            {row["path"] for row in rows}, {".gitattributes", ".gitignore", "source.txt"}
        )
        for row in rows:
            data = (self.destination / row["path"]).read_bytes()
            self.assertEqual(row["bytes"], len(data))
            self.assertEqual(row["sha256"], hashlib.sha256(data).hexdigest())

    def test_hidden_working_change_and_untracked_source_are_refused(self):
        (self.repository / "source.txt").write_bytes(b"Hidden change\n")
        self.git("update-index", "--assume-unchanged", "--", "source.txt")
        self.assertEqual(self.git("status", "--porcelain"), b"")
        with self.assertRaisesRegex(ValueError, "Working bytes differ"):
            self.snapshot()
        self.git("update-index", "--no-assume-unchanged", "--", "source.txt")
        self.git("checkout", "--", "source.txt")
        (self.repository / "untracked.py").write_bytes(b"Not committed\n")
        with self.assertRaisesRegex(ValueError, "clean checkout"):
            self.snapshot()

    def test_git_link_entries_are_refused(self):
        # Git's index can represent a symlink even where creating one needs OS privilege.
        target = self.path / "link-target"
        target.write_bytes(b"outside")
        blob = self.git("hash-object", "-w", str(target)).decode().strip()
        self.git("update-index", "--add", "--cacheinfo", "120000," + blob + ",link")
        self.git(
            "-c",
            "user.name=Askweft test fixture",
            "-c",
            "user.email=248948303+bglglzd@users.noreply.github.com",
            "commit",
            "-q",
            "-m",
            "Synthetic symlink fixture",
        )
        self.git("config", "core.symlinks", "false")
        self.git("checkout", "--", "link")
        self.assertEqual(self.git("status", "--porcelain"), b"")
        # Snapshot reads the committed modes independently of the local OS link support.
        with self.assertRaisesRegex(ValueError, "symlinks or submodules"):
            self.snapshot()

    def test_changed_build_configuration_and_wrong_tool_versions_refuse_before_output(self):
        (self.repository / "pyproject.toml").write_text(
            '[project]\nname="askweft"\nversion="0.1.0"\n'
            '[build-system]\nrequires=["unaccepted-backend"]\n'
            'build-backend="setuptools.build_meta"\n',
            encoding="utf-8",
            newline="\n",
        )
        self.commit()
        output = self.path / "candidate"
        with patch.object(BUILDER, "ROOT", self.repository):
            with self.assertRaisesRegex(ValueError, "build configuration"):
                BUILDER.build(output)
            with patch.object(BUILDER, "installed_version", return_value="0.0.0"):
                with self.assertRaisesRegex(ValueError, "exact build tools"):
                    BUILDER.build(output)
        self.assertFalse(output.exists())
