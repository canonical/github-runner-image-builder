# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for cli module."""

from unittest.mock import MagicMock

import pytest

from github_runner_image_builder.cli import builder, main


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
    monkeypatch.setattr(builder, "setup_builder", (setup_mock := MagicMock()))
    monkeypatch.setattr(builder, "build_image", (build_mock := MagicMock()))

    with pytest.raises(SystemExit):
        main([choice])

    setup_mock.assert_not_called()
    build_mock.assert_not_called()


def test_main_install(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given install argument and mocked builder functions.
    act: when main is called.
    assert: Setup builder mock function is called.
    """
    monkeypatch.setattr(builder, "setup_builder", (setup_mock := MagicMock()))
    monkeypatch.setattr(builder, "build_image", (build_mock := MagicMock()))

    main(["install"])

    setup_mock.assert_called()
    build_mock.assert_not_called()


def test_main_invalid_base_image(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given invalid base_image argument and mocked builder functions.
    act: when main is called.
    assert: SystemExit is raised.
    """
    monkeypatch.setattr(builder, "setup_builder", (setup_mock := MagicMock()))
    monkeypatch.setattr(builder, "build_image", (build_mock := MagicMock()))

    with pytest.raises(SystemExit):
        main(["build", "-i", "invalid", "-o", "compressed.img"])

    setup_mock.assert_not_called()
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
def test_main_base_image(monkeypatch: pytest.MonkeyPatch, image: str):
    """
    arrange: given invalid base_image argument and mocked builder functions.
    act: when main is called.
    assert: build image is called.
    """
    monkeypatch.setattr(builder, "setup_builder", (setup_mock := MagicMock()))
    monkeypatch.setattr(builder, "build_image", (build_mock := MagicMock()))

    main(["build", "-i", image, "-o", "compressed.img"])

    setup_mock.assert_not_called()
    build_mock.assert_called()
