"""Serving compatibility must not admit other PyTorch releases or builds."""
import unittest
from bibleprep.chat_model import compatible_chat_torch


class RuntimePortabilityTests(unittest.TestCase):
    def test_same_release_and_official_linux_cpu_build(self):
        self.assertTrue(compatible_chat_torch("2.14.0", "2.14.0", "darwin"))
        self.assertTrue(compatible_chat_torch("2.14.0+cpu", "2.14.0", "linux"))

    def test_cpu_allowance_is_narrow(self):
        for installed, recorded, platform in [
            ("2.14.0+cpu", "2.14.0", "darwin"),
            ("2.14.1+cpu", "2.14.0", "linux"),
            ("2.14.0+cu128", "2.14.0", "linux"),
            ("2.15.0", "2.14.0", "linux"),
            ("2.15.0+cpu", "2.15.0", "linux"),
        ]:
            with self.subTest(installed=installed, recorded=recorded, platform=platform):
                self.assertFalse(compatible_chat_torch(installed, recorded, platform))
