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


# This is a class used for type hinting argparse.
class ActionsNamespace(argparse.Namespace):  # pylint: disable=too-few-public-methods
    """Action positional argument namespace.

    Attributes:
        action: CLI action positional argument.
        base_image: The base image to build.
        output: The output file path.
    """

    action: Literal["install", "build"]
    base_image: Literal["22.04", "jammy", "24.04", "noble"]
    output: str


def main(args: list[str] | None = None) -> None:
    """Run entrypoint for Github runner image builder CLI.

    Args:
        args: Command line arguments.
    """
    # The following line is used for unit testing.
    if args is None:  # pragma: nocover
        args = sys.argv[1:]

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
    build_parser.add_argument(
        "-o",
        "--output",
        dest="output",
        required=False,
        default="compressed.img",
    )
    parsed = cast(ActionsNamespace, parser.parse_args(args))

    if parsed.action == "install":
        builder.setup_builder()
        return

    config = BuildImageConfig(
        arch=get_supported_arch(), base_image=BaseImage.from_str(parsed.base_image)
    )
    builder.build_image(config=config, output=Path(parsed.output))
