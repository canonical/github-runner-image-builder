# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Main entrypoint for github-runner-image-builder cli application."""

# Subprocess module is used to execute trusted commands
import subprocess  # nosec: B404
from pathlib import Path

import click

from github_runner_image_builder import builder, logging, openstack_builder, store
from github_runner_image_builder.config import (
    BASE_CHOICES,
    IMAGE_OUTPUT_PATH,
    LOG_LEVELS,
    BaseImage,
    get_supported_arch,
)


@click.option(
    "--log-level",
    type=click.Choice(LOG_LEVELS),
    default="info",
    help="Configure logging verbosity.",
)
@click.group()
def main(log_level: str | int) -> None:
    """Run entrypoint for Github runner image builder CLI.

    Args:
        log_level: The logging verbosity to apply.
    """
    logging.configure(log_level=log_level)


@main.command(name="init")
@click.option(
    "--experimental-external",
    default=False,
    help="EXPERIMENTAL: Use external Openstack builder to build images.",
)
@click.option(
    "--cloud-name",
    default="",
    help="The cloud to use from the clouds.yaml file. The CLI looks for clouds.yaml in paths of "
    "the following order: current directory, ~/.config/openstack, /etc/openstack.",
)
def initialize(experimental_external: bool, cloud_name: str) -> None:
    """Initialize builder CLI function wrapper.

    Args:
        experimental_external: Whether to use external Openstack builder to build images.
        cloud_name: The cloud name to use from clouds.yaml.
    """
    if not experimental_external:
        builder.initialize()
        return
    arch = get_supported_arch()

    openstack_builder.initialize(
        arch=arch, cloud_name=openstack_builder.determine_cloud(cloud_name=cloud_name)
    )


@main.command(name="latest-build-id")
@click.argument("cloud_name")
@click.argument("image_name")
def get_latest_build_id(cloud_name: str, image_name: str) -> None:
    # Click arguments do not take help parameter, display help through docstrings.
    """Get latest build ID of <image_name> from Openstack <cloud_name>.

    Args:
        cloud_name: The cloud to use from the clouds.yaml file. The CLI looks for clouds.yaml in
            paths of the following order: current directory, ~/.config/openstack, /etc/openstack.
        image_name: The image name uploaded to Openstack.
    """
    click.echo(
        message=store.get_latest_build_id(cloud_name=cloud_name, image_name=image_name),
        nl=False,
    )


@main.command(name="run")
@click.argument("cloud_name")
@click.argument("image_name")
@click.option(
    "-b",
    "--base-image",
    type=click.Choice(BASE_CHOICES),
    default="noble",
    help=("The Ubuntu base image to use as build base."),
)
@click.option(
    "-k",
    "--keep-revisions",
    default=5,
    help="The maximum number of images to keep before deletion.",
)
@click.option(
    "-s",
    "--callback-script",
    type=click.Path(exists=True),
    default=None,
    help=(
        "The callback script to trigger after image is built. The callback script is called"
        "with the first argument as the image ID."
    ),
)
@click.option(
    "--runner-version",
    default="",
    help=(
        "The GitHub runner version to install, e.g. 2.317.0. "
        "See github.com/actions/runner/releases/."
        "Defaults to latest version."
    ),
)
@click.option(
    "--experimental-external",
    default=False,
    help="EXPERIMENTAL: Use external Openstack builder to build images.",
)
@click.option(
    "--flavor",
    default="",
    help="EXPERIMENTAL: OpenStack flavor to launch for external build run VMs. "
    "Ignored if --experimental-external is not enabled",
)
@click.option(
    "--network",
    default="",
    help="EXPERIMENTAL: OpenStack network to launch the external build run VMs under. "
    "Ignored if --experimental-external is not enabled",
)
@click.option(
    "--proxy",
    default="",
    help="EXPERIMENTAL: Proxy to use for external build VMs in host:port format (without scheme). "
    "Ignored if --experimental-external is not enabled",
)
@click.option(
    "--upload-cloud",
    default="",
    help="EXPERIMENTAL: Different cloud to use to upload the externally built image. The cloud "
    "connection parameters should exist in the clouds.yaml. Ignored if --experimental-external is"
    " not enabled",
)
# click doesn't yet support dataclasses, hence all arguments are required.
def run(  # pylint: disable=too-many-arguments
    cloud_name: str,
    image_name: str,
    base_image: str,
    keep_revisions: int,
    callback_script: Path | None,
    runner_version: str,
    experimental_external: bool,
    flavor: str,
    network: str,
    proxy: str,
    upload_cloud: str,
) -> None:
    """Build a cloud image using chroot and upload it to OpenStack.

    Args:
        cloud_name: The cloud to use from the clouds.yaml file. The CLI looks for clouds.yaml in
            paths of the following order: current directory, ~/.config/openstack, /etc/openstack.
        image_name: The image name uploaded to Openstack.
        base_image: The Ubuntu base image to use as build base.
        keep_revisions: Number of past revisions to keep before deletion.
        callback_script: Script to callback after a successful build.
        runner_version: GitHub runner version to pin.
        experimental_external: Whether to use external OpenStack builder.
        flavor: The Openstack flavor to create server to build images.
        network: The Openstack network to assign to server to build images.
        proxy: Proxy to use for external build VMs.
        upload_cloud: The Opensttack cloud to use to upload externally built image.
    """
    arch = get_supported_arch()
    base = BaseImage.from_str(base_image)
    if not experimental_external:
        builder.run(arch=arch, base_image=base, runner_version=runner_version)
        image_id = store.upload_image(
            arch=arch,
            cloud_name=cloud_name,
            image_name=image_name,
            image_path=IMAGE_OUTPUT_PATH,
            keep_revisions=keep_revisions,
        )
    else:
        image_id = openstack_builder.run(
            arch=arch,
            base=base,
            cloud_config=openstack_builder.CloudConfig(
                cloud_name=cloud_name,
                flavor=flavor,
                network=network,
                proxy=proxy,
                upload_cloud_name=upload_cloud,
            ),
            runner_version=runner_version,
            keep_revisions=keep_revisions,
        )
    if callback_script:
        # The callback script is a user trusted script.
        subprocess.check_call([str(callback_script), image_id])  # nosec: B603
