#!/usr/bin/env python3

import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sim-build.sh"


class SimulatorBuildScriptTest(unittest.TestCase):
    def test_help_exposes_reproducible_release_build_options(self) -> None:
        result = subprocess.run(
            ["bash", str(SCRIPT), "--help"],
            cwd=ROOT,
            check=True,
            capture_output=True,
            text=True,
        )

        self.assertIn('--configuration "Release"', result.stdout)
        self.assertIn('--build-number "237"', result.stdout)

    def test_release_build_uses_local_dependency_copy_not_symlink(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('NODE_MODULES_SOURCE="$(cd "${ROOT}/mobile/node_modules" && pwd -P)"', script)
        self.assertIn('cp -cR "${NODE_MODULES_SOURCE}"', script)
        self.assertNotIn('ln -s "${ROOT}/mobile/node_modules"', script)


if __name__ == "__main__":
    unittest.main()
