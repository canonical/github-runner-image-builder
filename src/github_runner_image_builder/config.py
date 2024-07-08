# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module containing configurations."""

import argparse
import logging
import platform
from enum import Enum
from pathlib import Path
from typing import Literal

from github_runner_image_builder.errors import UnsupportedArchitectureError

logger = logging.getLogger(__name__)

ACTION_INIT = "init"
ACTION_RUN = "run"
ACTION_LATEST_BUILD_ID = "latest-build-id"


# This is a class used for type hinting argparse.
class ActionsNamespace(argparse.Namespace):  # pylint: disable=too-few-public-methods
    """Action positional argument namespace.

    Attributes:
        action: CLI action positional argument.
        base: The base image to build.
        callback_script_path: The callback script path to run after image build.
        cloud_name: The Openstack cloud to interact with. The CLI assumes clouds.yaml is written
            to the default path, i.e. current directory or ~/.config/openstack or /etc/openstack.
        image_name: The image name to upload as.
        keep_revisions: The maximum number of images to keep before deletion.
        runner_version: The GitHub runner version. See https://github.com/actions/runner/releases/.
    """

    action: Literal["init", "run", "latest-build-id"]
    base: Literal["22.04", "jammy", "24.04", "noble"]
    callback_script_path: Path | None
    cloud_name: str
    image_name: str
    keep_revisions: int
    runner_version: str


class Arch(str, Enum):
    """Supported system architectures.

    Attributes:
        ARM64: Represents an ARM64 system architecture.
        X64: Represents an X64/AMD64 system architecture.
    """

    ARM64 = "arm64"
    X64 = "x64"

    def to_openstack(self) -> str:
        """Convert the architecture to OpenStack compatible arch string.

        Returns:
            The architecture string.
        """  # noqa: DCO050 the ValueError is an unreachable code.
        match self:
            case Arch.ARM64:
                return "aarch64"
            case Arch.X64:
                return "x86_64"
        raise ValueError  # pragma: nocover


ARCHITECTURES_ARM64 = {"aarch64", "arm64"}
ARCHITECTURES_X86 = {"x86_64"}


def get_supported_arch() -> Arch:
    """Get current machine architecture.

    Raises:
        UnsupportedArchitectureError: if the current architecture is unsupported.

    Returns:
        Arch: Current machine architecture.
    """
    arch = platform.machine()
    match arch:
        case arch if arch in ARCHITECTURES_ARM64:
            return Arch.ARM64
        case arch if arch in ARCHITECTURES_X86:
            return Arch.X64
        case _:
            raise UnsupportedArchitectureError()


class BaseImage(str, Enum):
    """The ubuntu OS base image to build and deploy runners on.

    Attributes:
        JAMMY: The jammy ubuntu LTS image.
        NOBLE: The noble ubuntu LTS image.
    """

    JAMMY = "jammy"
    NOBLE = "noble"

    @classmethod
    def from_str(cls, tag_or_name: str) -> "BaseImage":
        """Retrieve the base image tag from input.

        Args:
            tag_or_name: The base image string option.

        Returns:
            The base image configuration of the app.
        """
        if tag_or_name in LTS_IMAGE_VERSION_TAG_MAP:
            return cls(LTS_IMAGE_VERSION_TAG_MAP[tag_or_name])
        return cls(tag_or_name)


LTS_IMAGE_VERSION_TAG_MAP = {"22.04": BaseImage.JAMMY.value, "24.04": BaseImage.NOBLE.value}

IMAGE_OUTPUT_PATH = Path("compressed.img")
