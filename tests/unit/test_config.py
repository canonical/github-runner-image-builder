# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for state module."""

# Need access to protected functions for testing
# pylint:disable=protected-access

import platform

import pytest

from github_runner_image_builder.config import (
    Arch,
    UnsupportedArchitectureError,
    get_supported_arch,
)


@pytest.mark.parametrize(
    "arch",
    [
        pytest.param("ppc64le", id="ppc64le"),
        pytest.param("mips", id="mips"),
        pytest.param("s390x", id="s390x"),
        pytest.param("testing", id="testing"),
    ],
)
def test_get_supported_arch_unsupported_arch(arch: str, monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given architectures that are not supported by the charm.
    act: when get_supported_arch is called.
    assert: UnsupportedArchitectureError is raised
    """
    monkeypatch.setattr(platform, "machine", lambda: arch)

    with pytest.raises(UnsupportedArchitectureError) as exc:
        get_supported_arch()

    assert arch in str(exc.getrepr())


@pytest.mark.parametrize(
    "arch, expected_arch",
    [
        pytest.param("aarch64", Arch.ARM64, id="aarch64"),
        pytest.param("arm64", Arch.ARM64, id="aarch64"),
        pytest.param("x86_64", Arch.X64, id="amd64"),
    ],
)
def test_get_supported_arch(arch: str, expected_arch: Arch, monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given architectures that is supported by the charm.
    act: when get_supported_arch is called.
    assert: expected architecture is returned.
    """
    monkeypatch.setattr(platform, "machine", lambda: arch)

    assert get_supported_arch() == expected_arch
