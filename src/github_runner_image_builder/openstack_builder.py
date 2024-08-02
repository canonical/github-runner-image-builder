# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module for interacting with external openstack VM image builder."""

import pathlib
import shutil

import openstack
import openstack.compute.v2.server
import openstack.connection
import openstack.image.v2.image
import yaml

from github_runner_image_builder import cloud_image, store
from github_runner_image_builder.config import Arch, BaseImage

BUILDER_SSH_KEY_NAME = "image-builder-ssh-key"
BUILDER_KEY_PATH = pathlib.Path("/home/ubuntu/.ssh/builder_key")

SHARED_SECURITY_GROUP_NAME = "github-runner-image-builder-v1"


def determine_cloud(cloud_name: str | None) -> str:
    """Automatically determine cloud to use from clouds.yaml by selecting the first cloud.

    Args:
        cloud_name: str

    Raises:
        ValueError: if clouds.yaml was not found.
    """
    if cloud_name:
        return cloud_name
    clouds_yaml_path: pathlib.Path | None
    for path in (
        pathlib.Path("clouds.yaml"),
        pathlib.Path("~/clouds.yaml"),
        pathlib.Path("~/.config/openstack/clouds.yaml"),
        pathlib.Path("/etc/openstack/clouds.yaml"),
    ):
        if path.exists():
            clouds_yaml_path = path
            break
    if not clouds_yaml_path:
        raise ValueError(
            "Unable to determine cloud to use from clouds.yaml files. "
            "Please check that clouds.yaml exists."
        )
    try:
        clouds_yaml = yaml.safe_load(clouds_yaml_path.read_text(encoding="utf-8"))
        cloud: str = list(clouds_yaml["clouds"].keys())[0]
    except (TypeError, yaml.error.YAMLError, KeyError) as exc:
        raise ValueError("Invalid clouds.yaml.") from exc
    return cloud


def initialize(arch: Arch, cloud_name: str):
    """Initialize the OpenStack external image builder.

    Upload ubuntu base images to openstack to use as builder base. This is a separate method to
    mitigate race conditions from happening during parallel runs (multiprocess) of the image
    builder, by creating shared resources beforehand.

    Args:
        arch: The architecture of the image to seed.
        cloud_name: The cloud to use from the clouds.yaml file.
    """
    jammy_image_path = cloud_image.download_and_validate_image(
        arch=arch, base_image=BaseImage.JAMMY
    )
    noble_image_path = cloud_image.download_and_validate_image(
        arch=arch, base_image=BaseImage.NOBLE
    )
    store.upload_image(
        arch=arch,
        cloud_name=cloud_name,
        image_name=_get_seed_image_name(arch=arch, base=BaseImage.JAMMY),
        image_path=jammy_image_path,
        keep_revisions=1,
    )
    store.upload_image(
        arch=arch,
        cloud_name=cloud_name,
        image_name=_get_seed_image_name(arch=arch, base=BaseImage.NOBLE),
        image_path=noble_image_path,
        keep_revisions=1,
    )

    with openstack.connect(cloud=cloud_name) as conn:
        _create_keypair(conn=conn)
        _create_security_group(conn=conn)


def _get_seed_image_name(arch: Arch, base: BaseImage) -> str:
    """Get formatted image name.

    Args:
        arch: The architecture of the image to seed.
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
    if conn.get_keypair(name=BUILDER_SSH_KEY_NAME):
        return
    keypair = conn.create_keypair(name=BUILDER_SSH_KEY_NAME)
    BUILDER_KEY_PATH.write_text(keypair.private_key)
    shutil.chown(BUILDER_KEY_PATH, user="ubuntu", group="ubuntu")
    BUILDER_KEY_PATH.chmod(0o400)


def _create_security_group(conn: openstack.connection.Connection) -> None:
    """Create a security group for builder instances.

    Args:
        conn: The Openstach connection instance.
    """
    if conn.get_security_group(name=BUILDER_SSH_KEY_NAME):
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


def run(
    arch: Arch, base: BaseImage, cloud_name: str, flavor: str, network: str, runner_version: str
) -> str:
    """Run external OpenStack builder instance and create a snapshot.

    Args:
        arch: The architecture of the image to seed.
        base: The Ubuntu base to use as builder VM base.
        cloud_name: The cloud to use from the clouds.yaml file.
        flavor: The openstack flavor to create the builder server on.
        network: The openstack network to assign the builder server to.
        runner_version: The GitHub runner version to install on the VM. Defaults to latest.

    Returns:
        The Openstack snapshot image ID.
    """
    flavor = _determine_flavor(flavor_name=flavor)
    network = _determine_network(flavor_name=network)
    installation_script = _generate_cloud_init_script(runner_version=runner_version)
    with openstack.connect(cloud=cloud_name) as conn:
        builder: openstack.compute.v2.server.Server = conn.create_server(
            name=_get_builder_name(arch=arch, base=base),
            image=_get_seed_image_name(arch=arch, base=base),
            key_name=BUILDER_SSH_KEY_NAME,
            flavor=flavor,
            network=network,
            security_groups=[SHARED_SECURITY_GROUP_NAME],
            userdata=installation_script,
            auto_ip=False,
            timeout=5 * 60,
            wait=True,
        )
        _wait_for_cloud_init_complete(builder)
        image: openstack.image.v2.image.Image = conn.create_image_snapshot()
        _wait_for_snapshot_complete(image)
    return str(image.id)


def _determine_flavor(flavor_name: str | None) -> str:
    """Determine the flavor to use for the image builder.

    Args:
        flavor_name: Flavor name to use if given.

    Raises:
        ValueError: If no suitable flavor was found.

    Returns:
        The flavor to use for launching builder VM.
    """
    pass


def _determine_network(network_name: str | None) -> str:
    """Determine the network to use for the image builder.

    Args:
        network_name: Network name to use if given.

    Raises:
        ValueError: If no suitable network was found.

    Returns:
        The network to use for launching builder VM.
    """
    pass


def _generate_cloud_init_script(runner_version: str):
    """Generate userdata for installing GitHub runner image components."""
    pass


def _get_builder_name(arch: Arch, base: BaseImage) -> str:
    """Get builder VM name.

    Args:
        arch: The architecture of the image to seed.
        base: The ubuntu base image.

    Returns:
        The builder VM name lauched on OpenStack.
    """
    return f"image-builder-{base.value}-{arch.value}"


def _wait_for_cloud_init_complete(server: openstack.compute.v2.server.Server):
    """Wait until the userdata has finished installing expected components."""
    pass


def _wait_for_snapshot_complete(image: openstack.image.v2.image.Image):
    """Wait until snapshot has been completed and is ready to be used."""
    pass
