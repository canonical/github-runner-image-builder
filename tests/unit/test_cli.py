# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for cli module."""

# Need access to protected functions for testing
# pylint:disable=protected-access

import itertools
from unittest.mock import MagicMock

import pytest

from github_runner_image_builder import cli
from github_runner_image_builder.cli import main


@pytest.fixture(scope="function", name="build_image_inputs")
def build_image_inputs_fixture():
    """Valid CLI inputs."""
    return {
        "-i": "jammy",
        "-r": "5",
        "-c": "sunbeam",
        "-n": "jammy-github-runner-arm64",
    }


@pytest.fixture(scope="function", name="get_latest_inputs")
def get_latest_inputs_fixture():
    """Valid CLI inputs."""
    return {
        "-c": "sunbeam",
        "-n": "jammy-github-runner-arm64",
    }


def test__install(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched builder.setup_builder function.
    act: when _install is called.
    assert: the mock function is called.
    """
    monkeypatch.setattr(cli.builder, "setup_builder", (setup_mock := MagicMock()))

    cli._install()

    setup_mock.assert_called_once()


def test__get_latest(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched builder.setup_builder function.
    act: when _install is called.
    assert: the mock function is called.
    """
    monkeypatch.setattr(
        cli, "OpenstackManager", (MagicMock(return_value=(manager_mock := MagicMock())))
    )
    cli._get_latest(cloud=MagicMock(), name=MagicMock())

    manager_mock.__enter__.return_value.get_latest_image_id.assert_called_once()


def test__build(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched builder.setup_builder function.
    act: when _install is called.
    assert: the mock function is called.
    """
    monkeypatch.setattr(cli.builder, "build_image", (builder_mock := MagicMock()))
    monkeypatch.setattr(
        cli, "OpenstackManager", (MagicMock(return_value=(manager_mock := MagicMock())))
    )

    cli._build(base="jammy", cloud=MagicMock(), name=MagicMock(), num_revisions=MagicMock())

    builder_mock.assert_called_once()
    manager_mock.__enter__.return_value.upload_image.assert_called_once()


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
    monkeypatch.setattr(cli, "_get_latest", (get_latest_mock := MagicMock()))
    monkeypatch.setattr(cli, "_build", (build_mock := MagicMock()))

    with pytest.raises(SystemExit):
        main([choice])

    install_mock.assert_not_called()
    get_latest_mock.assert_not_called()
    build_mock.assert_not_called()


def test_main_install(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given install argument and mocked builder functions.
    act: when main is called.
    assert: Setup builder mock function is called.
    """
    monkeypatch.setattr(cli, "_install", (install_mock := MagicMock()))
    monkeypatch.setattr(cli, "_get_latest", (get_latest_mock := MagicMock()))
    monkeypatch.setattr(cli, "_build", (build_mock := MagicMock()))

    main(["install"])

    install_mock.assert_called()
    get_latest_mock.assert_not_called()
    build_mock.assert_not_called()


def test_main_get_latest(monkeypatch: pytest.MonkeyPatch, get_latest_inputs: dict[str, str]):
    """
    arrange: given get-latest argument and mocked builder functions.
    act: when main is called.
    assert: Setup builder mock function is called.
    """
    monkeypatch.setattr(cli, "_install", (install_mock := MagicMock()))
    monkeypatch.setattr(cli, "_get_latest", (get_latest_mock := MagicMock()))
    monkeypatch.setattr(cli, "_build", (build_mock := MagicMock()))
    inputs = list(
        itertools.chain.from_iterable((flag, value) for (flag, value) in get_latest_inputs.items())
    )

    main(["get-latest", *inputs])

    install_mock.assert_not_called()
    get_latest_mock.assert_called()
    build_mock.assert_not_called()


@pytest.mark.parametrize(
    "invalid_patch",
    [
        pytest.param({"-c": ""}, id="empty cloud name"),
        pytest.param({"-n": ""}, id="empty image name"),
    ],
)
def test_main_invalid_get_latest(
    monkeypatch: pytest.MonkeyPatch,
    get_latest_inputs: dict[str, str],
    invalid_patch: dict[str, str],
):
    """
    arrange: given invalid get-latest arguments.
    act: when _get_latest is called.
    assert: SystemExit error is raised.
    """
    monkeypatch.setattr(cli, "_install", (install_mock := MagicMock()))
    monkeypatch.setattr(cli, "_get_latest", (get_latest_mock := MagicMock()))
    monkeypatch.setattr(cli, "_build", (build_mock := MagicMock()))
    get_latest_inputs.update(invalid_patch)
    inputs = list(
        itertools.chain.from_iterable((flag, value) for (flag, value) in invalid_patch.items())
    )

    with pytest.raises(SystemExit):
        main(["get-latest", *inputs])

    install_mock.assert_not_called()
    get_latest_mock.assert_not_called()
    build_mock.assert_not_called()


@pytest.mark.parametrize(
    "invalid_patch",
    [
        pytest.param({"-i": "test"}, id="invalid base-image"),
        pytest.param({"-r": "a"}, id="invalid revision-history (non-numeric)"),
        pytest.param({"-r": "-1"}, id="invalid revision-history (negative)"),
        pytest.param({"-r": "0"}, id="invalid revision-history (zero)"),
        pytest.param({"-r": "1"}, id="invalid revision-history (less than 2)"),
        pytest.param({"-r": "11"}, id="invalid revision-history (more than 10)"),
        pytest.param({"-c": ""}, id="empty cloud name"),
        pytest.param({"-n": ""}, id="empty image name"),
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
    monkeypatch.setattr(cli, "_get_latest", (get_latest_mock := MagicMock()))
    monkeypatch.setattr(cli, "_build", (build_mock := MagicMock()))
    build_image_inputs.update(invalid_patch)
    inputs = list(
        itertools.chain.from_iterable(
            (flag, value) for (flag, value) in build_image_inputs.items()
        )
    )

    with pytest.raises(SystemExit):
        main(["build", *inputs])

    install_mock.assert_not_called()
    get_latest_mock.assert_not_called()
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
    monkeypatch.setattr(cli, "_get_latest", (get_latest_mock := MagicMock()))
    monkeypatch.setattr(cli, "_build", (build_mock := MagicMock()))
    build_image_inputs.update({"-i": image})
    inputs = list(
        itertools.chain.from_iterable(
            (flag, value) for (flag, value) in build_image_inputs.items()
        )
    )

    main(["build", *inputs])

    install_mock.assert_not_called()
    get_latest_mock.assert_not_called()
    build_mock.assert_called()
