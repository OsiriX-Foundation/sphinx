import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
import unittest


class RecoveryDrillPreflightTests(unittest.TestCase):
    def test_inventory_failure_stops_before_starting_project(self):
        drill = Path(__file__).resolve().parents[1] / "scripts" / "recovery-drill.sh"
        for failing_command in ("ps", "volume"):
            with self.subTest(command=failing_command), TemporaryDirectory() as root:
                workspace = Path(root)
                (workspace / "scripts").mkdir()
                (workspace / "data").mkdir()
                shutil.copyfile(drill, workspace / "scripts" / drill.name)
                docker = workspace / "docker"
                docker.write_text(
                    '#!/bin/sh\n'
                    '[ "$1" != "$FAIL_COMMAND" ] || exit 42\n'
                    'case "$*" in *"config --quiet"|"ps "*|"volume ls "*) exit 0 ;; esac\n'
                    'echo "Unexpected invocation: $*" >&2\n'
                    'exit 99\n'
                )
                docker.chmod(0o755)
                env = {**os.environ, "PATH": f"{workspace}{os.pathsep}{os.environ['PATH']}",
                       "FAIL_COMMAND": failing_command}
                result = subprocess.run(
                    ["bash", workspace / "scripts" / drill.name],
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=10,
                )
                self.assertEqual(result.returncode, 42, result.stderr)
