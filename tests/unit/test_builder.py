# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for builder module."""

# Need access to protected functions for testing
# pylint:disable=protected-access

import time
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from github_runner_image_builder import builder
from github_runner_image_builder.builder import (
    Arch,
    BaseImage,
    BuilderSetupError,
    BuildImageError,
    ChrootBaseError,
    CleanBuildStateError,
    CloudImageDownloadError,
    DependencyInstallError,
    ExternalPackageInstallError,
    ImageCompressError,
    ImageMountError,
    ImageResizeError,
    NetworkBlockDeviceError,
    ResizePartitionError,
    SupportedCloudImageArch,
    SystemUserConfigurationError,
    UnattendedUpgradeDisableError,
    UnsupportedArchitectureError,
    YQBuildError,
    os,
    shutil,
    subprocess,
)


def test__install_dependencies_package_not_found(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given apt.add_package that raises PackageNotFoundError.
    act: when _install_dependencies is called.
    assert: DependencyInstallError is raised.
    """
    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(
            side_effect=[None, None, subprocess.CalledProcessError(1, [], "Package not found.")]
        ),
    )

    with pytest.raises(DependencyInstallError) as exc:
        builder._install_dependencies()

    assert "Package not found" in str(exc.getrepr())


def test__enable_nbd_fail(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given subprocess run that raises CalledProcessError.
    act: when _enable_nbd is called.
    assert: NetworkBlockDeviceError is raised.
    """
    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(side_effect=subprocess.CalledProcessError(1, [], "Module nbd not found")),
    )

    with pytest.raises(NetworkBlockDeviceError) as exc:
        builder._enable_nbd()

    assert "Module nbd not found" in str(exc.getrepr())


@pytest.mark.parametrize(
    "patch_obj, sub_func, exception, expected_message",
    [
        pytest.param(
            builder,
            "_install_dependencies",
            DependencyInstallError("Dependency not found"),
            "Dependency not found",
            id="Dependency not found",
        ),
        pytest.param(
            builder,
            "_enable_nbd",
            NetworkBlockDeviceError("Unable to enable nbd"),
            "Unable to enable nbd",
            id="Failed to enable nbd",
        ),
    ],
)
def test_setup_builder_fail(
    patch_obj: Any,
    sub_func: str,
    exception: Exception,
    expected_message: str,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    arrange: given a monkeypatched sub functions of setup_builder that raises given exceptions.
    act: when setup_builder is called.
    assert: A BuilderSetupError is raised.
    """
    mock_func = MagicMock(side_effect=exception)
    monkeypatch.setattr(builder, "_install_dependencies", MagicMock)
    monkeypatch.setattr(builder, "_enable_nbd", MagicMock)
    monkeypatch.setattr(patch_obj, sub_func, mock_func)

    with pytest.raises(BuilderSetupError) as exc:
        builder.setup_builder()

    assert expected_message in str(exc.getrepr())


def test__get_supported_runner_arch_unsupported_error():
    """
    arrange: given an architecture value that isn't supported.
    act: when _get_supported_runner_arch is called.
    assert: UnsupportedArchitectureError is raised.
    """
    arch = MagicMock()
    with pytest.raises(UnsupportedArchitectureError):
        builder._get_supported_runner_arch(arch)


@pytest.mark.parametrize(
    "arch, expected",
    [
        pytest.param(Arch.ARM64, "arm64", id="ARM64"),
        pytest.param(Arch.X64, "amd64", id="AMD64"),
    ],
)
def test__get_supported_runner_arch(arch: Arch, expected: SupportedCloudImageArch):
    """
    arrange: given an architecture value that is supported.
    act: when _get_supported_runner_arch is called.
    assert: Expected architecture in cloud_images format is returned.
    """
    assert builder._get_supported_runner_arch(arch) == expected


def test__clean_build_state_error(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a magic mocked IMAGE_MOUNT_DIR and subprocess call that raises exceptions.
    act: when _clean_build_state is called.
    assert: CleanBuildStateError is raised.
    """
    mock_mount_dir = MagicMock()
    mock_subprocess_run = MagicMock(
        side_effect=subprocess.CalledProcessError(1, [], "", "qemu-nbd error")
    )
    monkeypatch.setattr(builder, "IMAGE_MOUNT_DIR", mock_mount_dir)
    monkeypatch.setattr(subprocess, "run", mock_subprocess_run)

    with pytest.raises(CleanBuildStateError) as exc:
        builder._clean_build_state()

    assert "qemu-nbd error" in str(exc.getrepr())


def test__clean_build_state(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a magic mocked IMAGE_MOUNT_DIR and qemu-nbd subprocess call.
    act: when _clean_build_state is called.
    assert: the mocks are called.
    """
    mock_mount_dir = MagicMock()
    mock_subprocess_run = MagicMock()
    monkeypatch.setattr(builder, "IMAGE_MOUNT_DIR", mock_mount_dir)
    monkeypatch.setattr(builder.subprocess, "run", mock_subprocess_run)

    builder._clean_build_state()

    mock_mount_dir.mkdir.assert_called_once()
    mock_subprocess_run.assert_called()


@pytest.mark.parametrize(
    "patch_obj, sub_func, exception, expected_message",
    [
        pytest.param(
            builder,
            "_get_supported_runner_arch",
            UnsupportedArchitectureError("Unsupported architecture"),
            "Unsupported architecture",
            id="Unsupported architecture",
        ),
        pytest.param(
            builder.urllib.request,
            "urlretrieve",
            builder.urllib.error.ContentTooShortError("Network interrupted", ""),
            "Network interrupted",
            id="Network interrupted",
        ),
    ],
)
def test__download_cloud_image_fail(
    patch_obj: Any,
    sub_func: str,
    exception: Exception,
    expected_message: str,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    arrange: given monkeypatched sub functions of _download_cloud_image that raises exceptions.
    act: when _download_cloud_image is called.
    assert: A CloudImageDownloadError is raised.
    """
    mock_func = MagicMock(side_effect=exception)
    monkeypatch.setattr(builder, "_get_supported_runner_arch", MagicMock)
    monkeypatch.setattr(builder.urllib.request, "urlretrieve", MagicMock)
    monkeypatch.setattr(patch_obj, sub_func, mock_func)

    with pytest.raises(CloudImageDownloadError) as exc:
        builder._download_cloud_image(arch=MagicMock(), base_image=MagicMock())

    assert expected_message in str(exc.getrepr())


def test__download_cloud_image(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given monkeypatched sub functions of _download_cloud_image.
    act: when _download_cloud_image is called.
    assert: the downloaded path is returned.
    """
    monkeypatch.setattr(builder, "_get_supported_runner_arch", MagicMock(return_value="amd64"))
    monkeypatch.setattr(builder.urllib.request, "urlretrieve", MagicMock())

    assert builder._download_cloud_image(arch=Arch.X64, base_image=BaseImage.JAMMY) == Path(
        "jammy-server-cloudimg-amd64.img"
    )


def test__resize_cloud_img_fail(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched subprocess.run that raises an exception.
    act: when _resize_cloud_img is called.
    assert: ImageResizeError is raised.
    """
    mock_run = MagicMock(
        side_effect=subprocess.CalledProcessError(
            returncode=1, cmd=[], output="", stderr="resize error"
        )
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        mock_run,
    )

    with pytest.raises(ImageResizeError) as exc:
        builder._resize_cloud_img(cloud_image_path=MagicMock())

    assert "resize error" in str(exc.getrepr())


def test__mount_nbd_partition(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched mock subprocess run.
    act: when _mount_nbd_partition is called.
    assert: subprocess run call is made.
    """
    monkeypatch.setattr(subprocess, "run", (mock_run_call := MagicMock()))

    builder._mount_nbd_partition()

    mock_run_call.assert_called_once()


def test__mount_image_to_network_block_device_fail(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched process calls that fails.
    act: when _mount_image_to_network_block_device is called.
    assert: ImageMountError is raised.
    """
    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(side_effect=subprocess.CalledProcessError(1, [], "", "error mounting")),
    )

    with pytest.raises(ImageMountError) as exc:
        builder._mount_image_to_network_block_device(cloud_image_path=MagicMock())

    assert "error mounting" in str(exc.getrepr())


def test__mount_image_to_network_block_device(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched mock process run calls and _mount_nbd_partition call.
    act: when _mount_image_to_network_block_device is called.
    assert: expected calls are made.
    """
    monkeypatch.setattr(subprocess, "run", (run_mock := MagicMock()))
    monkeypatch.setattr(builder, "_mount_nbd_partition", (mount_mock := MagicMock()))

    builder._mount_image_to_network_block_device(cloud_image_path=MagicMock())

    run_mock.assert_called_once()
    mount_mock.assert_called_once()


def test__replace_mounted_resolv_conf(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched MOUNTED_RESOLV_CONF_PATH and shutil.copy call.
    act: when _replace_mounted_resolv_conf.
    assert: expected calls are made on the mocks.
    """
    mock_mounted_resolv_conf_path = MagicMock()
    mock_copy = MagicMock()
    monkeypatch.setattr(builder, "MOUNTED_RESOLV_CONF_PATH", mock_mounted_resolv_conf_path)
    monkeypatch.setattr(builder.shutil, "copy", mock_copy)

    builder._replace_mounted_resolv_conf()

    mock_mounted_resolv_conf_path.unlink.assert_called_once()
    mock_copy.assert_called_once()


def test__resize_mount_partitions(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched subprocess calls that raises CalledProcessError.
    act: when _resize_mount_partitions is called
    assert: ResizePartitionError is raised.
    """
    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(side_effect=[None, subprocess.CalledProcessError(1, [], "", "resize error")]),
    )

    with pytest.raises(ResizePartitionError) as exc:
        builder._resize_mount_partitions()

    assert "resize error" in str(exc.getrepr())


def test__install_yq_error(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched subprocess.run function that raises an error.
    act: when _install_yq is called.
    assert: YQBuildError is raised.
    """
    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(side_effect=[None, subprocess.CalledProcessError(1, [], "", "Go build error.")]),
    )

    with pytest.raises(YQBuildError) as exc:
        builder._install_yq()

    assert "Go build error" in str(exc.getrepr())


def test__install_yq_already_exists(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched yq mocked path that already exists.
    act: when _install_yq is called.
    assert: Mock functions are called.
    """
    monkeypatch.setattr(builder, "YQ_REPOSITORY_PATH", MagicMock(return_value=True))
    monkeypatch.setattr(subprocess, "run", (run_mock := MagicMock()))
    monkeypatch.setattr(shutil, "copy", (copy_mock := MagicMock()))

    builder._install_yq()

    run_mock.assert_called()
    copy_mock.assert_called()


def test__install_yq(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched yq install mock functions.
    act: when _install_yq is called.
    assert: Mock functions are called.
    """
    monkeypatch.setattr(subprocess, "run", (run_mock := MagicMock()))
    monkeypatch.setattr(shutil, "copy", (copy_mock := MagicMock()))

    builder._install_yq()

    run_mock.assert_called()
    copy_mock.assert_called()


def test__create_python_symlinks(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched os.symlink function.
    act: when _create_python_symlinks is called.
    assert: the symlink function is called.
    """
    mock_symlink_call = MagicMock()
    monkeypatch.setattr(os, "symlink", mock_symlink_call)

    builder._create_python_symlinks()

    mock_symlink_call.assert_called()


def test__disable_unattended_upgrades_subprocess_fail(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched subprocess run function that raises SubprocessError.
    act: when _disable_unattended_upgrades is called.
    assert: the UnattendedUpgradeDisableError is raised.
    """
    # Pylint thinks the testing mock patches are duplicate code (side effects are different).
    # pylint: disable=duplicate-code
    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(
            side_effect=[
                *([None] * 7),
                subprocess.SubprocessError("Failed to disable unattended upgrades"),
            ]
        ),
    )

    with pytest.raises(UnattendedUpgradeDisableError) as exc:
        builder._disable_unattended_upgrades()

    assert "Failed to disable unattended upgrades" in str(exc.getrepr())


def test__configure_system_users(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched subprocess run calls that raises an exception.
    act: when _configure_system_users is called.
    assert: SystemUserConfigurationError is raised.
    """
    monkeypatch.setattr(builder, "UBUNTU_HOME", MagicMock())
    monkeypatch.setattr(
        builder.subprocess,
        "run",
        MagicMock(side_effect=[*([None] * 5), subprocess.SubprocessError("Failed to add group.")]),
    )

    with pytest.raises(SystemUserConfigurationError) as exc:
        builder._configure_system_users()

    assert "Failed to add group." in str(exc.getrepr())


def test__install_external_packages_error(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched subprocess.run that raises an error.
    act: when _install_external_packages is called.
    assert: ExternalPackageInstallError is raised.
    """
    # The test mocks use similar codes.
    monkeypatch.setattr(  # pylint: disable=duplicate-code
        subprocess,
        "run",
        MagicMock(
            side_effect=[
                None,
                subprocess.CalledProcessError(1, [], "", "Failed to clean npm cache."),
            ]
        ),
    )

    with pytest.raises(ExternalPackageInstallError) as exc:
        builder._install_external_packages()

    assert "Failed to clean npm cache." in str(exc.getrepr())


def test__install_external_packages(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched functions of _install_external_packages.
    act: when _install_external_packages is called.
    assert: The function exists without raising an error.
    """
    monkeypatch.setattr(subprocess, "run", MagicMock())

    assert builder._install_external_packages() is None


def test__compress_image_fail(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given subprocess run that raises CalledProcessError.
    act: when _compress_image is called.
    assert: ImageCompressError is raised.
    """
    # Bypass decorated retry sleep
    monkeypatch.setattr(time, "sleep", MagicMock())
    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(side_effect=subprocess.CalledProcessError(1, [], "Compression error")),
    )

    with pytest.raises(ImageCompressError) as exc:
        builder._compress_image(image=MagicMock())

    assert "Compression error" in str(exc.getrepr())


@pytest.mark.parametrize(
    "patch_obj, sub_func, mock, expected_message",
    [
        pytest.param(
            builder,
            "_resize_mount_partitions",
            MagicMock(side_effect=ResizePartitionError("Partition resize failed")),
            "Partition resize failed",
            id="Partition resize failed",
        ),
        pytest.param(
            builder,
            "ChrootContextManager",
            MagicMock(side_effect=ChrootBaseError("Failed to chroot into dir")),
            "Failed to chroot into dir",
            id="Failed to chroot into dir",
        ),
        pytest.param(
            builder,
            "_compress_image",
            MagicMock(side_effect=ImageCompressError("Failed to compress image")),
            "Failed to compress image",
            id="Failed to compress image",
        ),
    ],
)
def test_build_image_error(
    patch_obj: Any,
    sub_func: str,
    mock: MagicMock,
    expected_message: str,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    arrange: given a monkeypatched functions of build_image that raises exceptions.
    act: when build_image is called.
    assert: BuildImageError is raised.
    """
    monkeypatch.setattr(builder, "_clean_build_state", MagicMock())
    monkeypatch.setattr(builder, "_download_cloud_image", MagicMock())
    monkeypatch.setattr(builder, "_resize_cloud_img", MagicMock())
    monkeypatch.setattr(builder, "_mount_image_to_network_block_device", MagicMock())
    monkeypatch.setattr(builder, "_resize_mount_partitions", MagicMock())
    monkeypatch.setattr(builder, "_replace_mounted_resolv_conf", MagicMock())
    monkeypatch.setattr(builder, "_install_yq", MagicMock())
    monkeypatch.setattr(builder, "ChrootContextManager", MagicMock())
    monkeypatch.setattr(builder.subprocess, "run", MagicMock())
    monkeypatch.setattr(builder, "_create_python_symlinks", MagicMock())
    monkeypatch.setattr(builder, "_disable_unattended_upgrades", MagicMock())
    monkeypatch.setattr(builder, "_configure_system_users", MagicMock())
    monkeypatch.setattr(builder, "_install_external_packages", MagicMock())
    monkeypatch.setattr(builder, "_compress_image", MagicMock())
    monkeypatch.setattr(patch_obj, sub_func, mock)

    with pytest.raises(BuildImageError) as exc:
        builder.build_image(config=MagicMock())

    assert expected_message in str(exc.getrepr())
