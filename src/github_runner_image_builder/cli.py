# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Main entrypoint for github-runner-image-builder cli application."""
import argparse
import itertools
import subprocess
import sys
from pathlib import Path
from typing import cast

from github_runner_image_builder import builder
from github_runner_image_builder.builder import BuildImageConfig
from github_runner_image_builder.config import (
    IMAGE_OUTPUT_PATH,
    LTS_IMAGE_VERSION_TAG_MAP,
    ActionsNamespace,
    BaseImage,
    get_supported_arch,
)
from github_runner_image_builder.upload import OpenstackManager, UploadImageConfig


def _existing_path(value: str) -> Path:
    """Check the path exists.

    Args:
        value: The path string.

    Raises:
        ValueError: If the path does not exist.

    Returns:
        Path that exists.
    """
    path = Path(value)
    if not path.exists():
        raise ValueError(f"Given path {value} not found.")
    return path


def _install() -> None:
    """Install builder."""
    builder.setup_builder()


def _build_and_upload(
    base: str, cloud_name: str, num_revisions: int, callback_script_path: Path
) -> None:
    """Build and upload image.

    Args:
        base: Ubuntu image base.
        cloud_name: The Openstack cloud to upload the image to.
        num_revisions: Number of image revisions to keep before deletion.
        callback_script_path: Path to bash script to call after image upload.
    """
    arch = get_supported_arch()
    base_image = BaseImage.from_str(base)
    build_config = BuildImageConfig(arch=arch, base_image=base_image)
    builder.build_image(config=build_config)
    with OpenstackManager(cloud_name=cloud_name) as manager:
        image_id = manager.upload_image(
            config=UploadImageConfig(
                arch=arch,
                app_name="TBD",
                base=base_image,
                num_revisions=num_revisions,
                src_path=IMAGE_OUTPUT_PATH,
            )
        )
    subprocess.check_call([str(callback_script_path), image_id])


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
        "-c",
        "--cloud-name",
        dest="cloud_name",
        required=True,
        help=(
            "The cloud to use from the clouds.yaml file. The CLI looks for clouds.yaml in paths "
            "of the following order: current directory, ~/.config/openstack, /etc/openstack."
        ),
    )
    build_parser.add_argument(
        "-n",
        "--num-revisions",
        dest="num_revisions",
        required=False,
        type=int,
        default=5,
        help="The maximum number of images to keep before deletion.",
    )
    build_parser.add_argument(
        "-p",
        "--callback-script-path",
        dest="callback_script_path",
        required=True,
        type=_existing_path,
        help=(
            "The callback script to trigger after image is built. The callback script is called"
            "with the first argument as the image ID."
        ),
    )
    parsed = cast(ActionsNamespace, parser.parse_args(args))

    if parsed.action == "install":
        _install()
        return

    _build_and_upload(
        base=parsed.base,
        cloud_name=parsed.cloud_name,
        num_revisions=parsed.num_revisions,
        callback_script_path=parsed.callback_script_path,
    )
