"""Exercise the real shell wrapper without Docker, uv, or external requests."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.parametrize("exit_code", [0, 7])
def test_wrapper_logs_and_preserves_refresh_exit(tmp_path: Path, exit_code: int) -> None:
    root = tmp_path / "project"
    scripts = root / "scripts"
    scripts.mkdir(parents=True)
    wrapper = scripts / "run_scheduled_refresh.sh"
    shutil.copyfile("scripts/run_scheduled_refresh.sh", wrapper)
    (root / ".env").write_text("# fixture, no credentials\n")
    home = tmp_path / "home"
    binaries = home / ".local" / "bin"
    binaries.mkdir(parents=True)
    for name, result in (("docker", 0), ("uv", exit_code)):
        executable = binaries / name
        executable.write_text(f"#!/bin/bash\nexit {result}\n")
        executable.chmod(0o755)
    result = subprocess.run(
        ["bash", str(wrapper)], env={**os.environ, "HOME": str(home)},
        capture_output=True, text=True, timeout=10, check=False,
    )
    assert result.returncode == exit_code
    assert f"Exit:     {exit_code}" in result.stdout
    assert "Finished:" in result.stdout
