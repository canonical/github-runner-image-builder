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
        base: The base image to build.
        output: Path of the output image file.
    """

    action: Literal["install", "build"]
    base: Literal["22.04", "jammy", "24.04", "noble"]
    output: str


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


def _build(base: str, output: str) -> None:
    """Build and upload image.

    Args:
        base: Ubuntu image base.
        output: The build image output path.
    """
    arch = get_supported_arch()
    output_path = Path(output)
    build_config = BuildImageConfig(
        arch=arch, base_image=BaseImage.from_str(base), output=output_path
    )
    builder.build_image(config=build_config)


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
        "-o", "--output", dest="output", required=True, type=non_empty_string
    )
    parsed = cast(ActionsNamespace, parser.parse_args(args))

    if parsed.action == "install":
        _install()
        return

    _build(base=parsed.base, output=parsed.output)
