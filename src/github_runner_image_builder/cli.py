# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Main entrypoint for github-runner-image-builder cli application."""
import argparse
import itertools
import sys
from pathlib import Path
from typing import Literal, cast

from github_runner_image_builder import builder
from github_runner_image_builder.builder import BuildImageConfig
from github_runner_image_builder.config import (
    LTS_IMAGE_VERSION_TAG_MAP,
    BaseImage,
    get_supported_arch,
)
from github_runner_image_builder.openstack_manager import OpenstackManager, UploadImageConfig


# This is a class used for type hinting argparse.
class ActionsNamespace(argparse.Namespace):  # pylint: disable=too-few-public-methods
    """Action positional argument namespace.

    Attributes:
        action: CLI action positional argument.
        base: The base image to build.
        revision_history: Maximum number of images to keep before deletion.
        cloud: The Openstack cloud name to use.
        name: The image name to upload to openstack.
    """

    action: Literal["install", "build", "get-latest"]
    base: Literal["22.04", "jammy", "24.04", "noble"]
    revision_history: int
    cloud: str
    name: str


def non_empty_string(value: str) -> str:
    """Check the string is non-empty.

    Args:
        value: The string value to check.

    Raises:
        ValueError: If empty string was received.

    Returns:
        Non-empty string value.
    """
    if not value:
        raise ValueError("Empty string.")
    return value


def _install() -> None:
    """Install builder."""
    builder.setup_builder()


def _get_latest(cloud: str, name: str) -> str:
    """Fetch latest image from Openstack.

    Args:
        cloud: Openstack cloud name to load from clouds.yaml.
        name: Openstack image name to upload as.

    Returns:
        The latest image ID if available.
    """
    with OpenstackManager(cloud_name=cloud) as manager:
        return manager.get_latest_image_id(name=name) or ""


def _build(base: str, cloud: str, name: str, num_revisions: int) -> str:
    """Build and upload image.

    Args:
        base: Ubuntu image base.
        cloud: Openstack cloud name to load from clouds.yaml.
        name: Openstack image name to upload as.
        num_revisions: Maximum number of revisions to keep before deletion.

    Returns:
        The built image ID.
    """
    arch = get_supported_arch()
    output = Path("compressed.img")
    build_config = BuildImageConfig(arch=arch, base_image=BaseImage.from_str(base), output=output)
    builder.build_image(config=build_config)

    upload_config = UploadImageConfig(name=name, num_revisions=num_revisions, path=output)
    with OpenstackManager(cloud_name=cloud) as manager:
        return manager.upload_image(config=upload_config)


def main(args: list[str] | None = None) -> None:
    """Run entrypoint for Github runner image builder CLI.

    Args:
        args: Command line arguments.
    """
    # The following line is used for unit testing.
    if args is None:  # pragma: nocover
        args = sys.argv[1:]

    print(args)
    parser = argparse.ArgumentParser(
        prog="Github runner image builder CLI",
        description="Builds github runner image and uploads it to openstack.",
    )
    subparsers = parser.add_subparsers(
        title="actions",
        description="command modes for Github runner image builder CLI.",
        dest="action",
        required=True,
    )
    subparsers.add_parser("install")
    get_parser = subparsers.add_parser("get-latest")
    get_parser.add_argument("-c", "--cloud", dest="cloud", required=True, type=non_empty_string)
    get_parser.add_argument("-n", "--name", dest="name", required=True, type=non_empty_string)
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument(
        "-i",
        "--image-base",
        dest="base",
        required=False,
        choices=tuple(
            itertools.chain.from_iterable(
                (tag, name) for (tag, name) in LTS_IMAGE_VERSION_TAG_MAP.items()
            )
        ),
        default="jammy",
    )
    build_parser.add_argument(
        "-r",
        "--revision-history",
        dest="revision_history",
        required=False,
        default=5,
        type=int,
        choices=list(range(2, 11)),
    )
    build_parser.add_argument("-c", "--cloud", dest="cloud", required=True, type=non_empty_string)
    build_parser.add_argument("-n", "--name", dest="name", required=True, type=non_empty_string)
    parsed = cast(ActionsNamespace, parser.parse_args(args))

    if parsed.action == "install":
        _install()
        return

    if parsed.action == "get-latest":
        print(_get_latest(cloud=parsed.cloud, name=parsed.name))
        return

    print(
        _build(
            base=parsed.base,
            cloud=parsed.cloud,
            name=parsed.name,
            num_revisions=parsed.revision_history,
        )
    )
    return
