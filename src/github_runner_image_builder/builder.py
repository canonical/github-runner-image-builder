# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module for interacting with qemu image builder."""

import dataclasses
import logging
import os
import shutil

# Ignore B404:blacklist since all subprocesses are run with predefined executables.
import subprocess  # nosec
import sys
import urllib.error
import urllib.request
from contextlib import redirect_stdout
from pathlib import Path
from typing import Literal

from github_runner_image_builder.chroot import ChrootBaseError, ChrootContextManager
from github_runner_image_builder.config import Arch, BaseImage
from github_runner_image_builder.errors import (
    BuilderSetupError,
    BuildImageError,
    CleanBuildStateError,
    CloudImageDownloadError,
    DependencyInstallError,
    ExternalPackageInstallError,
    ImageBuilderBaseError,
    ImageCompressError,
    ImageMountError,
    ImageResizeError,
    NetworkBlockDeviceError,
    ResizePartitionError,
    SystemUserConfigurationError,
    UnattendedUpgradeDisableError,
    UnsupportedArchitectureError,
    YQBuildError,
)
from github_runner_image_builder.utils import retry

logger = logging.getLogger(__name__)

SupportedCloudImageArch = Literal["amd64", "arm64"]

APT_DEPENDENCIES = [
    "qemu-utils",  # used for qemu utilities tools to build and resize image
    "libguestfs-tools",  # used to modify VM images.
    "cloud-utils",  # used for growpart.
    "golang-go",  # used to build yq from source.
]
SNAP_GO = "go"

# Constants for mounting images
IMAGE_MOUNT_DIR = Path("/mnt/ubuntu-image/")
NETWORK_BLOCK_DEVICE_PATH = Path("/dev/nbd0")
NETWORK_BLOCK_DEVICE_PARTITION_PATH = Path("/dev/nbd0p1")

# Constants for downloading cloud-images
CLOUD_IMAGE_URL_TMPL = (
    "https://cloud-images.ubuntu.com/{BASE_IMAGE}/current/"
    "{BASE_IMAGE}-server-cloudimg-{BIN_ARCH}.img"
)
CLOUD_IMAGE_FILE_NAME_TMPL = "{BASE_IMAGE}-server-cloudimg-{BIN_ARCH}.img"

# Constants for building image
# This amount is the smallest increase that caters for the installations within this image.
RESIZE_AMOUNT = "+1.5G"
MOUNTED_RESOLV_CONF_PATH = IMAGE_MOUNT_DIR / "etc/resolv.conf"
HOST_RESOLV_CONF_PATH = Path("/etc/resolv.conf")

# Constants for chroot environment Python symmlinks
DEFAULT_PYTHON_PATH = Path("/usr/bin/python3")
SYM_LINK_PYTHON_PATH = Path("/usr/bin/python")

# Constants for disabling automatic apt updates
APT_TIMER = "apt-daily.timer"
APT_SVC = "apt-daily.service"
APT_UPGRADE_TIMER = "apt-daily-upgrade.timer"
APT_UPGRAD_SVC = "apt-daily-upgrade.service"

# Constants for managing users and groups
UBUNTU_USER = "ubuntu"
DOCKER_GROUP = "docker"
MICROK8S_GROUP = "microk8s"
LXD_GROUP = "lxd"
UBUNTU_HOME = Path("/home/ubuntu")

# Constants for packages in the image
YQ_REPOSITORY_URL = "https://github.com/mikefarah/yq.git"
YQ_REPOSITORY_PATH = Path("yq_source")
HOST_YQ_BIN_PATH = Path("/usr/bin/yq")
MOUNTED_YQ_BIN_PATH = IMAGE_MOUNT_DIR / "usr/bin/yq"
IMAGE_DEFAULT_APT_PACKAGES = [
    "docker.io",
    "npm",
    "python3-pip",
    "shellcheck",
    "jq",
    "wget",
    "unzip",
    "gh",
]


def _install_dependencies() -> None:
    """Install required dependencies to run qemu image build.

    Raises:
        DependencyInstallError: If there was an error installing apt packages.
    """
    try:
        subprocess.run(
            ["/usr/bin/apt-get", "update", "-y"], check=True, timeout=30 * 60
        )  # nosec: B603
        subprocess.run(
            ["/usr/bin/apt-get", "install", "-y", "--no-install-recommends", *APT_DEPENDENCIES],
            check=True,
            timeout=30 * 60,
        )  # nosec: B603
        subprocess.run(
            ["/usr/bin/snap", "install", SNAP_GO, "--classic"],
            check=True,
            timeout=30 * 60,
        )  # nosec: B603
    except subprocess.CalledProcessError as exc:
        raise DependencyInstallError from exc


def _enable_nbd() -> None:
    """Enable network block device module to mount and build chrooted image.

    Raises:
        NetworkBlockDeviceError: If there was an error enable nbd kernel.
    """
    try:
        subprocess.run(["/usr/sbin/modprobe", "nbd"], check=True, timeout=10)  # nosec: B603
    except subprocess.CalledProcessError as exc:
        raise NetworkBlockDeviceError from exc


def setup_builder() -> None:
    """Configure the host machine to build images.

    Raises:
        BuilderSetupError: If there was an error setting up the host device for building images.
    """
    try:
        _install_dependencies()
        _enable_nbd()
    except ImageBuilderBaseError as exc:
        raise BuilderSetupError from exc


def _get_supported_runner_arch(arch: Arch) -> SupportedCloudImageArch:
    """Validate and return supported runner architecture.

    The supported runner architecture takes in arch value from Github supported
    architecture and outputs architectures supported by ubuntu cloud images.
    See: https://docs.github.com/en/actions/hosting-your-own-runners/managing-\
        self-hosted-runners/about-self-hosted-runners#architectures
    and https://cloud-images.ubuntu.com/jammy/current/

    Args:
        arch: The compute architecture to check support for.

    Raises:
        UnsupportedArchitectureError: If an unsupported architecture was passed.

    Returns:
        The supported architecture.
    """
    match arch:
        case Arch.X64:
            return "amd64"
        case Arch.ARM64:
            return "arm64"
        case _:
            raise UnsupportedArchitectureError(arch)


def _clean_build_state() -> None:
    """Remove any artefacts left by previous build.

    Raises:
        CleanBuildStateError: if there was an error cleaning up the build state.
    """
    # The commands will fail if artefacts do not exist and hence there is no need to check the
    # output of subprocess runs.
    IMAGE_MOUNT_DIR.mkdir(parents=True, exist_ok=True)
    try:
        subprocess.run(
            ["/usr/bin/umount", str(IMAGE_MOUNT_DIR / "dev")], timeout=30, check=False
        )  # nosec: B603
        subprocess.run(
            ["/usr/bin/umount", str(IMAGE_MOUNT_DIR / "proc")], timeout=30, check=False
        )  # nosec: B603
        subprocess.run(
            ["/usr/bin/umount", str(IMAGE_MOUNT_DIR / "sys")], timeout=30, check=False
        )  # nosec: B603
        subprocess.run(
            ["/usr/bin/umount", str(IMAGE_MOUNT_DIR)], timeout=30, check=False
        )  # nosec: B603
        subprocess.run(
            ["/usr/bin/umount", str(NETWORK_BLOCK_DEVICE_PATH)], timeout=30, check=False
        )  # nosec: B603
        subprocess.run(  # nosec: B603
            ["/usr/bin/umount", str(NETWORK_BLOCK_DEVICE_PARTITION_PATH)], timeout=30, check=False
        )
        subprocess.run(  # nosec: B603
            ["/usr/bin/qemu-nbd", "--disconnect", str(NETWORK_BLOCK_DEVICE_PATH)],
            timeout=30,
            check=False,
        )
        subprocess.run(  # nosec: B603
            ["/usr/bin/qemu-nbd", "--disconnect", str(NETWORK_BLOCK_DEVICE_PARTITION_PATH)],
            timeout=30,
            check=False,
        )
    except subprocess.SubprocessError as exc:
        raise CleanBuildStateError from exc


def _download_cloud_image(arch: Arch, base_image: BaseImage) -> Path:
    """Download the cloud image from cloud-images.ubuntu.com.

    Args:
        arch: The cloud image architecture to download.
        base_image: The ubuntu base image OS to download.

    Returns:
        The downloaded cloud image path.

    Raises:
        CloudImageDownloadError: If there was an error downloading the image.
    """
    try:
        bin_arch = _get_supported_runner_arch(arch)
    except UnsupportedArchitectureError as exc:
        raise CloudImageDownloadError from exc

    try:
        # The ubuntu-cloud-images is a trusted source
        image_path, _ = urllib.request.urlretrieve(  # nosec: B310
            CLOUD_IMAGE_URL_TMPL.format(BASE_IMAGE=base_image.value, BIN_ARCH=bin_arch),
            CLOUD_IMAGE_FILE_NAME_TMPL.format(BASE_IMAGE=base_image.value, BIN_ARCH=bin_arch),
        )
        return Path(image_path)
    except urllib.error.URLError as exc:
        raise CloudImageDownloadError from exc


def _resize_cloud_img(cloud_image_path: Path) -> None:
    """Resize cloud image to allow space for dependency installations.

    Args:
        cloud_image_path: The target cloud image file to resize.

    Raises:
        ImageResizeError: If there was an error resizing the image.
    """
    try:
        subprocess.run(  # nosec: B603
            ["/usr/bin/qemu-img", "resize", str(cloud_image_path), RESIZE_AMOUNT],
            check=True,
            timeout=60,
        )
    except subprocess.CalledProcessError as exc:
        raise ImageResizeError from exc


@retry(tries=5, delay=5, max_delay=60, backoff=2, local_logger=logger)
def _mount_nbd_partition() -> None:
    """Mount the network block device partition."""
    subprocess.run(  # nosec: B603
        [
            "/usr/bin/mount",
            "-o",
            "rw",
            str(NETWORK_BLOCK_DEVICE_PARTITION_PATH),
            str(IMAGE_MOUNT_DIR),
        ],
        check=True,
        timeout=60,
    )


def _mount_image_to_network_block_device(cloud_image_path: Path) -> None:
    """Mount the image to network block device in preparation for chroot.

    Args:
        cloud_image_path: The target cloud image file to mount.

    Raises:
        ImageMountError: If there was an error mounting the image to network block device.
    """
    try:
        subprocess.run(  # nosec: B603
            ["/usr/bin/qemu-nbd", f"--connect={NETWORK_BLOCK_DEVICE_PATH}", str(cloud_image_path)],
            check=True,
            timeout=60,
        )
        _mount_nbd_partition()
    except subprocess.CalledProcessError as exc:
        raise ImageMountError from exc


def _replace_mounted_resolv_conf() -> None:
    """Replace resolv.conf to host resolv.conf to allow networking."""
    MOUNTED_RESOLV_CONF_PATH.unlink(missing_ok=True)
    shutil.copy(str(HOST_RESOLV_CONF_PATH), str(MOUNTED_RESOLV_CONF_PATH))


def _resize_mount_partitions() -> None:
    """Resize the block partition to fill available space.

    Raises:
        ResizePartitionError: If there was an error resizing network block device partitions.
    """
    try:
        subprocess.run(  # nosec: B603
            ["/usr/bin/growpart", str(NETWORK_BLOCK_DEVICE_PATH), "1"], check=True, timeout=10 * 60
        )
        subprocess.run(  # nosec: B603
            ["/usr/sbin/resize2fs", str(NETWORK_BLOCK_DEVICE_PARTITION_PATH)],
            check=True,
            timeout=10 * 60,
        )
    except subprocess.CalledProcessError as exc:
        raise ResizePartitionError from exc


def _install_yq() -> None:
    """Build and install yq from source.

    Raises:
        YQBuildError: If there was an error building yq from source.
    """
    try:
        subprocess.run(  # nosec: B603
            ["/usr/bin/git", "clone", str(YQ_REPOSITORY_URL), str(YQ_REPOSITORY_PATH)],
            check=True,
            timeout=60 * 10,
        )
        subprocess.run(  # nosec: B603
            ["/snap/bin/go", "build", "-C", str(YQ_REPOSITORY_PATH), "-o", str(HOST_YQ_BIN_PATH)],
            check=True,
            timeout=20 * 60,
        )
        shutil.copy(HOST_YQ_BIN_PATH, MOUNTED_YQ_BIN_PATH)
    except subprocess.CalledProcessError as exc:
        raise YQBuildError from exc


def _create_python_symlinks() -> None:
    """Create python3 symlinks."""
    os.symlink(DEFAULT_PYTHON_PATH, SYM_LINK_PYTHON_PATH)


def _disable_unattended_upgrades() -> None:
    """Disable unatteneded upgrades to prevent apt locks.

    Raises:
        UnattendedUpgradeDisableError: If there was an error disabling unattended upgrade related
            services.
    """
    try:
        # use subprocess run rather than operator-libs-linux's systemd library since the library
        # does not provide full features like mask.
        subprocess.run(
            ["/usr/bin/systemctl", "stop", APT_TIMER], check=True, timeout=30
        )  # nosec: B603
        subprocess.run(
            ["/usr/bin/systemctl", "disable", APT_TIMER], check=True, timeout=30
        )  # nosec: B603
        subprocess.run(
            ["/usr/bin/systemctl", "mask", APT_SVC], check=True, timeout=30
        )  # nosec: B603
        subprocess.run(
            ["/usr/bin/systemctl", "stop", APT_UPGRADE_TIMER], check=True, timeout=30
        )  # nosec: B603
        subprocess.run(  # nosec: B603
            ["/usr/bin/systemctl", "disable", APT_UPGRADE_TIMER], check=True, timeout=30
        )
        subprocess.run(
            ["/usr/bin/systemctl", "mask", APT_UPGRAD_SVC], check=True, timeout=30
        )  # nosec: B603
        subprocess.run(
            ["/usr/bin/systemctl", "daemon-reload"], check=True, timeout=30
        )  # nosec: B603
        subprocess.run(  # nosec: B603
            ["/usr/bin/apt-get", "remove", "-y", "unattended-upgrades"], check=True, timeout=30
        )
    except subprocess.SubprocessError as exc:
        raise UnattendedUpgradeDisableError from exc


def _configure_system_users() -> None:
    """Configure system users.

    Raises:
        SystemUserConfigurationError: If there was an error configuring ubuntu user.
    """
    try:
        subprocess.run(  # nosec: B603
            ["/usr/sbin/useradd", "-m", UBUNTU_USER], check=True, timeout=30
        )
        with (UBUNTU_HOME / ".profile").open("a") as profile_file:
            profile_file.write(f"PATH=$PATH:{UBUNTU_HOME}/.local/bin\n")
        with (UBUNTU_HOME / ".bashrc").open("a") as bashrc_file:
            bashrc_file.write(f"PATH=$PATH:{UBUNTU_HOME}/.local/bin\n")
        subprocess.run(  # nosec: B603
            ["/usr/sbin/groupadd", MICROK8S_GROUP], check=True, timeout=30
        )
        subprocess.run(  # nosec: B603
            ["/usr/sbin/usermod", "-aG", DOCKER_GROUP, UBUNTU_USER], check=True, timeout=30
        )
        subprocess.run(  # nosec: B603
            ["/usr/sbin/usermod", "-aG", MICROK8S_GROUP, UBUNTU_USER], check=True, timeout=30
        )
        subprocess.run(  # nosec: B603
            ["/usr/sbin/usermod", "-aG", LXD_GROUP, UBUNTU_USER], check=True, timeout=30
        )
        subprocess.run(  # nosec: B603
            ["/usr/bin/chmod", "777", "/usr/local/bin"], check=True, timeout=30
        )
    except subprocess.SubprocessError as exc:
        raise SystemUserConfigurationError from exc


def _install_external_packages() -> None:
    """Install packages outside of apt.

    Installs yarn.

    Raises:
        ExternalPackageInstallError: If there was an error installing external package.
    """
    try:
        # 2024/04/26 There's a potential security risk here, npm is subject to toolchain attacks.
        subprocess.run(
            ["/usr/bin/npm", "install", "--global", "yarn"], check=True, timeout=60 * 5
        )  # nosec: B603
        subprocess.run(
            ["/usr/bin/npm", "cache", "clean", "--force"], check=True, timeout=60
        )  # nosec: B603
    except subprocess.SubprocessError as exc:
        raise ExternalPackageInstallError from exc


@retry(tries=5, delay=5, max_delay=60, backoff=2, local_logger=logger)
def _compress_image(image: Path, output: Path) -> None:
    """Compress the cloud image.

    Args:
        image: The image to compress.
        output: The desired image output path.

    Raises:
        ImageCompressError: If there was something wrong compressing the image.
    """
    try:
        subprocess.run(  # nosec: B603
            ["/usr/bin/virt-sparsify", "--compress", str(image), str(output)],
            check=True,
            timeout=60 * 10,
        )
    except subprocess.CalledProcessError as exc:
        raise ImageCompressError from exc


@dataclasses.dataclass
class BuildImageConfig:
    """Configuration for building the image.

    Attributes:
        arch: The CPU architecture to build the image for.
        base_image: The ubuntu image to use as build base.
        output: The path to write final image to.
    """

    arch: Arch
    base_image: BaseImage
    output: Path


def build_image(config: BuildImageConfig) -> None:
    """Build and save the image locally.

    Args:
        config: The configuration values to build the image with.

    Raises:
        BuildImageError: If there was an error building the image.
    """
    logger.info("Clean build state.")
    with redirect_stdout(sys.stderr):
        try:
            _clean_build_state()
            logger.info("Downloading cloud image.")
            cloud_image_path = _download_cloud_image(
                arch=config.arch, base_image=config.base_image
            )
            logger.info("Resizing cloud image.")
            _resize_cloud_img(cloud_image_path=cloud_image_path)
            logger.info("Mounting network block device.")
            _mount_image_to_network_block_device(cloud_image_path=cloud_image_path)
            logger.info("Replacing resolv.conf.")
            _replace_mounted_resolv_conf()
            logger.info("Resizing partitions.")
            _resize_mount_partitions()
            logger.info("Building YQ from source.")
            _install_yq()
        except ImageBuilderBaseError as exc:
            raise BuildImageError from exc

        try:
            logger.info("Setting up chroot environment.")
            with ChrootContextManager(IMAGE_MOUNT_DIR):
                # operator_libs_linux apt package uses dpkg -l and that does not work well with
                # chroot env, hence use subprocess run.
                subprocess.run(
                    ["/usr/bin/apt-get", "update", "-y"],
                    check=True,
                    timeout=60 * 10,
                    env={"DEBIAN_FRONTEND": "noninteractive"},
                )  # nosec: B603
                subprocess.run(  # nosec: B603
                    [
                        "/usr/bin/apt-get",
                        "install",
                        "-y",
                        "--no-install-recommends",
                        *IMAGE_DEFAULT_APT_PACKAGES,
                    ],
                    check=True,
                    timeout=60 * 20,
                    env={"DEBIAN_FRONTEND": "noninteractive"},
                )
                _create_python_symlinks()
                _disable_unattended_upgrades()
                _configure_system_users()
                _install_external_packages()
        except (ImageBuilderBaseError, ChrootBaseError) as exc:
            raise BuildImageError from exc

        try:
            _clean_build_state()
            logger.info("Compressing image")
            _compress_image(cloud_image_path, config.output)
        except ImageBuilderBaseError as exc:
            raise BuildImageError from exc
