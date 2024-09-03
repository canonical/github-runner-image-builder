# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module for interacting with external openstack VM image builder."""

import dataclasses
import logging
import pathlib
import shutil
import time

import fabric
import jinja2
import openstack
import openstack.compute.v2.flavor
import openstack.compute.v2.image
import openstack.compute.v2.keypair
import openstack.compute.v2.server
import openstack.connection
import openstack.exceptions
import openstack.image.v2.image
import openstack.key_manager
import openstack.key_manager.key_manager_service
import openstack.network.v2.network
import openstack.network.v2.subnet
import paramiko
import paramiko.ssh_exception
import tenacity
import yaml

import github_runner_image_builder.errors
from github_runner_image_builder import cloud_image, config, store
from github_runner_image_builder.config import IMAGE_DEFAULT_APT_PACKAGES, Arch, BaseImage

logger = logging.getLogger(__name__)

CLOUD_YAML_PATHS = (
    pathlib.Path("clouds.yaml"),
    pathlib.Path("~/clouds.yaml"),
    pathlib.Path("~/.config/openstack/clouds.yaml"),
    pathlib.Path("/etc/openstack/clouds.yaml"),
)

BUILDER_SSH_KEY_NAME = "image-builder-ssh-key"
BUILDER_KEY_PATH = pathlib.Path("/home/ubuntu/.ssh/builder_key")

SHARED_SECURITY_GROUP_NAME = "github-runner-image-builder-v1"
IMAGE_SNAPSHOT_FILE_PATH = pathlib.Path("github-runner-image-snapshot.img")

CREATE_SERVER_TIMEOUT = 5 * 60  # seconds

MIN_CPU = 2
MIN_RAM = 8192  # M
MIN_DISK = 20  # G


def determine_cloud(cloud_name: str | None = None) -> str:
    """Automatically determine cloud to use from clouds.yaml by selecting the first cloud.

    Args:
        cloud_name: str

    Raises:
        CloudsYAMLError: if clouds.yaml was not found.

    Returns:
        The cloud name to use.
    """
    # The cloud credentials may be stored in environment variable, trust user input if given.
    if cloud_name:
        return cloud_name
    logger.info("Determning cloud to use.")
    try:
        clouds_yaml_path = next(path for path in CLOUD_YAML_PATHS if path.exists())
    except StopIteration as exc:
        logger.exception("Unable to determine cloud to use from clouds.yaml files.")
        raise github_runner_image_builder.errors.CloudsYAMLError(
            "Unable to determine cloud to use from clouds.yaml files. "
            "Please check that clouds.yaml exists."
        ) from exc
    try:
        clouds_yaml = yaml.safe_load(clouds_yaml_path.read_text(encoding="utf-8"))
        cloud: str = list(clouds_yaml["clouds"].keys())[0]
    except (TypeError, yaml.error.YAMLError, KeyError, IndexError) as exc:
        logger.exception("Invalid clouds.yaml contents.")
        raise github_runner_image_builder.errors.CloudsYAMLError("Invalid clouds.yaml.") from exc
    return cloud


def initialize(arch: Arch, cloud_name: str) -> None:
    """Initialize the OpenStack external image builder.

    Upload ubuntu base images to openstack to use as builder base. This is a separate method to
    mitigate race conditions from happening during parallel runs (multiprocess) of the image
    builder, by creating shared resources beforehand.

    Args:
        arch: The architecture of the image to seed.
        cloud_name: The cloud to use from the clouds.yaml file.
    """
    logger.info("Initializing external builder.")
    logger.info("Downloading Jammy image.")
    jammy_image_path = cloud_image.download_and_validate_image(
        arch=arch, base_image=BaseImage.JAMMY
    )
    logger.info("Downloading Noble image.")
    noble_image_path = cloud_image.download_and_validate_image(
        arch=arch, base_image=BaseImage.NOBLE
    )
    logger.info("Uploading Jammy image.")
    store.upload_image(
        arch=arch,
        cloud_name=cloud_name,
        image_name=_get_base_image_name(arch=arch, base=BaseImage.JAMMY),
        image_path=jammy_image_path,
        keep_revisions=1,
    )
    logger.info("Uploading Noble image.")
    store.upload_image(
        arch=arch,
        cloud_name=cloud_name,
        image_name=_get_base_image_name(arch=arch, base=BaseImage.NOBLE),
        image_path=noble_image_path,
        keep_revisions=1,
    )

    with openstack.connect(cloud=cloud_name) as conn:
        logger.info("Creating keypair %s.", BUILDER_SSH_KEY_NAME)
        _create_keypair(conn=conn)
        logger.info("Creating security group %s.", SHARED_SECURITY_GROUP_NAME)
        _create_security_group(conn=conn)


def _get_base_image_name(arch: Arch, base: BaseImage) -> str:
    """Get formatted image name.

    Args:
        arch: The architecture of the image to use as build base.
        base: The ubuntu base image.

    Returns:
        The ubuntu base image name uploaded to OpenStack.
    """
    return f"image-builder-base-{base.value}-{arch.value}"


def _create_keypair(conn: openstack.connection.Connection) -> None:
    """Create an SSH Keypair to ssh into builder instance.

    Args:
        conn: The Openstach connection instance.
    """
    key = conn.get_keypair(name_or_id=BUILDER_SSH_KEY_NAME)
    if key and BUILDER_KEY_PATH.exists():
        return
    conn.delete_keypair(name=BUILDER_SSH_KEY_NAME)
    keypair = conn.create_keypair(name=BUILDER_SSH_KEY_NAME)
    BUILDER_KEY_PATH.write_text(keypair.private_key, encoding="utf-8")
    shutil.chown(BUILDER_KEY_PATH, user="ubuntu", group="ubuntu")
    BUILDER_KEY_PATH.chmod(0o400)


def _create_security_group(conn: openstack.connection.Connection) -> None:
    """Create a security group for builder instances.

    Args:
        conn: The Openstach connection instance.
    """
    if conn.get_security_group(name_or_id=SHARED_SECURITY_GROUP_NAME):
        return
    conn.create_security_group(
        name=SHARED_SECURITY_GROUP_NAME,
        description="For builders managed by the github-runner-image-builder.",
    )
    conn.create_security_group_rule(
        secgroup_name_or_id=SHARED_SECURITY_GROUP_NAME,
        protocol="icmp",
        direction="ingress",
        ethertype="IPv4",
    )
    conn.create_security_group_rule(
        secgroup_name_or_id=SHARED_SECURITY_GROUP_NAME,
        port_range_min="22",
        port_range_max="22",
        protocol="tcp",
        direction="ingress",
        ethertype="IPv4",
    )


@dataclasses.dataclass
class CloudConfig:
    """The OpenStack cloud configuration values.

    Attributes:
        cloud_name: The OpenStack cloud name to use.
        flavor: The OpenStack flavor to launch builder VMs on.
        network: The OpenStack network to launch the builder VMs on.
        proxy: The proxy to enable on builder VMs.
        upload_cloud_name: The OpenStack cloud name to upload the snapshot to. (Default same cloud)
    """

    cloud_name: str
    flavor: str
    network: str
    proxy: str
    upload_cloud_name: str | None


def run(
    cloud_config: CloudConfig,
    image_config: config.ImageConfig,
    keep_revisions: int,
) -> str:
    """Run external OpenStack builder instance and create a snapshot.

    Args:
        cloud_config: The OpenStack cloud configuration values for builder VM.
        image_config: The target image configuration values.
        keep_revisions: The number of image to keep for snapshot before deletion.

    Returns:
        The Openstack snapshot image ID.
    """
    cloud_init_script = _generate_cloud_init_script(
        arch=image_config.arch,
        base=image_config.base,
        runner_version=image_config.runner_version,
        proxy=cloud_config.proxy,
    )
    with openstack.connect(cloud=cloud_config.cloud_name) as conn:
        flavor = _determine_flavor(conn=conn, flavor_name=cloud_config.flavor)
        logger.info("Using flavor ID: %s.", flavor)
        network = _determine_network(conn=conn, network_name=cloud_config.network)
        logger.info("Using network ID: %s.", network)
        builder: openstack.compute.v2.server.Server = conn.create_server(
            name=_get_builder_name(arch=image_config.arch, base=image_config.base),
            image=_get_base_image_name(arch=image_config.arch, base=image_config.base),
            key_name=BUILDER_SSH_KEY_NAME,
            flavor=flavor,
            network=network,
            security_groups=[SHARED_SECURITY_GROUP_NAME],
            userdata=cloud_init_script,
            auto_ip=False,
            timeout=CREATE_SERVER_TIMEOUT,
            wait=True,
        )
        logger.info("Launched builder, waiting for cloud-init to complete: %s.", builder.id)
        _wait_for_cloud_init_complete(conn=conn, server=builder, ssh_key=BUILDER_KEY_PATH)
        image = store.create_snapshot(
            cloud_name=cloud_config.cloud_name,
            image_name=image_config.name,
            server=builder,
            keep_revisions=keep_revisions,
        )
        logger.info("Requested snapshot, waiting for snapshot to complete: %s.", image.id)
        _wait_for_snapshot_complete(conn=conn, image=image)
        if (
            cloud_config.upload_cloud_name
            # and cloud_config.cloud_name != cloud_config.upload_cloud_name
        ):
            logger.info("Downloading snapshot to %s.", IMAGE_SNAPSHOT_FILE_PATH)
            conn.download_image(
                name_or_id=image.id, output_file=IMAGE_SNAPSHOT_FILE_PATH, stream=True
            )
            logger.info("Uploading downloaded snapshot to %s.", cloud_config.upload_cloud_name)
            image = store.upload_image(
                arch=image_config.arch,
                cloud_name=cloud_config.upload_cloud_name,
                image_name=image_config.name,
                image_path=IMAGE_SNAPSHOT_FILE_PATH,
                keep_revisions=keep_revisions,
            )
            logger.info(
                "Uploaded snapshot on cloud %s, id: %s, name: %s",
                cloud_config.upload_cloud_name,
                image.id,
                image.name,
            )
        logger.info("Deleting builder VM: %s (%s)", builder.name, builder.id)
        conn.delete_server(name_or_id=builder.id, wait=True, timeout=5 * 60)
        logger.info("Image builder run complete.")
    return str(image.id)


def _determine_flavor(conn: openstack.connection.Connection, flavor_name: str | None) -> str:
    """Determine the flavor to use for the image builder.

    Args:
        conn: The OpenStack connection instance.
        flavor_name: Flavor name to use if given.

    Raises:
        FlavorNotFoundError: If no suitable flavor was found.
        FlavorRequirementsNotMetError: If the provided flavor does not meet minimum requirements.

    Returns:
        The flavor ID to use for launching builder VM.
    """
    if flavor_name:
        if not (flavor := conn.get_flavor(name_or_id=flavor_name)):
            logger.error("Given flavor %s not found.", flavor_name)
            raise github_runner_image_builder.errors.FlavorNotFoundError(
                f"Given flavor {flavor_name} not found."
            )
        logger.info("Flavor found, %s", flavor.name)
        if not (flavor.vcpus >= MIN_CPU and flavor.ram >= MIN_RAM and flavor.disk >= MIN_DISK):
            logger.error("Given flavor %s does not meet the minimum requirements.", flavor_name)
            raise github_runner_image_builder.errors.FlavorRequirementsNotMetError(
                f"Provided flavor {flavor_name} does not meet the minimum requirements."
                f"Required: CPU: {MIN_CPU} MEM: {MIN_RAM}M DISK: {MIN_DISK}G. "
                f"Got: CPU: {flavor.vcpus} MEM: {flavor.ram}M DISK: {flavor.disk}G."
            )
        return flavor.id
    flavors: list[openstack.compute.v2.flavor.Flavor] = conn.list_flavors()
    flavors = sorted(flavors, key=lambda flavor: (flavor.vcpus, flavor.ram, flavor.disk))
    for flavor in flavors:
        if flavor.vcpus >= MIN_CPU and flavor.ram >= MIN_RAM and flavor.disk >= MIN_DISK:
            logger.info("Flavor found, %s", flavor.name)
            return flavor.id
    raise github_runner_image_builder.errors.FlavorNotFoundError("No suitable flavor found.")


def _determine_network(conn: openstack.connection.Connection, network_name: str | None) -> str:
    """Determine the network to use for the image builder.

    Args:
        conn: The OpenStack connection instance.
        network_name: Network name to use if given.

    Raises:
        NetworkNotFoundError: If no suitable network was found.

    Returns:
        The network to use for launching builder VM.
    """
    if network_name:
        if not (network := conn.get_network(name_or_id=network_name)):
            logger.error("Given network %s not found.", network_name)
            raise github_runner_image_builder.errors.NetworkNotFoundError(
                f"Given network {network_name} not found."
            )
        logger.info("Network found, %s", network.name)
        return network.id
    networks: list[openstack.network.v2.network.Network] = conn.list_networks()
    # Only a single valid subnet should exist per environment.
    subnets: list[openstack.network.v2.subnet.Subnet] = conn.list_subnets()
    if not subnets:
        logger.error("No valid subnets found.")
        raise github_runner_image_builder.errors.NetworkNotFoundError("No valid subnets found.")
    subnet = subnets[0]
    for network in networks:
        if subnet.id in network.subnet_ids:
            logger.info("Network found, %s", network.name)
            return network.id
    raise github_runner_image_builder.errors.NetworkNotFoundError("No suitable network found.")


def _generate_cloud_init_script(
    arch: Arch,
    base: BaseImage,
    runner_version: str,
    proxy: str,
) -> str:
    """Generate userdata for installing GitHub runner image components.

    Args:
        arch: The GitHub runner architecture to download.
        base: The ubuntu base image.
        runner_version: The GitHub runner version to pin.
        proxy: The proxy to enable while setting up the VM.

    Returns:
        The cloud-init script to create snapshot image.
    """
    env = jinja2.Environment(
        loader=jinja2.PackageLoader("github_runner_image_builder", "templates"),
        autoescape=jinja2.select_autoescape(),
    )
    template = env.get_template("cloud-init.sh.j2")
    return template.render(
        PROXY_URL=proxy,
        APT_PACKAGES=" ".join(IMAGE_DEFAULT_APT_PACKAGES),
        HWE_VERSION=BaseImage.get_version(base),
        RUNNER_VERSION=runner_version,
        RUNNER_ARCH=arch.value,
    )


def _get_builder_name(arch: Arch, base: BaseImage) -> str:
    """Get builder VM name.

    Args:
        arch: The architecture of the image to seed.
        base: The ubuntu base image.

    Returns:
        The builder VM name launched on OpenStack.
    """
    return f"image-builder-{base.value}-{arch.value}"


@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=2, max=30),
    # retry if False is returned
    retry=tenacity.retry_if_result(lambda result: not result),
    reraise=True,
)
def _wait_for_cloud_init_complete(
    conn: openstack.connection.Connection,
    server: openstack.compute.v2.server.Server,
    ssh_key: pathlib.Path,
) -> bool:
    """Wait until the userdata has finished installing expected components.

    Args:
        conn: The Openstach connection instance.
        server: The OpenStack server instance to check if cloud_init is complete.
        ssh_key: The key to SSH RSA key to connect to the OpenStack server instance.

    Raises:
        CloudInitFailError: if there was an error running cloud-init status command.

    Returns:
        Whether the cloud init is complete. Used for tenacity retry to pick up return value.
    """
    ssh_connection = _get_ssh_connection(conn=conn, server=server, ssh_key=ssh_key)
    result: fabric.Result | None = ssh_connection.run("cloud-init status --wait", timeout=60 * 10)
    if not result or not result.ok:
        logger.error("cloud-init status command failure, result: %s.", result)
        raise github_runner_image_builder.errors.CloudInitFailError("Invalid cloud-init status")
    return "status: done" in result.stdout


@tenacity.retry(wait=tenacity.wait_exponential(multiplier=2, max=30), reraise=True)
def _get_ssh_connection(
    conn: openstack.connection.Connection,
    server: openstack.compute.v2.server.Server,
    ssh_key: pathlib.Path,
) -> fabric.Connection:
    """Get a valid SSH connection to OpenStack instance.

    Args:
        conn: The Openstach connection instance.
        server: The OpenStack server instance to check if cloud_init is complete.
        ssh_key: The key to SSH RSA key to connect to the OpenStack server instance.

    Raises:
        AddressNotFoundError: If there was no valid address to get SSH connection.

    Returns:
        The SSH Connection instance.
    """
    server = conn.get_server(name_or_id=server.id)
    network_address_list = server.addresses.values()
    if not network_address_list:
        logger.error("Server address not found, %s.", server.name)
        raise github_runner_image_builder.errors.AddressNotFoundError(
            f"No addresses found for OpenStack server {server.name}"
        )

    server_addresses: list[str] = [
        address["addr"]
        for network_addresses in network_address_list
        for address in network_addresses
    ]
    for ip in server_addresses:
        try:
            connection = fabric.Connection(
                host=ip,
                user="ubuntu",
                connect_kwargs={"key_filename": str(ssh_key)},
                connect_timeout=30,
            )
            result: fabric.Result | None = connection.run(
                "echo hello world", warn=True, timeout=30
            )
            if not result or not result.ok:
                logger.warning(
                    "SSH test connection failed, server: %s, address: %s", server.name, ip
                )
                continue
            if "hello world" in result.stdout:
                return connection
        except (
            paramiko.ssh_exception.NoValidConnectionsError,
            TimeoutError,
            paramiko.ssh_exception.SSHException,
        ):
            logger.warning(
                "Unable to SSH into %s with address %s",
                server.name,
                connection.host,
                exc_info=True,
            )
            continue
    logger.error("Server SSH address not found, %s.", server.name)
    raise github_runner_image_builder.errors.AddressNotFoundError(
        f"No connectable SSH addresses found, server: {server.name}, "
        f"addresses: {server_addresses}"
    )


def _wait_for_snapshot_complete(
    conn: openstack.connection.Connection, image: openstack.image.v2.image.Image
) -> None:
    """Wait until snapshot has been completed and is ready to be used.

    Args:
        conn: The Openstach connection instance.
        image: The OpenStack server snapshot image to check is complete.

    Raises:
        TimeoutError: if the image snapshot took too long to complete.
    """
    for _ in range(10):
        image = conn.get_image(name_or_id=image.id)
        if image.status == "active":
            return
        time.sleep(60)
    image = conn.get_image(name_or_id=image.id)
    if not image.status == "active":
        logger.error("Timed out waiting for snapshot to be active, %s.", image.name)
        raise TimeoutError(f"Timed out waiting for snapshot to be active, {image.id}.")
