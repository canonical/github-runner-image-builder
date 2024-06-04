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


def test_main_invalid_choice(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched _parse_args that returns invalid action choice.
    act: when main is called.
    assert: ValueError is raised.
    """
    monkeypatch.setattr(
        cli, "_parse_args", MagicMock(return_value=cli.ActionsNamespace(action="invalid"))
    )

    with pytest.raises(ValueError) as exc:
        cli.main()

    assert "Invalid CLI action argument." in str(exc.getrepr())


@pytest.mark.parametrize(
    "action",
    [
        pytest.param("init", id="init"),
        pytest.param("latest-build-id", id="latest-build-id"),
        pytest.param("run", id="run"),
    ],
)
def test_main(monkeypatch: pytest.MonkeyPatch, action: str):
    """
    arrange: given a monkeypatched _parse_args that returns valid choice.
    act: when main is called.
    assert: mocked subfunctions are called correctly.
    """
    actions_namespace_mock = MagicMock(autospec=cli.ActionsNamespace)
    actions_namespace_mock.action = action
    monkeypatch.setattr(cli, "_parse_args", MagicMock(return_value=actions_namespace_mock))
    monkeypatch.setattr(cli.builder, "initialize", init_mock := MagicMock())
    monkeypatch.setattr(cli.store, "get_latest_build_id", latest_build_mock := MagicMock())
    monkeypatch.setattr(cli, "_build_and_upload", build_mock := MagicMock())

    cli.main()

    assert any((init_mock.called, latest_build_mock.called, build_mock.called))


@pytest.mark.parametrize(
    "invalid_action",
    [
        pytest.param("", id="empty"),
        pytest.param("invalid", id="invalid"),
    ],
)
def test__parse_args_invalid_action(invalid_action: str):
    """
    arrange: given invalid action arguments.
    act: when _parse_args is called.
    assert: SystemExit error is raised.
    """
    with pytest.raises(SystemExit) as exc:
        cli._parse_args([invalid_action])

    assert "invalid choice" in str(exc.getrepr())


@pytest.mark.parametrize(
    "invalid_args",
    [
        pytest.param({"": ""}, id="empty cloud name positional argument"),
        pytest.param({" ": ""}, id="empty image name positional argument"),
    ],
)
def test__parse_args_invalid_latest_build_id_args(run_inputs: dict, invalid_args: dict):
    """
    arrange: given invalid latest-build-id action arguments.
    act: when _parse_args is called.
    assert: SystemExit error is raised.
    """
    run_inputs.update(invalid_args)
    inputs = list(
        # if flag does not exist, append it as a positional argument.
        itertools.chain.from_iterable(
            (flag, value) if flag.strip() else (value,) for (flag, value) in run_inputs.items()
        )
    )

    with pytest.raises(SystemExit) as exc:
        cli._parse_args(inputs)

    assert "invalid choice" in str(exc.getrepr())


@pytest.mark.parametrize(
    "invalid_args",
    [
        pytest.param({"--base-image": ""}, id="no base-image"),
        pytest.param({"--base-image": "test"}, id="invalid base-image"),
        pytest.param(
            {"--callback-script": "non-existant-path"}, id="empty image name positional argument"
        ),
        pytest.param({"": ""}, id="empty cloud name positional argument"),
        pytest.param({" ": ""}, id="empty image name positional argument"),
    ],
)
def test__parse_args_invalid_run_args(run_inputs: dict, invalid_args: dict):
    """
    arrange: given invalid run action arguments.
    act: when _parse_args is called.
    assert: SystemExit error is raised.
    """
    run_inputs.update(invalid_args)
    inputs = list(
        # if flag does not exist, append it as a positional argument.
        itertools.chain.from_iterable(
            (flag, value) if flag.strip() else (value,) for (flag, value) in run_inputs.items()
        )
    )

    with pytest.raises(SystemExit) as exc:
        cli._parse_args(inputs)

    assert "invalid choice" in str(exc.getrepr())


@pytest.mark.parametrize(
    "action, args, expected",
    [
        pytest.param("init", {}, cli.argparse.Namespace(action="init"), id="init"),
        pytest.param(
            "latest-build-id",
            {"": "test-cloud-name", " ": "test-image-name"},
            cli.argparse.Namespace(
                action="latest-build-id",
                cloud_name="test-cloud-name",
                image_name="test-image-name",
            ),
            id="latest-build-id",
        ),
        pytest.param(
            "run",
            {"": "test-cloud-name", " ": "test-image-name"},
            cli.argparse.Namespace(
                action="run",
                base="noble",
                callback_script_path=None,
                cloud_name="test-cloud-name",
                image_name="test-image-name",
                keep_revisions=5,
            ),
            id="run (no-optional)",
        ),
        pytest.param(
            "run",
            {"": "test-cloud-name", " ": "test-image-name", "--base-image": "jammy"},
            cli.argparse.Namespace(
                action="run",
                base="jammy",
                callback_script_path=None,
                cloud_name="test-cloud-name",
                image_name="test-image-name",
                keep_revisions=5,
            ),
            id="run (base image)",
        ),
        pytest.param(
            "run",
            {"": "test-cloud-name", " ": "test-image-name", "--keep-revisions": "2"},
            cli.argparse.Namespace(
                action="run",
                base="noble",
                callback_script_path=None,
                cloud_name="test-cloud-name",
                image_name="test-image-name",
                keep_revisions=2,
            ),
            id="run (keep revisions)",
        ),
        pytest.param(
            "run",
            {"": "test-cloud-name", " ": "test-image-name", "--callback-script": "test_callback"},
            cli.argparse.Namespace(
                action="run",
                base="noble",
                callback_script_path=Path("test_callback"),
                cloud_name="test-cloud-name",
                image_name="test-image-name",
                keep_revisions=5,
            ),
            id="run (callback script)",
        ),
    ],
)
def test__parse_args(
    monkeypatch: pytest.MonkeyPatch, action: str, args: dict, expected: cli.ActionsNamespace
):
    """
    arrange: given action and its arguments.
    act: when _parse_args is called.
    assert: expected ActionsNamespace object is created.
    """
    monkeypatch.setattr(
        cli,
        "_existing_path",
        MagicMock(
            return_value=(
                Path(args["--callback-script"]) if args.get("--callback-script", None) else None
            )
        ),
    )
    inputs = list(
        # if flag does not exist, append it as a positional argument.
        itertools.chain.from_iterable(
            (flag, value) if flag.strip() else (value,) for (flag, value) in args.items()
        )
    )

    assert cli._parse_args([action, *inputs]) == expected


def test__existing_path_not_exists(tmp_path: Path):
    """
    arrange: given a path that does not exist.
    act: when _existing_path is called.
    assert: ValueError is raised.
    """
    not_exists_path = tmp_path / "non-existent"
    with pytest.raises(ValueError) as exc:
        cli._existing_path(str(not_exists_path))

    assert f"Given path {not_exists_path} not found." in str(exc.getrepr())


def test__existing_path(tmp_path: Path):
    """
    arrange: given a path that does not exist.
    act: when _existing_path is called.
    assert: ValueError is raised.
    """
    not_exists_path = tmp_path / "non-existent"
    not_exists_path.touch()
    assert cli._existing_path(str(not_exists_path)) == not_exists_path


def test__non_empty_string_error():
    """
    arrange: given an empty string.
    act: when _non_empty_string is called.
    assert: ValueError is raised.
    """
    with pytest.raises(ValueError):
        cli._non_empty_string("")


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
