from pathlib import Path
from unittest.mock import Mock

import pytest
from dbt.cli.main import (
    dbtRunnerResult,
)

from tendergraph.pipeline.dbt import (
    run_dbt_build,
)


def dbt_files(
    tmp_path: Path,
) -> tuple[
    Path,
    Path,
]:
    project_dir = (
        tmp_path
        / "project"
    )

    profiles_dir = (
        tmp_path
        / "profiles"
    )

    project_dir.mkdir()
    profiles_dir.mkdir()

    (
        project_dir
        / "dbt_project.yml"
    ).write_text(
        "name: test\n"
    )

    (
        profiles_dir
        / "profiles.yml"
    ).write_text(
        "test: {}\n"
    )

    return (
        project_dir,
        profiles_dir,
    )


def test_run_dbt_build_success(
    tmp_path: Path,
) -> None:
    (
        project_dir,
        profiles_dir,
    ) = dbt_files(
        tmp_path
    )

    runner = Mock()

    runner.invoke.return_value = (
        dbtRunnerResult(
            success=True,
            exception=None,
            result=["model.a"],
        )
    )

    summary = run_dbt_build(
        project_dir=project_dir,
        profiles_dir=profiles_dir,
        runner=runner,
    )

    runner.invoke.assert_called_once_with(
        [
            "build",
            "--project-dir",
            str(project_dir),
            "--profiles-dir",
            str(profiles_dir),
        ]
    )

    assert summary.success
    assert summary.command[0:2] == (
        "dbt",
        "build",
    )
    assert (
        summary.elapsed_seconds
        >= 0
    )
    assert (
        summary.result_type
        == "list"
    )


def test_run_dbt_build_raises_attached_exception(
    tmp_path: Path,
) -> None:
    (
        project_dir,
        profiles_dir,
    ) = dbt_files(
        tmp_path
    )

    runner = Mock()

    underlying = ValueError(
        "database unavailable"
    )

    runner.invoke.return_value = (
        dbtRunnerResult(
            success=False,
            exception=underlying,
            result=None,
        )
    )

    with pytest.raises(
        RuntimeError,
        match="dbt build failed",
    ) as caught:
        run_dbt_build(
            project_dir=project_dir,
            profiles_dir=profiles_dir,
            runner=runner,
        )

    assert (
        caught.value.__cause__
        is underlying
    )


def test_run_dbt_build_rejects_failure_without_exception(
    tmp_path: Path,
) -> None:
    (
        project_dir,
        profiles_dir,
    ) = dbt_files(
        tmp_path
    )

    runner = Mock()

    runner.invoke.return_value = (
        dbtRunnerResult(
            success=False,
            exception=None,
            result=None,
        )
    )

    with pytest.raises(
        RuntimeError,
        match="without an attached exception",
    ):
        run_dbt_build(
            project_dir=project_dir,
            profiles_dir=profiles_dir,
            runner=runner,
        )


def test_run_dbt_build_requires_project_file(
    tmp_path: Path,
) -> None:
    profiles_dir = (
        tmp_path
        / "profiles"
    )

    profiles_dir.mkdir()

    (
        profiles_dir
        / "profiles.yml"
    ).write_text(
        "test: {}\n"
    )

    with pytest.raises(
        FileNotFoundError,
        match="dbt project",
    ):
        run_dbt_build(
            project_dir=(
                tmp_path
                / "missing"
            ),
            profiles_dir=profiles_dir,
            runner=Mock(),
        )
