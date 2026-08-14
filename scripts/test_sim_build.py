#!/usr/bin/env python3

import json
import importlib.util
import subprocess
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "sim-build.sh"
NESTED_SCRIPT = ROOT / "mobile" / "scripts" / "sim-build.sh"
PACKAGE_JSON = ROOT / "mobile" / "package.json"
RESOLVER = ROOT / "scripts" / "resolve_ios_simulator.py"


def _resolver_module():
    spec = importlib.util.spec_from_file_location("resolve_ios_simulator", RESOLVER)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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

    def test_npm_and_nested_entrypoints_delegate_to_guarded_root_wrapper(self) -> None:
        package = json.loads(PACKAGE_JSON.read_text(encoding="utf-8"))
        nested = NESTED_SCRIPT.read_text(encoding="utf-8")

        self.assertEqual(package["scripts"]["ios"], "../scripts/sim-build.sh --current-tree")
        self.assertIn('exec "${ROOT_WRAPPER}" --current-tree --device "${SIM}"', nested)
        self.assertNotIn("expo run:ios", nested)
        self.assertNotIn("pod install", nested)

    def test_physical_name_and_udid_never_reach_expo(self) -> None:
        resolver = _resolver_module()
        payload = {
            "devices": {
                "runtime": [
                    {
                        "name": "iPhone 17 Pro",
                        "udid": "SIMULATOR-UDID",
                        "isAvailable": True,
                    }
                ]
            },
            "decoy": "Suntice iPhone PHYSICAL-DEVICE-UDID",
        }

        for destination in ("iPhone", "Suntice iPhone", "PHYSICAL-DEVICE-UDID"):
            with self.assertRaises(ValueError):
                resolver.resolve_available_simulator(payload, destination)

    def test_exact_simulator_name_resolves_to_udid_before_expo(self) -> None:
        resolver = _resolver_module()
        payload = {
            "devices": {
                "runtime": [
                    {
                        "name": "iPhone 17 Pro",
                        "udid": "SIMULATOR-UDID",
                        "isAvailable": True,
                    }
                ]
            }
        }
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertEqual(
            resolver.resolve_available_simulator(payload, "iPhone 17 Pro"),
            "SIMULATOR-UDID",
        )
        self.assertIn('DEVICE="${RESOLVED_SIMULATOR_UDID}"', script)
        self.assertIn('--device "${DEVICE}"', script)
        self.assertIn("/usr/bin/xcrun simctl list devices available --json", script)
        self.assertNotIn("REVA_SIMCTL_RUNNER_FOR_TESTS", script)
        self.assertNotIn('simctl list devices available | grep', script)


if __name__ == "__main__":
    unittest.main()
