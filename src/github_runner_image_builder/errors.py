# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module containing error definitions."""


class ImageBuilderBaseError(Exception):
    """Represents an error with any builder related executions."""


# nosec: B603: All subprocess runs are run with trusted executables.
class DependencyInstallError(ImageBuilderBaseError):
    """Represents an error while installing required dependencies."""


class NetworkBlockDeviceError(ImageBuilderBaseError):
    """Represents an error while enabling network block device."""


class BuilderSetupError(ImageBuilderBaseError):
    """Represents an error while setting up host machine as builder."""


class UnsupportedArchitectureError(ImageBuilderBaseError):
    """Raised when given machine architecture is unsupported."""


class CleanBuildStateError(ImageBuilderBaseError):
    """Represents an error cleaning up build state."""


class CloudImageDownloadError(ImageBuilderBaseError):
    """Represents an error downloading cloud image."""


class ImageResizeError(ImageBuilderBaseError):
    """Represents an error while resizing the image."""


class ImageMountError(ImageBuilderBaseError):
    """Represents an error while mounting the image to network block device."""


class ResizePartitionError(ImageBuilderBaseError):
    """Represents an error while resizing network block device partitions."""


class UnattendedUpgradeDisableError(ImageBuilderBaseError):
    """Represents an error while disabling unattended-upgrade related services."""


class SystemUserConfigurationError(ImageBuilderBaseError):
    """Represents an error while adding user to chroot env."""


class YQBuildError(ImageBuilderBaseError):
    """Represents an error while building yq binary from source."""


class ExternalPackageInstallError(ImageBuilderBaseError):
    """Represents an error installilng external packages."""


class ImageCompressError(ImageBuilderBaseError):
    """Represents an error while compressing cloud-img."""


class BuildImageError(ImageBuilderBaseError):
    """Represents an error while building the image."""


class OpenstackBaseError(Exception):
    """Represents an error while interacting with Openstack."""


class UnauthorizedError(OpenstackBaseError):
    """Represents an unauthorized connection to Openstack."""


class UploadImageError(OpenstackBaseError):
    """Represents an error when uploading image to Openstack."""


class GetImageError(OpenstackBaseError):
    """Represents an error when fetching images from Openstack."""


class OpenstackConnectionError(OpenstackBaseError):
    """Represents an error while communicating with Openstack."""