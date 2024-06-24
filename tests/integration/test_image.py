# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Image test module."""

import dataclasses
import logging
from pathlib import Path

import pytest
from fabric.connection import Connection as SSHConnection
from fabric.runners import Result
from openstack.connection import Connection
from pylxd import Client

from github_runner_image_builder.cli import main
from github_runner_image_builder.config import IMAGE_OUTPUT_PATH
from tests.integration.helpers import (
    create_lxd_instance,
    create_lxd_vm_image,
    format_dockerhub_mirror_microk8s_command,
)

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class Commands:
    """Test commands to execute.

    Attributes:
        name: The test name.
        command: The command to execute.
        env: Additional run envs.
    """

    name: str
    command: str
    env: dict | None = None


# This is matched with E2E test run of github-runner-operator charm.
TEST_RUNNER_COMMANDS = (
    Commands(name="simple hello world", command="echo hello world"),
    Commands(name="file permission to /usr/local/bin", command="ls -ld /usr/local/bin"),
    Commands(
        name="file permission to /usr/local/bin (create)", command="touch /usr/local/bin/test_file"
    ),
    Commands(name="install microk8s", command="sudo snap install microk8s --classic"),
    # This is a special helper command to configure dockerhub registry if available.
    Commands(
        name="configure dockerhub mirror",
        command="""echo 'server = "{registry_url}"

[host.{hostname}:{port}]
capabilities = ["pull", "resolve"]
' | sudo tee /var/snap/microk8s/current/args/certs.d/docker.io/hosts.toml && \
sudo microk8s stop && sudo microk8s start""",
    ),
    Commands(name="wait for microk8s", command="microk8s status --wait-ready"),
    Commands(
        name="deploy nginx in microk8s",
        command="microk8s kubectl create deployment nginx --image=nginx",
    ),
    Commands(
        name="wait for nginx",
        command="microk8s kubectl rollout status deployment/nginx --timeout=20m",
    ),
    Commands(name="update apt in docker", command="docker run python:3.10-slim apt-get update"),
    Commands(name="docker version", command="docker version"),
    Commands(name="check python3 alias", command="python --version"),
    Commands(name="pip version", command="python3 -m pip --version"),
    Commands(name="npm version", command="npm --version"),
    Commands(name="shellcheck version", command="shellcheck --version"),
    Commands(name="jq version", command="jq --version"),
    Commands(name="yq version", command="yq --version"),
    Commands(name="apt update", command="sudo apt-get update -y"),
    Commands(name="install pipx", command="sudo apt-get install -y pipx"),
    Commands(name="pipx add path", command="pipx ensurepath"),
    Commands(name="install check-jsonschema", command="pipx install check-jsonschema"),
    Commands(
        name="check jsonschema",
        command="check-jsonschema --version",
        # pipx has been added to PATH but still requires additional PATH env since
        # default shell is not bash in OpenStack
        env={"PATH": "$PATH:/home/ubuntu/.local/bin"},
    ),
    Commands(name="unzip version", command="unzip -v"),
    Commands(name="gh version", command="gh --version"),
    Commands(
        name="test sctp support", command="sudo apt-get install lksctp-tools -yq && checksctp"
    ),
)


@pytest.mark.asyncio
@pytest.mark.amd64
@pytest.mark.usefixtures("cli_run")
async def test_image_amd(image: str, tmp_path: Path, dockerhub_mirror: str | None):
    """
    arrange: given a built output from the CLI.
    act: when the image is booted and commands are executed.
    assert: commands do not error.
    """
    lxd = Client()
    logger.info("Creating LXD VM Image.")
    create_lxd_vm_image(lxd_client=lxd, img_path=IMAGE_OUTPUT_PATH, image=image, tmp_path=tmp_path)
    logger.info("Launching LXD instance.")
    instance = await create_lxd_instance(lxd_client=lxd, image=image)

    for testcmd in TEST_RUNNER_COMMANDS:
        if testcmd == "configure dockerhub mirror":
            if not dockerhub_mirror:
                continue
            testcmd.command = format_dockerhub_mirror_microk8s_command(
                command=testcmd.command, dockerhub_mirror=dockerhub_mirror
            )
        logger.info("Running command: %s", testcmd.command)
        # run command as ubuntu user. Passing in user argument would not be equivalent to a login
        # shell which is missing critical environment variables such as $USER and the user groups
        # are not properly loaded.
        result = instance.execute(
            ["su", "--shell", "/bin/bash", "--login", "ubuntu", "-c", testcmd.command]
        )
        logger.info("Command output: %s %s %s", result.exit_code, result.stdout, result.stderr)
        assert result.exit_code == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("cli_run")
async def test_openstack_upload(openstack_connection: Connection, openstack_image_name: str):
    """
    arrange: given a built output from the CLI.
    act: when openstack images are listed.
    assert: the built image is uploaded in Openstack.
    """
    assert len(openstack_connection.search_images(openstack_image_name))


@pytest.mark.asyncio
@pytest.mark.arm64
@pytest.mark.usefixtures("cli_run")
async def test_image_arm(ssh_connection: SSHConnection, dockerhub_mirror: str | None):
    """
    arrange: given a built output from the CLI.
    act: when the image is booted and commands are executed.
    assert: commands do not error.
    """
    for testcmd in TEST_RUNNER_COMMANDS:
        if testcmd == "configure dockerhub mirror":
            if not dockerhub_mirror:
                continue
            testcmd.command = format_dockerhub_mirror_microk8s_command(
                command=testcmd.command, dockerhub_mirror=dockerhub_mirror
            )
        logger.info("Running command: %s", testcmd.command)
        result: Result = ssh_connection.run(testcmd.command, env=testcmd.env)
        logger.info("Command output: %s %s %s", result.return_code, result.stdout, result.stderr)
        assert result.return_code == 0


@pytest.mark.asyncio
@pytest.mark.usefixtures("cli_run")
async def test_script_callback(callback_result_path: Path):
    """
    arrange: given a CLI run with script that creates a file.
    act: None.
    assert: the file exist.
    """
    assert callback_result_path.exists()
    assert len(callback_result_path.read_text(encoding="utf-8"))


@pytest.mark.asyncio
@pytest.mark.usefixtures("cli_run")
async def test_get_image(
    cloud_name: str,
    openstack_image_name: str,
    capsys: pytest.CaptureFixture,
    openstack_connection: Connection,
):
    """
    arrange: a cli that already ran.
    act: when get image id is run.
    assert: the latest image matches the stdout output.
    """
    main(["latest-build-id", cloud_name, openstack_image_name])
    image_id = openstack_connection.get_image_id(openstack_image_name)

    res = capsys.readouterr()
    assert res.out == image_id, f"Openstack image not matching, {res.out} {res.err}, {image_id}"
