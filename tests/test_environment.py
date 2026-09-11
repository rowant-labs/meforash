import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from bibleprep import environment


class ProjectEnvironmentTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.parent = Path(temporary.name)
        self.project = self.parent / "project"
        self.project.mkdir()
        root_patch = patch.object(environment, "PROJECT_ROOT", self.project)
        root_patch.start()
        self.addCleanup(root_patch.stop)
        env_patch = patch.dict(os.environ, {}, clear=True)
        env_patch.start()
        self.addCleanup(env_patch.stop)

    def test_loads_repo_file_and_preserves_exported_values(self):
        (self.project / ".env").write_text(
            "TINKER_API_KEY=fixture-file-key\nGROQ_API_KEY=fixture-groq-key\n", encoding="utf-8"
        )
        os.environ["TINKER_API_KEY"] = "fixture-exported-key"
        self.assertTrue(environment.load_project_environment())
        self.assertEqual(os.environ["TINKER_API_KEY"], "fixture-exported-key")
        self.assertEqual(os.environ["GROQ_API_KEY"], "fixture-groq-key")

    def test_missing_project_file_never_searches_parent(self):
        (self.parent / ".env").write_text("TINKER_API_KEY=fixture-parent-key\n", encoding="utf-8")
        self.assertFalse(environment.load_project_environment())
        self.assertNotIn("TINKER_API_KEY", os.environ)

    def test_values_are_not_interpolated_or_run_as_shell(self):
        (self.project / ".env").write_text(
            "SOURCE=fixture-value\nTINKER_API_KEY=${SOURCE}\n"
            "GROQ_API_KEY=$(touch dotenv-should-never-run)\n"
            "FIREWORKS_API_KEY=`touch dotenv-should-never-run`\n", encoding="utf-8"
        )
        with patch("os.system", side_effect=AssertionError("No shell execution")):
            environment.load_project_environment()
        self.assertEqual(os.environ["TINKER_API_KEY"], "${SOURCE}")
        self.assertEqual(os.environ["GROQ_API_KEY"], "$(touch dotenv-should-never-run)")
        self.assertEqual(os.environ["FIREWORKS_API_KEY"], "`touch dotenv-should-never-run`")

    def test_even_empty_exported_value_has_precedence(self):
        (self.project / ".env").write_text("TINKER_API_KEY=fixture-file-key\n", encoding="utf-8")
        os.environ["TINKER_API_KEY"] = ""
        environment.load_project_environment()
        self.assertEqual(os.environ["TINKER_API_KEY"], "")

    def test_symlink_cannot_load_a_file_outside_checkout(self):
        outside = self.parent / "outside.env"
        outside.write_text("TINKER_API_KEY=fixture-outside-key\n", encoding="utf-8")
        (self.project / ".env").symlink_to(outside)
        with self.assertRaises(ValueError):
            environment.load_project_environment()
        self.assertNotIn("TINKER_API_KEY", os.environ)


if __name__ == "__main__":
    unittest.main()
