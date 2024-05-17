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


@pytest.fixture(scope="function", name="build_image_inputs")
def build_image_inputs_fixture(callback_path: Path):
    """Valid CLI inputs."""
    return {"-i": "jammy", "-c": "test-cloud-name", "-n": "5", "-p": str(callback_path)}


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


def test__install(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched builder.setup_builder function.
    act: when _install is called.
    assert: the mock function is called.
    """
    monkeypatch.setattr(cli.builder, "setup_builder", (setup_mock := MagicMock()))

    cli._install()

    setup_mock.assert_called_once()


def test__build(monkeypatch: pytest.MonkeyPatch, callback_path: Path):
    """
    arrange: given a monkeypatched builder.setup_builder function.
    act: when _build is called.
    assert: the mock function is called.
    """
    monkeypatch.setattr(cli.builder, "build_image", (builder_mock := MagicMock()))
    monkeypatch.setattr(
        cli, "OpenstackManager", MagicMock(return_value=(openstack_manager := MagicMock()))
    )

    cli._build_and_upload(
        base="jammy",
        cloud_name=MagicMock(),
        num_revisions=MagicMock(),
        callback_script_path=callback_path,
    )

    builder_mock.assert_called_once()
    openstack_manager.upload_image.assert_called_once()


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
    monkeypatch.setattr(cli, "_install", (install_mock := MagicMock()))
    monkeypatch.setattr(cli, "_build_and_upload", (build_mock := MagicMock()))

    with pytest.raises(SystemExit):
        main([choice])

    install_mock.assert_not_called()
    build_mock.assert_not_called()


def test_main_install(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given install argument and mocked builder functions.
    act: when main is called.
    assert: Setup builder mock function is called.
    """
    monkeypatch.setattr(cli, "_install", (install_mock := MagicMock()))
    monkeypatch.setattr(cli, "_build_and_upload", (build_mock := MagicMock()))

    main(["install"])

    install_mock.assert_called()
    build_mock.assert_not_called()


@pytest.mark.parametrize(
    "invalid_patch",
    [
        pytest.param({"-i": ""}, id="no base-image"),
        pytest.param({"-i": "test"}, id="invalid base-image"),
        pytest.param({"-o": ""}, id="empty output"),
    ],
)
def test_main_invalid_build_inputs(
    monkeypatch: pytest.MonkeyPatch,
    build_image_inputs: dict[str, str],
    invalid_patch: dict[str, str],
):
    """
    arrange: given invalid build arguments and mocked builder functions.
    act: when main is called.
    assert: SystemExit is raised.
    """
    monkeypatch.setattr(cli, "_install", (install_mock := MagicMock()))
    monkeypatch.setattr(cli, "_build_and_upload", (build_mock := MagicMock()))
    build_image_inputs.update(invalid_patch)
    inputs = list(
        itertools.chain.from_iterable(
            (flag, value) for (flag, value) in build_image_inputs.items()
        )
    )

    with pytest.raises(SystemExit):
        main(["build", *inputs])

    install_mock.assert_not_called()
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
def test_main_base_image(
    monkeypatch: pytest.MonkeyPatch, image: str, build_image_inputs: dict[str, str]
):
    """
    arrange: given invalid base_image argument and mocked builder functions.
    act: when main is called.
    assert: build image is called.
    """
    monkeypatch.setattr(cli, "_install", (install_mock := MagicMock()))
    monkeypatch.setattr(cli, "_build_and_upload", (build_mock := MagicMock()))
    build_image_inputs.update({"-i": image})
    inputs = list(
        itertools.chain.from_iterable(
            (flag, value) for (flag, value) in build_image_inputs.items()
        )
    )

    main(["build", *inputs])

    install_mock.assert_not_called()
    build_mock.assert_called()
