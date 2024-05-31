# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Main entrypoint for github-runner-image-builder cli application."""
import argparse
import itertools

# Subprocess module is used to execute trusted commands
import subprocess  # nosec: B404
import sys
from pathlib import Path
from typing import cast

from github_runner_image_builder import builder, store
from github_runner_image_builder.config import (
    ACTION_INIT,
    ACTION_LATEST_BUILD_ID,
    ACTION_RUN,
    IMAGE_OUTPUT_PATH,
    LTS_IMAGE_VERSION_TAG_MAP,
    ActionsNamespace,
    BaseImage,
    get_supported_arch,
)


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
    subparsers.add_parser(ACTION_INIT)
    get_latest_id_parser = subparsers.add_parser(
        ACTION_LATEST_BUILD_ID, description="Fetch the latest ID of the built image."
    )
    run_parser = subparsers.add_parser(ACTION_RUN, description="Build the image.")
    get_latest_id_parser.add_argument(
        dest="cloud_name",
        help=(
            "The cloud to use from the clouds.yaml file. The CLI looks for clouds.yaml in paths "
            "of the following order: current directory, ~/.config/openstack, /etc/openstack."
        ),
        type=non_empty_string,
    )
    get_latest_id_parser.add_argument(
        dest="image_name",
        help="The image name uploaded to Openstack.",
        type=non_empty_string,
    )
    run_parser.add_argument(
        dest="cloud_name",
        help=(
            "The cloud to use from the clouds.yaml file. The CLI looks for clouds.yaml in paths "
            "of the following order: current directory, ~/.config/openstack, /etc/openstack."
        ),
        type=non_empty_string,
    )
    run_parser.add_argument(
        dest="image_name",
        help="The image name to upload to Openstack.",
        type=non_empty_string,
    )
    run_parser.add_argument(
        "-b",
        "--base-image",
        dest="base",
        required=False,
        choices=tuple(
            itertools.chain.from_iterable(
                (tag, name) for (tag, name) in LTS_IMAGE_VERSION_TAG_MAP.items()
            )
        ),
        default="noble",
    )
    run_parser.add_argument(
        "-k",
        "--keep-revisions",
        dest="keep_revisions",
        required=False,
        type=int,
        default=5,
        help="The maximum number of images to keep before deletion.",
    )
    run_parser.add_argument(
        "-s",
        "--callback-script",
        dest="callback_script_path",
        required=False,
        type=_existing_path,
        help=(
            "The callback script to trigger after image is built. The callback script is called"
            "with the first argument as the image ID."
        ),
    )
    options = cast(ActionsNamespace, parser.parse_args(args))
    if options.action == "init":
        builder.initialize()
        return

    if options.action == "latest-build-id":
        print(
            store.get_latest_build_id(
                cloud_name=options.cloud_name, image_name=options.image_name
            ),
            end=None,
        )
        return

    _build_and_upload(
        base=options.base,
        cloud_name=options.cloud_name,
        image_name=options.image_name,
        keep_revisions=options.keep_revisions,
        callback_script_path=options.callback_script_path,
    )


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


def non_empty_string(arg: str) -> str:
    """Check that the argument is non-empty.

    Args:
        arg: The argument to check.

    Raises:
        ValueError: If the argument is empty.

    Returns:
        Non-empty string.
    """
    arg = str(arg)
    if not arg:
        raise ValueError("Must not be empty string")
    return arg


def _build_and_upload(
    base: str,
    cloud_name: str,
    image_name: str,
    keep_revisions: int,
    callback_script_path: Path | None = None,
) -> None:
    """Build and upload image.

    Args:
        base: Ubuntu image base.
        cloud_name: The Openstack cloud to upload the image to.
        image_name: The image name to upload as.
        keep_revisions: Number of image revisions to keep before deletion.
        callback_script_path: Path to bash script to call after image upload.
    """
    arch = get_supported_arch()
    base_image = BaseImage.from_str(base)
    builder.build_image(arch=arch, base_image=base_image)
    image_id = store.upload_image(
        cloud_name=cloud_name,
        image_name=image_name,
        image_path=IMAGE_OUTPUT_PATH,
        keep_revisions=keep_revisions,
    )
    if callback_script_path:
        # The callback script is a user trusted script.
        subprocess.check_call(["/bin/bash", str(callback_script_path), image_id])  # nosec: B603
