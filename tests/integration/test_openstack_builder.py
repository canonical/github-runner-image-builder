# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Test openstack image builder module."""

# Need access to protected functions for testing
# pylint:disable=protected-access

import functools
import itertools
import logging
import typing
from datetime import datetime, timezone

import openstack
import pytest
import pytest_asyncio
from fabric.connection import Connection as SSHConnection
from openstack.compute.v2.image import Image
from openstack.compute.v2.server import Server
from openstack.connection import Connection

from github_runner_image_builder import config, openstack_builder
from tests.integration import helpers, types

logger = logging.getLogger(__name__)


@pytest.mark.amd64
@pytest.mark.arm64
def test_initialize(openstack_connection: Connection, arch: config.Arch, cloud_name: str):
    """
    arrange: given an openstack cloud instance.
    act: when openstack builder is initialized.
    assert: \
        1. the base cloud images are created
        2. openstack resources(security group, keypair) are \
            created.
    """
    test_start_time = datetime.now(tz=timezone.utc)

    openstack_builder.initialize(arch=arch, cloud_name=cloud_name)

    # 1.
    images: list[Image] = openstack_connection.list_images()
    jammy_images = filter(
        functools.partial(
            helpers.has_name,
            name=openstack_builder._get_base_image_name(arch=arch, base=config.BaseImage.JAMMY),
        ),
        images,
    )
    noble_images = filter(
        functools.partial(
            helpers.has_name,
            name=openstack_builder._get_base_image_name(arch=arch, base=config.BaseImage.NOBLE),
        ),
        images,
    )
    image_builder_images = itertools.chain(jammy_images, noble_images)
    test_images: typing.Iterable[Image] = filter(
        functools.partial(helpers.is_greater_than_time, timestamp=test_start_time),
        image_builder_images,
    )
    assert list(test_images)

    # 2.
    assert openstack_connection.get_security_group(
        name_or_id=openstack_builder.SHARED_SECURITY_GROUP_NAME
    )
    assert openstack_connection.get_keypair(name_or_id=openstack_builder.BUILDER_SSH_KEY_NAME)


# The code is not duplicated, it has similar setup but uses different input fixtures for external
# openstack builder.
# pylint: disable=R0801
@pytest.fixture(scope="module", name="server")
def server_fixture(
    openstack_metadata: types.OpenstackMeta,
    test_id: str,
):
    """The OpenStåck sserver fixture."""
    image: Image = openstack_metadata.connection.get_image(
        name_or_id=openstack_builder.IMAGE_SNAPSHOT_NAME
    )
    server_name = f"test-image-builder-run-{test_id}"
    try:
        server: Server = openstack_metadata.connection.create_server(
            name=server_name,
            image=image.id,
            key_name=openstack_builder.BUILDER_SSH_KEY_NAME,
            flavor=openstack_metadata.flavor,
            network=openstack_metadata.network,
            security_groups=[openstack_builder.SHARED_SECURITY_GROUP_NAME],
            auto_ip=False,
            timeout=5 * 60,
            wait=True,
        )
        yield server
    except openstack.exceptions.SDKException:
        server = openstack_metadata.connection.get_server(name_or_id=server_name)
        logger.exception("Failed to create server, %s", dict(server))
    finally:
        openstack_metadata.connection.delete_server(server_name, wait=True)
        openstack_metadata.connection.delete_image(image.name, wait=True)


@pytest_asyncio.fixture(scope="module", name="ssh_connection")
async def ssh_connection_fixture(
    server: Server,
    proxy: types.ProxyConfig,
    openstack_metadata: types.OpenstackMeta,
    dockerhub_mirror: str | None,
) -> SSHConnection:
    """The openstack server ssh connection fixture."""
    logger.info("Setting up SSH connection.")
    ssh_connection = await helpers.wait_for_valid_connection(
        connection=openstack_metadata.connection,
        server_name=server.name,
        network=openstack_metadata.network,
        ssh_key=openstack_metadata.ssh_key.private_key,
        proxy=proxy,
        dockerhub_mirror=dockerhub_mirror,
    )

    return ssh_connection


# pylint: enable=R0801


@pytest.mark.amd64
@pytest.mark.arm64
async def test_run(ssh_connection: SSHConnection, dockerhub_mirror: str | None):
    """
    arrange: given openstack cloud instance.
    act: when run (build image) is called.
    assert: an image snapshot of working VM is created with the ability to run expected commands.
    """
    helpers.run_openstack_tests(dockerhub_mirror=dockerhub_mirror, ssh_connection=ssh_connection)
