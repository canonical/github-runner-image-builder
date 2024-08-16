# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Image test module."""

import logging
from pathlib import Path

import pytest
from fabric.connection import Connection as SSHConnection
from openstack.connection import Connection
from pylxd import Client

from github_runner_image_builder.cli import get_latest_build_id
from github_runner_image_builder.config import IMAGE_OUTPUT_PATH
from tests.integration import commands, helpers

logger = logging.getLogger(__name__)


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
    helpers.create_lxd_vm_image(
        lxd_client=lxd, img_path=IMAGE_OUTPUT_PATH, image=image, tmp_path=tmp_path
    )
    logger.info("Launching LXD instance.")
    instance = await helpers.create_lxd_instance(lxd_client=lxd, image=image)

    for testcmd in commands.TEST_RUNNER_COMMANDS:
        if testcmd == "configure dockerhub mirror":
            if not dockerhub_mirror:
                continue
            testcmd.command = helpers.format_dockerhub_mirror_microk8s_command(
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


@pytest.mark.amd64
@pytest.mark.arm64
@pytest.mark.asyncio
@pytest.mark.usefixtures("cli_run")
async def test_openstack_upload(openstack_connection: Connection, openstack_image_name: str):
    """
    arrange: given a built output from the CLI.
    act: when openstack images are listed.
    assert: the built image is uploaded in Openstack.
    """
    assert len(openstack_connection.search_images(openstack_image_name))


@pytest.mark.arm64
@pytest.mark.asyncio
@pytest.mark.usefixtures("cli_run")
async def test_image_arm(ssh_connection: SSHConnection, dockerhub_mirror: str | None):
    """
    arrange: given a built output from the CLI.
    act: when the image is booted and commands are executed.
    assert: commands do not error.
    """
    helpers.run_openstack_tests(dockerhub_mirror=dockerhub_mirror, ssh_connection=ssh_connection)


@pytest.mark.amd64
@pytest.mark.arm64
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


@pytest.mark.amd64
@pytest.mark.arm64
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
    get_latest_build_id(cloud_name, openstack_image_name)
    image_id = openstack_connection.get_image_id(openstack_image_name)

    res = capsys.readouterr()
    assert res.out == image_id, f"Openstack image not matching, {res.out} {res.err}, {image_id}"
