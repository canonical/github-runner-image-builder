# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for cli module."""

# Need access to protected functions for testing
# pylint:disable=protected-access

import itertools
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from github_runner_image_builder import cli
from github_runner_image_builder.cli import main


@pytest.fixture(scope="function", name="callback_path")
def callback_path_fixture(tmp_path: Path):
    """The testing callback file path."""
    test_path = tmp_path / "test"
    test_path.touch()
    return test_path


@pytest.fixture(scope="function", name="run_inputs")
def run_inputs_fixture(callback_path: Path):
    """Valid CLI run mode inputs."""
    return {
        "": "test-cloud-name",
        " ": "test-image-name",
        "--base-image": "noble",
        "--keep-revisions": "5",
        "--callback-script": str(callback_path),
    }


def test__existing_path(tmp_path: Path):
    """
    arrange: given a path that does not exist.
    act: when _existing_path is called.
    assert: ValueError is raised.
    """
    not_exists_path = tmp_path / "non-existent"
    with pytest.raises(ValueError) as exc:
        cli._existing_path(str(not_exists_path))

    assert f"Given path {not_exists_path} not found." in str(exc.getrepr())


@pytest.mark.parametrize(
    "callback_script",
    [
        pytest.param(None, id="No callback script"),
        pytest.param(Path("tmp_path"), id="Callback script"),
    ],
)
def test__build_and_upload(monkeypatch: pytest.MonkeyPatch, callback_script: Path | None):
    """
    arrange: given a monkeypatched builder.setup_builder function.
    act: when _build is called.
    assert: the mock function is called.
    """
    monkeypatch.setattr(cli.builder, "build_image", (builder_mock := MagicMock()))
    monkeypatch.setattr(cli.store, "upload_image", MagicMock(return_value="test-image-id"))
    monkeypatch.setattr(cli.subprocess, "check_call", MagicMock())

    cli._build_and_upload(
        base="jammy",
        cloud_name=MagicMock(),
        image_name=MagicMock(),
        keep_revisions=MagicMock(),
        callback_script_path=callback_script,
    )

    builder_mock.assert_called_once()


@pytest.mark.parametrize(
    "choice",
    [
        pytest.param("", id="no choice"),
        pytest.param("invalid", id="invalid choice"),
    ],
)
def test_main_invalid_choice(monkeypatch: pytest.MonkeyPatch, choice: str):
    """
    arrange: given invalid argument choice and mocked builder functions.
    act: when main is called.
    assert: SystemExit is raised and mocked builder functions are not called.
    """
    monkeypatch.setattr(cli.builder, "initialize", (initialize_mock := MagicMock()))
    monkeypatch.setattr(cli.store, "get_latest_build_id", (get_mock := MagicMock()))
    monkeypatch.setattr(cli, "_build_and_upload", (build_mock := MagicMock()))

    with pytest.raises(SystemExit):
        main([choice])

    initialize_mock.assert_not_called()
    get_mock.assert_not_called()
    build_mock.assert_not_called()


def test_main_init(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given init argument and mocked builder functions.
    act: when main is called.
    assert: initialize builder mock function is called.
    """
    monkeypatch.setattr(cli.builder, "initialize", (initialize_mock := MagicMock()))
    monkeypatch.setattr(cli.store, "get_latest_build_id", (get_mock := MagicMock()))
    monkeypatch.setattr(cli, "_build_and_upload", (build_mock := MagicMock()))

    main(["init"])

    initialize_mock.assert_called()
    get_mock.assert_not_called()
    build_mock.assert_not_called()


def test_main_latest_build_id(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given latest-build-id argument and mocked builder functions.
    act: when main is called.
    assert: get mock function is called.
    """
    monkeypatch.setattr(cli.builder, "initialize", (initialize_mock := MagicMock()))
    monkeypatch.setattr(cli.store, "get_latest_build_id", (get_mock := MagicMock()))
    monkeypatch.setattr(cli, "_build_and_upload", (build_mock := MagicMock()))

    main(["latest-build-id", "test-cloud", "test-image"])

    initialize_mock.assert_not_called()
    get_mock.assert_called()
    build_mock.assert_not_called()


@pytest.mark.parametrize(
    "invalid_patch",
    [
        pytest.param({"--base-image": ""}, id="no base-image"),
        pytest.param({"--base-image": "test"}, id="invalid base-image"),
        pytest.param({"": ""}, id="empty cloud name positional argument"),
        pytest.param({" ": ""}, id="empty image name positional argument"),
    ],
)
def test_main_invalid_run_inputs(
    monkeypatch: pytest.MonkeyPatch,
    run_inputs: dict[str, str],
    invalid_patch: dict[str, str],
):
    """
    arrange: given invalid run arguments and mocked builder functions.
    act: when main is called.
    assert: SystemExit is raised.
    """
    monkeypatch.setattr(cli.builder, "initialize", (initialize_mock := MagicMock()))
    monkeypatch.setattr(cli.store, "get_latest_build_id", (get_mock := MagicMock()))
    monkeypatch.setattr(cli, "_build_and_upload", (build_mock := MagicMock()))
    run_inputs.update(invalid_patch)
    inputs = list(
        # if flag does not exist, append it as a positional argument.
        itertools.chain.from_iterable(
            (flag, value) if flag.strip() else (value,) for (flag, value) in run_inputs.items()
        )
    )

    with pytest.raises(SystemExit):
        main(["run", *inputs])

    initialize_mock.assert_not_called()
    get_mock.assert_not_called()
    build_mock.assert_not_called()


@pytest.mark.parametrize(
    "image",
    [
        pytest.param("jammy", id="jammy"),
        pytest.param("22.04", id="jammy tag"),
        pytest.param("noble", id="noble"),
        pytest.param("24.04", id="noble tag"),
    ],
)
def test_main_run(monkeypatch: pytest.MonkeyPatch, image: str, run_inputs: dict[str, str]):
    """
    arrange: given invalid run argument and mocked builder functions.
    act: when main is called.
    assert: run is called.
    """
    monkeypatch.setattr(cli.builder, "initialize", (initialize_mock := MagicMock()))
    monkeypatch.setattr(cli.store, "get_latest_build_id", (get_mock := MagicMock()))
    monkeypatch.setattr(cli, "_build_and_upload", (build_mock := MagicMock()))
    run_inputs.update({"--base-image": image})
    inputs = list(
        # if flag does not exist, append it as a positional argument.
        itertools.chain.from_iterable(
            (flag, value) if flag.strip() else (value,) for (flag, value) in run_inputs.items()
        )
    )

    main(["run", *inputs])

    initialize_mock.assert_not_called()
    get_mock.assert_not_called()
    build_mock.assert_called()
