# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures for github runner image builder integration tests."""
import pytest


@pytest.fixture(scope="module", name="image")
def image_fixture(pytestconfig: pytest.Config) -> str:
    """Path to the built charm."""
    image = pytestconfig.getoption("--image")
    assert image, "Please specify the --image command line option"
    return image
