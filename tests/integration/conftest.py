# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures for github runner image builder integration tests."""
import logging
import secrets
import string

# Subprocess is used to run the application.
import subprocess  # nosec: B404
import typing
from pathlib import Path

import openstack
import openstack.exceptions
import pytest
import pytest_asyncio
import yaml
from fabric.connection import Connection as SSHConnection
from openstack.compute.v2.keypair import Keypair
from openstack.compute.v2.server import Server
from openstack.connection import Connection
from openstack.image.v2.image import Image
from openstack.network.v2.security_group import SecurityGroup

from tests.integration import helpers, types

logger = logging.getLogger(__name__)


@pytest.fixture(scope="module", name="image")
def image_fixture(pytestconfig: pytest.Config) -> str:
    """The ubuntu image base to build from."""
    image = pytestconfig.getoption("--image")
    assert image, "Please specify the --image command line option"
    return image


@pytest.fixture(scope="module", name="openstack_clouds_yaml")
def openstack_clouds_yaml_fixture(pytestconfig: pytest.Config) -> str:
    """Configured clouds-yaml setting."""
    clouds_yaml = pytestconfig.getoption("--openstack-clouds-yaml")
    return clouds_yaml


@pytest.fixture(scope="module", name="private_endpoint_clouds_yaml")
def private_endpoint_clouds_yaml_fixture(pytestconfig: pytest.Config) -> typing.Optional[str]:
    """The openstack private endpoint clouds yaml."""
    auth_url = pytestconfig.getoption("--openstack-auth-url")
    password = pytestconfig.getoption("--openstack-password")
    project_domain_name = pytestconfig.getoption("--openstack-project-domain-name")
    project_name = pytestconfig.getoption("--openstack-project-name")
    user_domain_name = pytestconfig.getoption("--openstack-user-domain-name")
    user_name = pytestconfig.getoption("--openstack-username")
    region_name = pytestconfig.getoption("--openstack-region-name")
    if any(
        not val
        for val in (
            auth_url,
            password,
            project_domain_name,
            project_name,
            user_domain_name,
            user_name,
            region_name,
        )
    ):
        return None
    return string.Template(
        Path("tests/integration/data/clouds.yaml.tmpl").read_text(encoding="utf-8")
    ).substitute(
        {
            "auth_url": auth_url,
            "password": password,
            "project_domain_name": project_domain_name,
            "project_name": project_name,
            "user_domain_name": user_domain_name,
            "username": user_name,
            "region_name": region_name,
        }
    )


@pytest.fixture(scope="module", name="network_name")
def network_name_fixture(pytestconfig: pytest.Config) -> str:
    """Network to use to spawn test instances under."""
    network_name = pytestconfig.getoption("--openstack-network-name")
    assert network_name, "Please specify the --openstack-network-name command line option"
    return network_name


@pytest.fixture(scope="module", name="flavor_name")
def flavor_name_fixture(pytestconfig: pytest.Config) -> str:
    """Flavor to create testing instances with."""
    flavor_name = pytestconfig.getoption("--openstack-flavor-name")
    assert flavor_name, "Please specify the --openstack-flavor-name command line option"
    return flavor_name


@pytest.fixture(scope="module", name="clouds_yaml_contents")
def clouds_yaml_contents_fixture(
    openstack_clouds_yaml: typing.Optional[str], private_endpoint_clouds_yaml: typing.Optional[str]
):
    """The Openstack clouds yaml or private endpoint cloud yaml contents."""
    clouds_yaml_contents = openstack_clouds_yaml or private_endpoint_clouds_yaml
    assert clouds_yaml_contents, (
        "Please specify --openstack-clouds-yaml or all of private endpoint arguments "
        "(--openstack-auth-url, --openstack-password, --openstack-project-domain-name, "
        "--openstack-project-name, --openstack-user-domain-name, --openstack-username, "
        "--openstack-region-name)"
    )
    return clouds_yaml_contents


@pytest.fixture(scope="module", name="cloud_name")
def cloud_name_fixture(clouds_yaml_contents: str) -> str:
    """The cloud to use from cloud config."""
    clouds_yaml = yaml.safe_load(clouds_yaml_contents)
    clouds_yaml_path = Path("clouds.yaml")
    clouds_yaml_path.write_text(data=clouds_yaml_contents, encoding="utf-8")
    first_cloud = next(iter(clouds_yaml["clouds"].keys()))
    return first_cloud


@pytest.fixture(scope="module", name="openstack_connection")
def openstack_connection_fixture(cloud_name: str) -> Connection:
    """The openstack connection instance."""
    return openstack.connect(cloud_name)


@pytest.fixture(scope="module", name="callback_result_path")
def callback_result_path_fixture() -> Path:
    """The file created when the callback script is run."""
    return Path("callback_complete")


@pytest.fixture(scope="module", name="callback_script")
def callback_script_fixture(callback_result_path: Path) -> Path:
    """The callback script to use with the image builder."""
    callback_script = Path("callback")
    callback_script.write_text(
        f"""#!/bin/bash
IMAGE_ID=$1
echo $IMAGE_ID | tee {callback_result_path}
""",
        encoding="utf-8",
    )
    callback_script.chmod(0o775)
    return callback_script


@pytest.fixture(scope="module", name="test_id")
def test_id_fixture() -> str:
    """The unique test identifier."""
    return secrets.token_hex(4)


@pytest.fixture(scope="module", name="openstack_image_name")
def openstack_image_name_fixture(test_id: str) -> str:
    """The image name to upload to openstack."""
    return f"image-builder-test-image-{test_id}"


@pytest.fixture(scope="module", name="ssh_key")
def ssh_key_fixture(
    openstack_connection: Connection, test_id: str
) -> typing.Generator[types.SSHKey, None, None]:
    """The openstack ssh key fixture."""
    keypair: Keypair = openstack_connection.create_keypair(f"test-image-builder-keys-{test_id}")
    ssh_key_path = Path("tmp_key")
    ssh_key_path.touch(exist_ok=True)
    ssh_key_path.write_text(keypair.private_key, encoding="utf-8")

    yield types.SSHKey(keypair=keypair, private_key=ssh_key_path)

    openstack_connection.delete_keypair(name=keypair.name)


class OpenstackMeta(typing.NamedTuple):
    """A wrapper around Openstack related info.

    Attributes:
        connection: The connection instance to Openstack.
        ssh_key: The SSH-Key created to connect to Openstack instance.
        network: The Openstack network to create instances under.
        flavor: The flavor to create instances with.
    """

    connection: Connection
    ssh_key: types.SSHKey
    network: str
    flavor: str


@pytest.fixture(scope="module", name="openstack_metadata")
def openstack_metadata_fixture(
    openstack_connection: Connection, ssh_key: types.SSHKey, network_name: str, flavor_name: str
) -> OpenstackMeta:
    """A wrapper around openstack related info."""
    return OpenstackMeta(
        connection=openstack_connection, ssh_key=ssh_key, network=network_name, flavor=flavor_name
    )


@pytest.fixture(scope="module", name="openstack_security_group")
def openstack_security_group_fixture(openstack_connection: Connection):
    """An ssh-connectable security group."""
    security_group_name = "github-runner-image-builder-test-security-group"
    security_group: SecurityGroup = openstack_connection.create_security_group(
        name=security_group_name,
        description="For servers managed by the github-runner-image-builder app.",
    )
    # For ping
    openstack_connection.create_security_group_rule(
        secgroup_name_or_id=security_group_name,
        protocol="icmp",
        direction="ingress",
        ethertype="IPv4",
    )
    # For SSH
    openstack_connection.create_security_group_rule(
        secgroup_name_or_id=security_group_name,
        port_range_min="22",
        port_range_max="22",
        protocol="tcp",
        direction="ingress",
        ethertype="IPv4",
    )
    # For tmate
    openstack_connection.create_security_group_rule(
        secgroup_name_or_id=security_group_name,
        port_range_min="10022",
        port_range_max="10022",
        protocol="tcp",
        direction="egress",
        ethertype="IPv4",
    )

    yield security_group

    openstack_connection.delete_security_group(security_group_name)


@pytest_asyncio.fixture(scope="module", name="openstack_server")
async def openstack_server_fixture(
    openstack_metadata: OpenstackMeta,
    openstack_security_group: SecurityGroup,
    openstack_image_name: str,
    test_id: str,
):
    """A testing openstack instance."""
    server_name = f"test-server-{test_id}"
    images: list[Image] = openstack_metadata.connection.search_images(openstack_image_name)
    assert images, "No built image found."
    try:
        server: Server = openstack_metadata.connection.create_server(
            name=server_name,
            image=images[0],
            key_name=openstack_metadata.ssh_key.keypair.name,
            auto_ip=False,
            # these are pre-configured values on private endpoint.
            security_groups=[openstack_security_group.name],
            flavor=openstack_metadata.flavor,
            network=openstack_metadata.network,
            timeout=60 * 20,
            wait=True,
        )
        yield server
    except openstack.exceptions.SDKException:
        server = openstack_metadata.connection.get_server(name_or_id=server_name)
        logger.exception("Failed to create server, %s", dict(server))
    finally:
        openstack_metadata.connection.delete_server(server_name, wait=True)
        for image in images:
            openstack_metadata.connection.delete_image(image.id)


@pytest.fixture(scope="module", name="proxy")
def proxy_fixture(pytestconfig: pytest.Config) -> types.ProxyConfig:
    """The environment proxy to pass on to the charm/testing model."""
    proxy = pytestconfig.getoption("--proxy")
    no_proxy = pytestconfig.getoption("--no-proxy")
    return types.ProxyConfig(http=proxy, https=proxy, no_proxy=no_proxy)


@pytest_asyncio.fixture(scope="module", name="ssh_connection")
async def ssh_connection_fixture(
    openstack_server: Server, openstack_metadata: OpenstackMeta, proxy: types.ProxyConfig
) -> SSHConnection:
    """The openstack server ssh connection fixture."""
    logger.info("Setting up SSH connection.")
    ssh_connection = await helpers.wait_for_valid_connection(
        connection=openstack_metadata.connection,
        server_name=openstack_server.name,
        network=openstack_metadata.network,
        ssh_key=openstack_metadata.ssh_key.private_key,
        proxy=proxy,
    )

    return ssh_connection


@pytest.fixture(scope="module", name="cli_run")
def cli_run_fixture(
    image: str,
    cloud_name: str,
    callback_script: Path,
    openstack_connection: Connection,
    openstack_image_name: str,
):
    """A CLI run.

    This fixture assumes pipx is installed in the system and the github-runner-image-builder has
    been installed using pipx. See testenv:integration section of tox.ini.
    """
    # This is a locally built application - we can trust it.
    subprocess.check_call(  # nosec: B603
        ["/usr/bin/sudo", Path.home() / ".local/bin/github-runner-image-builder", "init"]
    )
    subprocess.check_call(  # nosec: B603
        [
            "/usr/bin/sudo",
            Path.home() / ".local/bin/github-runner-image-builder",
            "run",
            cloud_name,
            openstack_image_name,
            "--base-image",
            image,
            "--keep-revisions",
            "2",
            "--callback-script",
            str(callback_script.absolute()),
        ]
    )

    yield

    openstack_image: Image
    for openstack_image in openstack_connection.search_images(openstack_image_name):
        openstack_connection.delete_image(openstack_image.id)
