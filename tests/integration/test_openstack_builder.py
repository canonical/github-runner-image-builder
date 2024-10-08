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

import pytest
import pytest_asyncio
from fabric.connection import Connection as SSHConnection
from openstack.compute.v2.image import Image
from openstack.compute.v2.server import Server
from openstack.connection import Connection
from openstack.network.v2.security_group import SecurityGroup

from github_runner_image_builder import config, openstack_builder
from tests.integration import helpers, types

logger = logging.getLogger(__name__)


@pytest.mark.amd64
@pytest.mark.arm64
def test_initialize(
    openstack_connection: Connection, arch: config.Arch, cloud_name: str, test_id: str
):
    """
    arrange: given an openstack cloud instance.
    act: when openstack builder is initialized.
    assert: \
        1. the base cloud images are created
        2. openstack resources(security group, keypair) are \
            created.
    """
    test_start_time = datetime.now(tz=timezone.utc)

    openstack_builder.initialize(arch=arch, cloud_name=cloud_name, prefix=test_id)

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
    assert openstack_connection.get_keypair(
        name_or_id=openstack_builder._get_keypair_name(prefix=test_id)
    )


@pytest.fixture(scope="module", name="cli_run")
def cli_run_fixture(
    image_config: types.ImageConfig,
    openstack_metadata: types.OpenstackMeta,
    test_id: str,
    proxy: types.ProxyConfig,
):
    """A CLI run.

    This fixture assumes pipx is installed in the system and the github-runner-image-builder has
    been installed using pipx. See testenv:integration section of tox.ini.
    """
    openstack_builder.run(
        cloud_config=openstack_builder.CloudConfig(
            cloud_name=openstack_metadata.cloud_name,
            flavor=openstack_metadata.flavor,
            network=openstack_metadata.network,
            proxy=proxy.http,
            prefix=test_id,
            upload_cloud_names=[openstack_metadata.cloud_name],
        ),
        image_config=config.ImageConfig(
            arch=image_config.arch,
            base=config.BaseImage.from_str(image_config.image),
            runner_version="",
            name=f"{test_id}-image-builder-test",
        ),
        keep_revisions=1,
    )


# the code is similar but the fixture source is localized and is different.
# pylint: disable=R0801
@pytest_asyncio.fixture(scope="module", name="openstack_server")
async def openstack_server_fixture(
    openstack_metadata: types.OpenstackMeta,
    openstack_security_group: SecurityGroup,
    test_id: str,
):
    """A testing openstack instance."""
    image: Image = openstack_metadata.connection.get_image(
        name_or_id=f"{test_id}-image-builder-test"
    )
    server_name = f"test-image-builder-run-{test_id}"
    for server in helpers.create_openstack_server(
        openstack_metadata=openstack_metadata,
        server_name=server_name,
        image=image,
        security_group=openstack_security_group,
    ):
        yield server
    openstack_metadata.connection.delete_image(image.id)


@pytest_asyncio.fixture(scope="module", name="ssh_connection")
async def ssh_connection_fixture(
    openstack_server: Server,
    proxy: types.ProxyConfig,
    openstack_metadata: types.OpenstackMeta,
    dockerhub_mirror: str | None,
) -> SSHConnection:
    """The openstack server ssh connection fixture."""
    logger.info("Setting up SSH connection.")
    ssh_connection = await helpers.wait_for_valid_connection(
        connection_params=helpers.OpenStackConnectionParams(
            connection=openstack_metadata.connection,
            server_name=openstack_server.name,
            network=openstack_metadata.network,
            ssh_key=openstack_metadata.ssh_key.private_key,
        ),
        proxy=proxy,
        dockerhub_mirror=dockerhub_mirror,
    )

    return ssh_connection


# pylint: enable=R0801


@pytest.mark.amd64
@pytest.mark.arm64
@pytest.mark.usefixtures("cli_run")
async def test_run(ssh_connection: SSHConnection, dockerhub_mirror: str | None):
    """
    arrange: given openstack cloud instance.
    act: when run (build image) is called.
    assert: an image snapshot of working VM is created with the ability to run expected commands.
    """
    helpers.run_openstack_tests(dockerhub_mirror=dockerhub_mirror, ssh_connection=ssh_connection)
