# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module containing configurations."""

import logging
import platform
from enum import Enum

logger = logging.getLogger(__name__)


class Arch(str, Enum):
    """Supported system architectures.

    Attributes:
        ARM64: Represents an ARM64 system architecture.
        X64: Represents an X64/AMD64 system architecture.
    """

    ARM64 = "arm64"
    X64 = "x64"


class UnsupportedArchitectureError(Exception):
    """Raised when given machine architecture is unsupported.

    Attributes:
        arch: The current machine architecture.
    """

    def __str__(self) -> str:
        """Represent the error in string format.

        Returns:
            The error in string format.
        """
        return f"UnsupportedArchitectureError: {self.arch}"

    def __init__(self, arch: str) -> None:
        """Initialize a new instance of the UnsupportedArchitectureError exception.

        Args:
            arch: The current machine architecture.
        """
        self.arch = arch


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
            raise UnsupportedArchitectureError(arch=arch)


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
