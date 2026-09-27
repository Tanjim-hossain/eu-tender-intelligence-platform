from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

from dbt.cli.main import (
    dbtRunner,
)

DEFAULT_DBT_PROJECT_DIR = Path("dbt")
DEFAULT_DBT_PROFILES_DIR = Path("dbt")


@dataclass(frozen=True, slots=True)
class DbtBuildSummary:
    success: bool
    command: tuple[str, ...]
    elapsed_seconds: float
    result_type: str


def run_dbt_build(
    *,
    project_dir: Path = DEFAULT_DBT_PROJECT_DIR,
    profiles_dir: Path = DEFAULT_DBT_PROFILES_DIR,
    runner: dbtRunner | None = None,
) -> DbtBuildSummary:
    """Build and test the TenderGraph dbt project."""

    project_file = (
        project_dir
        / "dbt_project.yml"
    )

    profiles_file = (
        profiles_dir
        / "profiles.yml"
    )

    if not project_file.is_file():
        raise FileNotFoundError(
            "dbt project file not found: "
            f"{project_file}"
        )

    if not profiles_file.is_file():
        raise FileNotFoundError(
            "dbt profiles file not found: "
            f"{profiles_file}"
        )

    args = [
        "build",
        "--project-dir",
        str(project_dir),
        "--profiles-dir",
        str(profiles_dir),
    ]

    active_runner = (
        runner
        if runner is not None
        else dbtRunner()
    )

    started = perf_counter()

    try:
        result = active_runner.invoke(
            args
        )
    except Exception as exc:
        raise RuntimeError(
            "dbt build invocation failed"
        ) from exc

    elapsed_seconds = (
        perf_counter()
        - started
    )

    if not result.success:
        if result.exception is not None:
            raise RuntimeError(
                "dbt build failed"
            ) from result.exception

        raise RuntimeError(
            "dbt build failed without "
            "an attached exception"
        )

    return DbtBuildSummary(
        success=True,
        command=(
            "dbt",
            *args,
        ),
        elapsed_seconds=(
            elapsed_seconds
        ),
        result_type=type(
            result.result
        ).__name__,
    )
