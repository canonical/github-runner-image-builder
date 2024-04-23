# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Image test module."""

import logging
from pathlib import Path
from typing import NamedTuple

import pytest
from pylxd import Client
from pylxd.models.image import Image
from pylxd.models.instance import Instance

from github_runner_image_builder.cli import main

logger = logging.getLogger(__name__)


class TestCommand(NamedTuple):
    """Test commands to execute.

    Attributes:
        name: The test name.
        command: The command to execute.
        expected: The expected stdout result.
    """

    name: str
    command: str
    expected: str


# This is matched with E2E test run of github-runner-operator charm.
TEST_RUNNER_COMMANDS = (
    TestCommand(name="simple hello world", command="echo 'hello world'", expected="hello world"),
    TestCommand(
        name="file permission to /usr/local/bin",
        command="ls -ld /usr/local/bin | grep drwxrwxrwx",
        expected="drwxrwxrwx",
    ),
    TestCommand(
        name="file permission to /usr/local/bin (create)",
        command="touch /usr/local/bin/test_file",
        expected="",
    ),
    TestCommand(
        name="install microk8s", command="sudo snap install microk8s --classic", expected=""
    ),
    TestCommand(name="wait for microk8s", command="microk8s status --wait-ready", expected=""),
    TestCommand(
        name="deploy nginx in microk8s",
        command="microk8s kubectl create deployment nginx --image=nginx",
        expected="",
    ),
    TestCommand(
        name="wait for nginx",
        command="microk8s kubectl rollout status deployment/nginx --timeout=30m",
        expected="",
    ),
    TestCommand(
        name="update apt in docker",
        command="docker run python:3.10-slim apt-get update",
        expected="",
    ),
    TestCommand(name="docker version", command="docker version", expected=""),
    TestCommand(name="check python3 alias", command="python --version", expected=""),
    TestCommand(name="pip version", command="python3 -m pip --version", expected=""),
    TestCommand(name="npm version", command="npm --version", expected=""),
    TestCommand(name="shellcheck version", command="shellcheck --version", expected=""),
    TestCommand(name="jq version", command="jq --version", expected=""),
    TestCommand(name="yq version", command="yq --version", expected=""),
    TestCommand(name="apt update", command="sudo apt-get update -y", expected=""),
    TestCommand(name="install pipx", command="sudo apt-get install -y pipx", expected=""),
    TestCommand(
        name="install check-jsonschema", command="pipx install check-jsonschema", expected=""
    ),
    TestCommand(name="unzip version", command="unzip -v", expected=""),
    TestCommand(name="gh version", command="gh --version", expected=""),
    TestCommand(name="check jsonschema", command="check-jsonschema --version", expected=""),
    TestCommand(
        name="test sctp support",
        command="sudo apt-get install lksctp-tools -yq && checksctp",
        expected="",
    ),
)


@pytest.mark.parametrize(
    "image, output",
    [
        pytest.param("jammy", "jammy.img", id="jammy"),
        pytest.param("noble", "noble.img", id="noble"),
    ],
)
def test_image(image: str, output: str):
    """
    arrange: given a built output from the CLI.
    act: when the image is booted and commands are executed.
    assert: commands do not error.
    """
    main(["install"])
    main(["build", "-i", image, "-o", output])

    lxd_client = Client()
    # lxc_clients are not properly typed.
    lxd_image: Image = lxd_client.images.create(  # pylint: disable=no-member
        Path(output).read_bytes(), public=True, wait=True
    )
    lxd_image.add_alias(image)
    instance_config = {
        "name": f"test-{image}",
        "source": {"type": "image", "alias": image},
        "type": "virtual-machine",
        "config": {"limits.cpu": "2"},
    }
    instance: Instance = lxd_client.instances.create(  # pylint: disable=no-member
        instance_config, wait=True
    )
    instance.start(timeout=10 * 60, wait=True)

    for command in TEST_RUNNER_COMMANDS:
        logger.info("Running command: %s", command.command)
        result = instance.execute([command.command])
        logger.info("Command output: %s %s %s", result.exit_code, result.stdout, result.stderr)
        assert result.exit_code == 0
