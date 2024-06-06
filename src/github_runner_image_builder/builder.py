# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module for interacting with qemu image builder."""

import hashlib
import logging
import shutil

# Ignore B404:blacklist since all subprocesses are run with predefined executables.
import subprocess  # nosec
import urllib.error
import urllib.request
from pathlib import Path
from typing import Literal

import requests

from github_runner_image_builder.chroot import ChrootBaseError, ChrootContextManager
from github_runner_image_builder.config import IMAGE_OUTPUT_PATH, Arch, BaseImage
from github_runner_image_builder.errors import (
    BaseImageDownloadError,
    BuildImageError,
    DependencyInstallError,
    ImageCompressError,
    ImageConnectError,
    ImageResizeError,
    NetworkBlockDeviceError,
    PermissionConfigurationError,
    ResizePartitionError,
    SystemUserConfigurationError,
    UnattendedUpgradeDisableError,
    UnmountBuildPathError,
    UnsupportedArchitectureError,
    YarnInstallError,
    YQBuildError,
)
from github_runner_image_builder.utils import retry

logger = logging.getLogger(__name__)

SupportedBaseImageArch = Literal["amd64", "arm64"]

APT_DEPENDENCIES = [
    "qemu-utils",  # used for qemu utilities tools to build and resize image
    "libguestfs-tools",  # used to modify VM images.
    "cloud-utils",  # used for growpart.
    "golang-go",  # used to build yq from source.
]
APT_NONINTERACTIVE_ENV = {"DEBIAN_FRONTEND": "noninteractive"}
SNAP_GO = "go"

CHECKSUM_BUF_SIZE = 65536  # 65kb

# Constants for mounting images
IMAGE_MOUNT_DIR = Path("/mnt/ubuntu-image/")
NETWORK_BLOCK_DEVICE_PATH = Path("/dev/nbd0")
NETWORK_BLOCK_DEVICE_PARTITION_PATH = Path(f"{NETWORK_BLOCK_DEVICE_PATH}p1")

# Constants for building image
# This amount is the smallest increase that caters for the installations within this image.
RESIZE_AMOUNT = "+1.5G"
MOUNTED_RESOLV_CONF_PATH = IMAGE_MOUNT_DIR / "etc/resolv.conf"
HOST_RESOLV_CONF_PATH = Path("/etc/resolv.conf")

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
    "gh",
    "jq",
    "npm",
    "python3-pip",
    "python-is-python3",
    "shellcheck",
    "unzip",
    "wget",
]


def initialize() -> None:
    """Configure the host machine to build images."""
    logger.info("Installing dependencies.")
    _install_dependencies()
    logger.info("Enabling network block device.")
    _enable_network_block_device()


def _install_dependencies() -> None:
    """Install required dependencies to run qemu image build.

    Raises:
        DependencyInstallError: If there was an error installing apt packages.
    """
    try:
        output = subprocess.check_output(
            ["/usr/bin/apt-get", "update", "-y"],
            encoding="utf-8",
            env=APT_NONINTERACTIVE_ENV,
            timeout=30 * 60,
        )  # nosec: B603
        logger.info("apt-get update out: %s", output)
        output = subprocess.check_output(
            ["/usr/bin/apt-get", "install", "-y", "--no-install-recommends", *APT_DEPENDENCIES],
            encoding="utf-8",
            env=APT_NONINTERACTIVE_ENV,
            timeout=30 * 60,
        )  # nosec: B603
        logger.info("apt-get install out: %s", output)
        output = subprocess.check_output(
            ["/usr/bin/snap", "install", SNAP_GO, "--classic"],
            encoding="utf-8",
            timeout=30 * 60,
        )  # nosec: B603
        logger.info("snap install go out: %s", output)
    except subprocess.CalledProcessError as exc:
        logger.exception(
            "Error installing dependencies, cmd: %s, code: %s, err: %s",
            exc.cmd,
            exc.returncode,
            exc.output,
        )
        raise DependencyInstallError from exc


def _enable_network_block_device() -> None:
    """Enable network block device module to mount and build chrooted image.

    Raises:
        NetworkBlockDeviceError: If there was an error enable nbd kernel.
    """
    try:
        output = subprocess.check_output(["/usr/sbin/modprobe", "nbd"], timeout=10)  # nosec: B603
        logger.info("modprobe nbd out: %s", output)
    except subprocess.CalledProcessError as exc:
        logger.exception(
            "Error enabling network block device, cmd: %s, code: %s, err: %s",
            exc.cmd,
            exc.returncode,
            exc.output,
        )
        raise NetworkBlockDeviceError from exc


def build_image(arch: Arch, base_image: BaseImage) -> None:
    """Build and save the image locally.

    Args:
        arch: The CPU architecture to build the image for.
        base_image: The ubuntu image to use as build base.

    Raises:
        BuildImageError: If there was an error building the image.
    """
    # ensure clean state - if there were errors within the chroot environment (e.g. network error)
    # this guarantees retry-ability
    _unmount_build_path()
    _disconnect_image_to_network_block_device(check=False)

    IMAGE_MOUNT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info("Downloading base image.")
    base_image_path = _download_and_validate_image(arch=arch, base_image=base_image)
    logger.info("Resizing base image.")
    _resize_image(image_path=base_image_path)
    logger.info("Connecting image to network block device.")
    _connect_image_to_network_block_device(image_path=base_image_path)
    logger.info("Resizing partitions.")
    _resize_mount_partitions()
    logger.info("Installing YQ from source.")
    _install_yq()

    logger.info("Setting up chroot environment.")
    logger.info("Replacing resolv.conf.")
    _replace_mounted_resolv_conf()
    try:
        with ChrootContextManager(IMAGE_MOUNT_DIR):
            # operator_libs_linux apt package uses dpkg -l and that does not work well with
            # chroot env, hence use subprocess run.
            output = subprocess.check_output(
                ["/usr/bin/apt-get", "update", "-y"],
                timeout=60 * 10,
                env=APT_NONINTERACTIVE_ENV,
            )  # nosec: B603
            logger.info("apt-get update out: %s", output)
            output = subprocess.check_output(  # nosec: B603
                [
                    "/usr/bin/apt-get",
                    "install",
                    "-y",
                    "--no-install-recommends",
                    *IMAGE_DEFAULT_APT_PACKAGES,
                ],
                timeout=60 * 20,
                env=APT_NONINTERACTIVE_ENV,
            )
            logger.info("apt-get install out: %s", output)
            _disable_unattended_upgrades()
            _configure_system_users()
            _configure_usr_local_bin()
            _install_yarn()
    except ChrootBaseError as exc:
        raise BuildImageError from exc

    logger.info("Disconnecting image to network block device.")
    _disconnect_image_to_network_block_device(check=True)

    logger.info("Compressing image.")
    _compress_image(base_image_path)


def _disconnect_image_to_network_block_device(check: bool = True) -> None:
    """Disconnect the image to network block device in cleanup for chroot.

    Args:
        check: Whether to raise an error on command failure.

    Raises:
        ImageConnectError: If there was an error disconnecting the image from network block device.
    """
    try:
        result = subprocess.run(  # nosec: B603
            ["/usr/bin/qemu-nbd", "--disconnect", str(NETWORK_BLOCK_DEVICE_PATH)],
            check=check,
            encoding="utf-8",
            timeout=30,
        )
        logger.info(
            "qemu-nbd disconnect nbd code: %s out: %s err: %s",
            result.returncode,
            result.stdout,
            result.stderr,
        )
        result = subprocess.run(  # nosec: B603
            ["/usr/bin/qemu-nbd", "--disconnect", str(NETWORK_BLOCK_DEVICE_PARTITION_PATH)],
            check=check,
            encoding="utf-8",
            timeout=30,
        )
        logger.info(
            "qemu-nbd disconnect nbdp1 code: %s out: %s err: %s",
            result.returncode,
            result.stdout,
            result.stderr,
        )
    except subprocess.CalledProcessError as exc:
        logger.exception(
            "Error disconnecting image to network block device, cmd: %s, code: %s, err: %s",
            exc.cmd,
            exc.returncode,
            exc.output,
        )
        raise ImageConnectError from exc
    except subprocess.SubprocessError as exc:
        raise ImageConnectError from exc


def _unmount_build_path() -> None:
    """Unmount any mounted paths left by previous build.

    Raises:
        UnmountBuildPathError: if there was an error unmounting previous build state.
    """
    # The commands will fail if artefacts do not exist and hence there is no need to check the
    # output of subprocess runs.
    try:
        output = subprocess.run(
            ["/usr/bin/umount", str(IMAGE_MOUNT_DIR / "dev")],
            timeout=30,
            check=False,
        )  # nosec: B603
        logger.info("umount dev out: %s", output)
        output = subprocess.run(
            ["/usr/bin/umount", str(IMAGE_MOUNT_DIR / "proc")],
            timeout=30,
            check=False,
            capture_output=True,
        )  # nosec: B603
        logger.info("umount proc out: %s", output)
        output = subprocess.run(
            ["/usr/bin/umount", str(IMAGE_MOUNT_DIR / "sys")],
            timeout=30,
            check=False,
            capture_output=True,
        )  # nosec: B603
        logger.info("umount sys out: %s", output)
        output = subprocess.run(
            ["/usr/bin/umount", str(IMAGE_MOUNT_DIR)], timeout=30, check=False, capture_output=True
        )  # nosec: B603
        logger.info("umount ubuntu-image out: %s", output)
        output = subprocess.run(
            ["/usr/bin/umount", str(NETWORK_BLOCK_DEVICE_PATH)],
            timeout=30,
            check=False,
            capture_output=True,
        )  # nosec: B603
        logger.info("umount nbd out: %s", output)
        output = subprocess.run(  # nosec: B603
            ["/usr/bin/umount", str(NETWORK_BLOCK_DEVICE_PARTITION_PATH)],
            timeout=30,
            check=False,
            capture_output=True,
        )
        logger.info("umount nbdp1 out: %s", output)
    except subprocess.SubprocessError as exc:
        raise UnmountBuildPathError from exc


def _download_and_validate_image(arch: Arch, base_image: BaseImage) -> Path:
    """Download and verify the base image from cloud-images.ubuntu.com.

    Args:
        arch: The base image architecture to download.
        base_image: The ubuntu base image OS to download.

    Returns:
        The downloaded image path.

    Raises:
        BaseImageDownloadError: If there was an error with downloading/verifying the image.
    """
    try:
        bin_arch = _get_supported_runner_arch(arch)
    except UnsupportedArchitectureError as exc:
        raise BaseImageDownloadError from exc

    image_path_str = f"{base_image.value}-server-cloudimg-{bin_arch}.img"
    image_path = _download_base_image(
        base_image=base_image, bin_arch=bin_arch, output_filename=image_path_str
    )
    shasums = _fetch_shasums(base_image=base_image)
    if image_path_str not in shasums:
        raise BaseImageDownloadError("Corresponding checksum not found.")
    if not _validate_checksum(image_path, shasums[image_path_str]):
        raise BaseImageDownloadError("Invalid checksum.")
    return image_path


def _get_supported_runner_arch(arch: Arch) -> SupportedBaseImageArch:
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
            raise UnsupportedArchitectureError(f"Detected system arch: {arch} is unsupported.")


@retry(tries=3, delay=5, max_delay=30, backoff=2, local_logger=logger)
def _download_base_image(base_image: BaseImage, bin_arch: str, output_filename: str) -> Path:
    """Download the base image.

    Args:
        bin_arch: The ubuntu cloud-image supported arch.
        base_image: The ubuntu base image OS to download.
        output_filename: The output filename of the downloaded image.

    Raises:
        BaseImageDownloadError: If there was an error downloaded from cloud-images.ubuntu.com

    Returns:
        The downloaded image path.
    """
    # The ubuntu-cloud-images is a trusted source
    try:
        urllib.request.urlretrieve(  # nosec: B310
            (
                f"https://cloud-images.ubuntu.com/{base_image.value}/current/{base_image.value}"
                f"-server-cloudimg-{bin_arch}.img"
            ),
            output_filename,
        )
    except urllib.error.URLError as exc:
        raise BaseImageDownloadError from exc
    return Path(output_filename)


@retry(tries=3, delay=5, max_delay=30, backoff=2, local_logger=logger)
def _fetch_shasums(base_image: BaseImage) -> dict[str, str]:
    """Fetch SHA256SUM for given base image.

    Args:
        base_image: The ubuntu base image OS to fetch SHA256SUMs for.

    Raises:
        BaseImageDownloadError: If there was an error downloading SHA256SUMS file from \
            cloud-images.ubuntu.com

    Returns:
        A map of image file name to SHA256SUM.
    """
    try:
        # bandit does not detect that the timeout parameter exists.
        response = requests.get(  # nosec: request_without_timeout
            f"https://cloud-images.ubuntu.com/{base_image.value}/current/SHA256SUMS",
            timeout=60 * 5,
        )
    except requests.RequestException as exc:
        raise BaseImageDownloadError from exc
    # file consisting of lines <SHA256SUM> *<filename>
    shasum_contents = str(response.content, encoding="utf-8")
    imagefile_to_shasum = {
        sha256_and_file[1].strip("*"): sha256_and_file[0]
        for shasum_line in shasum_contents.strip().splitlines()
        if (sha256_and_file := shasum_line.split())
    }
    return imagefile_to_shasum


def _validate_checksum(file: Path, expected_checksum: str) -> bool:
    """Validate the checksum of a given file.

    Args:
        file: The file to calculate checksum for.
        expected_checksum: The expected file checksum.

    Returns:
        True if the checksums match. False otherwise.
    """
    sha256 = hashlib.sha256()
    with open(file=file, mode="rb") as target_file:
        while True:
            data = target_file.read(CHECKSUM_BUF_SIZE)
            if not data:
                break
            sha256.update(data)
    return sha256.hexdigest() == expected_checksum


def _resize_image(image_path: Path) -> None:
    """Resize image to allow space for dependency installations.

    Args:
        image_path: The target image file to resize.

    Raises:
        ImageResizeError: If there was an error resizing the image.
    """
    try:
        output = subprocess.check_output(  # nosec: B603
            ["/usr/bin/qemu-img", "resize", str(image_path), RESIZE_AMOUNT],
            timeout=60,
        )
        logger.info("qemu-img resize out: %s", output)
    except subprocess.CalledProcessError as exc:
        logger.exception(
            "Error resizing image, cmd: %s, code: %s, err: %s",
            exc.cmd,
            exc.returncode,
            exc.output,
        )
        raise ImageResizeError from exc
    except subprocess.SubprocessError as exc:
        raise ImageResizeError from exc


def _connect_image_to_network_block_device(image_path: Path) -> None:
    """Connect the image to network block device in preparation for chroot.

    Args:
        image_path: The target image file to connect.

    Raises:
        ImageConnectError: If there was an error connecting the image to network block device.
    """
    try:
        output = subprocess.check_output(  # nosec: B603
            ["/usr/bin/qemu-nbd", f"--connect={NETWORK_BLOCK_DEVICE_PATH}", str(image_path)],
            timeout=60,
        )
        logger.info("qemu-nbd connect out: %s", output)
        _mount_network_block_device_partition()
    except subprocess.CalledProcessError as exc:
        logger.exception(
            "Error connecting image to network block device, cmd: %s, code: %s, err: %s",
            exc.cmd,
            exc.returncode,
            exc.output,
        )
        raise ImageConnectError from exc
    except subprocess.SubprocessError as exc:
        raise ImageConnectError from exc


# Network block device may fail to mount, retrying will usually fix this.
@retry(tries=5, delay=5, max_delay=60, backoff=2, local_logger=logger)
def _mount_network_block_device_partition() -> None:
    """Mount the network block device partition."""
    output = subprocess.check_output(  # nosec: B603
        [
            "/usr/bin/mount",
            "-o",
            "rw",
            str(NETWORK_BLOCK_DEVICE_PARTITION_PATH),
            str(IMAGE_MOUNT_DIR),
        ],
        timeout=60,
    )
    logger.info("mount nbd0p1 out: %s", output)


def _resize_mount_partitions() -> None:
    """Resize the block partition to fill available space.

    Raises:
        ResizePartitionError: If there was an error resizing network block device partitions.
    """
    try:
        output = subprocess.check_output(  # nosec: B603
            ["/usr/bin/growpart", str(NETWORK_BLOCK_DEVICE_PATH), "1"], timeout=10 * 60
        )
        logger.info("growpart out: %s", output)
        output = subprocess.check_output(  # nosec: B603
            ["/usr/sbin/resize2fs", str(NETWORK_BLOCK_DEVICE_PARTITION_PATH)],
            timeout=10 * 60,
        )
        logger.info("resize2fs out: %s", output)
    except subprocess.CalledProcessError as exc:
        logger.exception(
            "Error resizing mount partitions, cmd: %s, code: %s, err: %s",
            exc.cmd,
            exc.returncode,
            exc.output,
        )
        raise ResizePartitionError from exc
    except subprocess.SubprocessError as exc:
        raise ResizePartitionError from exc


@retry(tries=3, delay=5, max_delay=30, backoff=2, local_logger=logger)
def _install_yq() -> None:
    """Build and install yq from source.

    Raises:
        YQBuildError: If there was an error building yq from source.
    """
    try:
        if not YQ_REPOSITORY_PATH.exists():
            output = subprocess.check_output(  # nosec: B603
                ["/usr/bin/git", "clone", str(YQ_REPOSITORY_URL), str(YQ_REPOSITORY_PATH)],
                timeout=60 * 10,
            )
            logger.info("git clone out: %s", output)
        else:
            output = subprocess.check_output(  # nosec: B603
                ["/usr/bin/git", "-C", str(YQ_REPOSITORY_PATH), "pull"],
                timeout=60 * 10,
            )
            logger.info("git pull out: %s", output)
        output = subprocess.check_output(  # nosec: B603
            ["/snap/bin/go", "build", "-C", str(YQ_REPOSITORY_PATH), "-o", str(HOST_YQ_BIN_PATH)],
            timeout=20 * 60,
        )
        logger.info("go build out: %s", output)
        shutil.copy(HOST_YQ_BIN_PATH, MOUNTED_YQ_BIN_PATH)
    except subprocess.CalledProcessError as exc:
        logger.exception(
            "Error installing yq, cmd: %s, code: %s, err: %s",
            exc.cmd,
            exc.returncode,
            exc.output,
        )
        raise YQBuildError from exc
    except subprocess.SubprocessError as exc:
        raise YQBuildError from exc


def _replace_mounted_resolv_conf() -> None:
    """Replace resolv.conf to host resolv.conf to allow networking."""
    MOUNTED_RESOLV_CONF_PATH.unlink(missing_ok=True)
    shutil.copy(str(HOST_RESOLV_CONF_PATH), str(MOUNTED_RESOLV_CONF_PATH))


def _disable_unattended_upgrades() -> None:
    """Disable unatteneded upgrades to prevent apt locks.

    Raises:
        UnattendedUpgradeDisableError: If there was an error disabling unattended upgrade related
            services.
    """
    try:
        # use subprocess run rather than operator-libs-linux's systemd library since the library
        # does not provide full features like mask.
        output = subprocess.check_output(
            ["/usr/bin/systemctl", "stop", APT_TIMER], timeout=30
        )  # nosec: B603
        logger.info("systemctl stop apt timer out: %s", output)
        output = subprocess.check_output(
            ["/usr/bin/systemctl", "disable", APT_TIMER], timeout=30
        )  # nosec: B603
        logger.info("systemctl disable apt timer out: %s", output)
        output = subprocess.check_output(
            ["/usr/bin/systemctl", "mask", APT_SVC], timeout=30
        )  # nosec: B603
        logger.info("systemctl mask apt timer out: %s", output)
        output = subprocess.check_output(
            ["/usr/bin/systemctl", "stop", APT_UPGRADE_TIMER], timeout=30
        )  # nosec: B603
        logger.info("systemctl stop apt upgrade timer out: %s", output)
        output = subprocess.check_output(  # nosec: B603
            ["/usr/bin/systemctl", "disable", APT_UPGRADE_TIMER], timeout=30
        )
        logger.info("systemctl disable apt upgrade timer out: %s", output)
        output = subprocess.check_output(
            ["/usr/bin/systemctl", "mask", APT_UPGRAD_SVC], timeout=30
        )  # nosec: B603
        logger.info("systemctl mask apt upgrade timer out: %s", output)
        output = subprocess.check_output(
            ["/usr/bin/systemctl", "daemon-reload"], timeout=30
        )  # nosec: B603
        logger.info("systemctl daemon-reload out: %s", output)
        output = subprocess.check_output(  # nosec: B603
            ["/usr/bin/apt-get", "remove", "-y", "unattended-upgrades"],
            env=APT_NONINTERACTIVE_ENV,
            timeout=30,
        )
        logger.info("apt-get remove unattended-upgrades out: %s", output)
    except subprocess.CalledProcessError as exc:
        logger.exception(
            "Error disabling unattended upgrades, cmd: %s, code: %s, err: %s",
            exc.cmd,
            exc.returncode,
            exc.output,
        )
        raise UnattendedUpgradeDisableError from exc
    except subprocess.SubprocessError as exc:
        raise UnattendedUpgradeDisableError from exc


def _configure_system_users() -> None:
    """Configure system users.

    Raises:
        SystemUserConfigurationError: If there was an error configuring ubuntu user.
    """
    try:
        output = subprocess.check_output(  # nosec: B603
            ["/usr/sbin/useradd", "-m", UBUNTU_USER], timeout=30
        )
        logger.info("useradd ubunutu out: %s", output)
        with (UBUNTU_HOME / ".profile").open("a") as profile_file:
            profile_file.write(f"PATH=$PATH:{UBUNTU_HOME}/.local/bin\n")
        with (UBUNTU_HOME / ".bashrc").open("a") as bashrc_file:
            bashrc_file.write(f"PATH=$PATH:{UBUNTU_HOME}/.local/bin\n")
        output = subprocess.check_output(
            ["/usr/sbin/groupadd", MICROK8S_GROUP], timeout=30
        )  # nosec: B603
        logger.info("groupadd microk8s out: %s", output)
        output = subprocess.check_output(  # nosec: B603
            [
                "/usr/sbin/usermod",
                "-aG",
                f"{DOCKER_GROUP},{MICROK8S_GROUP},{LXD_GROUP}",
                UBUNTU_USER,
            ],
            timeout=30,
        )
        logger.info("usrmod to ubuntu user out: %s", output)
    except subprocess.CalledProcessError as exc:
        logger.exception(
            "Error disabling unattended upgrades, cmd: %s, code: %s, err: %s",
            exc.cmd,
            exc.returncode,
            exc.output,
        )
        raise SystemUserConfigurationError from exc
    except subprocess.SubprocessError as exc:
        raise SystemUserConfigurationError from exc


def _configure_usr_local_bin() -> None:
    """Change the permissions of /usr/local/bin dir to match GH hosted runners permissions.

    Raises:
        PermissionConfigurationError: if there was an error changing permissions.
    """
    try:
        # The 777 is to match the behavior of GitHub hosted runners
        output = subprocess.check_output(  # nosec: B603
            ["/usr/bin/chmod", "777", "/usr/local/bin"], timeout=30
        )
        logger.info("chmod /usr/local/bin out: %s", output)
    except subprocess.CalledProcessError as exc:
        logger.exception(
            "Error changing /usr/local/bin/ permissions, cmd: %s, code: %s, err: %s",
            exc.cmd,
            exc.returncode,
            exc.output,
        )
        raise PermissionConfigurationError from exc
    except subprocess.SubprocessError as exc:
        raise PermissionConfigurationError from exc


def _install_yarn() -> None:
    """Install yarn using NPM.

    Raises:
        YarnInstallError: If there was an error installing external package.
    """
    try:
        # 2024/04/26 There's a potential security risk here, npm is subject to toolchain attacks.
        output = subprocess.check_output(
            ["/usr/bin/npm", "install", "--global", "yarn"], timeout=60 * 5
        )  # nosec: B603
        logger.info("npm install yarn out: %s", output)
        output = subprocess.check_output(
            ["/usr/bin/npm", "cache", "clean", "--force"], timeout=60
        )  # nosec: B603
        logger.info("npm cache clean out: %s", output)
    except subprocess.CalledProcessError as exc:
        logger.exception(
            "Error installing Yarn, cmd: %s, code: %s, err: %s",
            exc.cmd,
            exc.returncode,
            exc.output,
        )
        raise YarnInstallError from exc
    except subprocess.SubprocessError as exc:
        raise YarnInstallError from exc


# Image compression might fail for arbitrary reasons - retrying usually solves this.
@retry(tries=5, delay=5, max_delay=60, backoff=2, local_logger=logger)
def _compress_image(image: Path) -> None:
    """Compress the image.

    Args:
        image: The image to compress.

    Raises:
        ImageCompressError: If there was something wrong compressing the image.
    """
    try:
        output = subprocess.check_output(  # nosec: B603
            ["/usr/bin/virt-sparsify", "--compress", str(image), str(IMAGE_OUTPUT_PATH)],
            timeout=60 * 10,
        )
        logger.info("virt-sparsify compress out: %s", output)
    except subprocess.CalledProcessError as exc:
        logger.exception(
            "Error compressing image, cmd: %s, code: %s, err: %s",
            exc.cmd,
            exc.returncode,
            exc.output,
        )
        raise ImageCompressError from exc
    except subprocess.SubprocessError as exc:
        raise ImageCompressError from exc
