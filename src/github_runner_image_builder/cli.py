# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Main entrypoint for github-runner-image-builder cli application."""
import argparse
import itertools
from typing import Literal, cast

from github_runner_image_builder import builder
from github_runner_image_builder.builder import BuildImageConfig
from github_runner_image_builder.config import (
    LTS_IMAGE_VERSION_TAG_MAP,
    BaseImage,
    get_supported_arch,
)


# This is a class used for type hinting argparse.
class ActionsNamespace(argparse.Namespace):  # pylint: disable=too-few-public-methods
    """Action positional argument namespace.

    Attributes:
        action: CLI action positional argument.
        base_image: The base image to build.
    """

    action: Literal["install", "build"]
    base_image: Literal["22.04", "jammy", "24.04", "noble"]


def main() -> None | str:
    """Run entrypoint for Github runner image builder CLI.

    Returns:
        The build image path if build mode. None otherwise.
    """
    parser = argparse.ArgumentParser(
        prog="Github runner image builder CLI",
        description="Builds github runner image and uploads it to openstack.",
    )
    subparsers = parser.add_subparsers(
        title="actions",
        description="command modes for Github runner image builder CLI.",
        dest="action",
    )
    subparsers.add_parser("install")
    build_parser = subparsers.add_parser("build")
    build_parser.add_argument(
        "-i",
        "--base-image",
        dest="base_image",
        required=False,
        choices=tuple(
            itertools.chain.from_iterable(
                (tag, name) for (tag, name) in LTS_IMAGE_VERSION_TAG_MAP.items()
            )
        ),
        default="jammy",
    )
    parsed = cast(ActionsNamespace, parser.parse_args())

    if parsed.action == "install":
        builder.setup_builder()
        return None

    config = BuildImageConfig(
        arch=get_supported_arch(), base_image=BaseImage.from_str(parsed.base_image)
    )
    return builder.build_image(config=config)
