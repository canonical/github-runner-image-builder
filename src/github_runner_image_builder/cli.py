# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Main entrypoint for github-runner-image-builder cli application."""
# Subprocess module is used to execute trusted commands
import subprocess  # nosec: B404
from pathlib import Path

import click

from github_runner_image_builder import builder, store
from github_runner_image_builder.config import (
    BASE_CHOICES,
    IMAGE_OUTPUT_PATH,
    BaseImage,
    get_supported_arch,
)


@click.group()
def main() -> None:
    """Run entrypoint for Github runner image builder CLI."""


@main.command(name="init")
def initialize() -> None:
    """Initialize builder CLI function wrapper."""
    builder.initialize()


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
    "-r",
    "--runner-version",
    default="",
    help=(
        "The GitHub runner version to install, e.g. 2.317.0. "
        "See github.com/actions/runner/releases/."
        "Defaults to latest version."
    ),
)
# click doesn't yet support dataclasses, hence all arguments are required.
def run(  # pylint: disable=too-many-arguments
    cloud_name: str,
    image_name: str,
    base_image: str,
    keep_revisions: int,
    callback_script: Path | None,
    runner_version: str,
) -> None:
    """Run build function wrapper.

    Args:
        cloud_name: The cloud to use from the clouds.yaml file. The CLI looks for clouds.yaml in
            paths of the following order: current directory, ~/.config/openstack, /etc/openstack.
        image_name: The image name uploaded to Openstack.
        base_image: The Ubuntu base image to use as build base.
        keep_revisions: Number of past revisions to keep before deletion.
        callback_script: Script to callback after a successful build.
        runner_version: GitHub runner version to pin.
    """
    arch = get_supported_arch()
    base = BaseImage.from_str(base_image)
    builder.build_image(arch=arch, base_image=base, runner_version=runner_version)
    image_id = store.upload_image(
        arch=arch,
        cloud_name=cloud_name,
        image_name=image_name,
        image_path=IMAGE_OUTPUT_PATH,
        keep_revisions=keep_revisions,
    )
    if callback_script:
        # The callback script is a user trusted script.
        subprocess.check_call([str(callback_script), image_id])  # nosec: B603
