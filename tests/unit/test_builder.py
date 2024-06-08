# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Unit tests for builder module."""

# Need access to protected functions for testing
# pylint:disable=protected-access

import time
from pathlib import Path
from typing import Any, Type
from unittest.mock import MagicMock

import pytest

from github_runner_image_builder import builder
from github_runner_image_builder.builder import (
    Arch,
    BaseImage,
    BaseImageDownloadError,
    BuildImageError,
    ChrootBaseError,
    DependencyInstallError,
    ImageCompressError,
    ImageConnectError,
    ImageResizeError,
    NetworkBlockDeviceError,
    PermissionConfigurationError,
    ResizePartitionError,
    SupportedBaseImageArch,
    SystemUserConfigurationError,
    UnattendedUpgradeDisableError,
    UnsupportedArchitectureError,
    YarnInstallError,
    YQBuildError,
    shutil,
    subprocess,
)


@pytest.mark.parametrize(
    "func, args",
    [
        pytest.param("_unmount_build_path", [], id="unmount build path"),
        pytest.param("_install_dependencies", [], id="install dependencies"),
        pytest.param("_enable_network_block_device", [], id="enable network block device"),
        pytest.param("_resize_image", [MagicMock()], id="resize image"),
        pytest.param("_resize_mount_partitions", [], id="resize mount partitions"),
        pytest.param("_disable_unattended_upgrades", [], id="disable unattended upgrades"),
        pytest.param("_configure_system_users", [], id="configure system users"),
        pytest.param("_configure_usr_local_bin", [], id="configure /usr/local/bin"),
        pytest.param("_compress_image", [MagicMock()], id="compress image"),
    ],
)
def test_subprocess_call_funcs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, func: str, args: list[Any]
):
    """
    arrange: given functions that consist of subprocess calls only with mocked subprocess calls.
    act: when the function is called.
    assert: no errors are raised.
    """
    monkeypatch.setattr(subprocess, "check_output", MagicMock())
    monkeypatch.setattr(subprocess, "run", MagicMock())
    monkeypatch.setattr(builder, "UBUNTU_HOME", tmp_path)
    # Bypass decorated retry sleep
    monkeypatch.setattr(time, "sleep", MagicMock())

    assert getattr(builder, func)(*args) is None


@pytest.mark.parametrize(
    "func, args, exc",
    [
        pytest.param(
            "_unmount_build_path", [], builder.UnmountBuildPathError, id="unmount build path"
        ),
        pytest.param("_resize_image", [MagicMock()], builder.ImageResizeError, id="resize image"),
        pytest.param(
            "_connect_image_to_network_block_device",
            [MagicMock()],
            builder.ImageConnectError,
            id="connect image to nbd",
        ),
        pytest.param(
            "_resize_mount_partitions", [], builder.ResizePartitionError, id="resize mount parts"
        ),
        pytest.param("_install_yq", [], builder.YQBuildError, id="install yq"),
        pytest.param(
            "_disable_unattended_upgrades",
            [],
            builder.UnattendedUpgradeDisableError,
            id="disable unattende upgrades",
        ),
        pytest.param(
            "_configure_system_users",
            [],
            builder.SystemUserConfigurationError,
            id="configure system users",
        ),
        pytest.param(
            "_configure_usr_local_bin",
            [],
            builder.PermissionConfigurationError,
            id="configure system users",
        ),
        pytest.param(
            "_install_yarn",
            [],
            builder.YarnInstallError,
            id="install yarn",
        ),
        pytest.param(
            "_disconnect_image_to_network_block_device",
            [],
            builder.ImageConnectError,
            id="disconnect image to nbd",
        ),
    ],
)
def test_subprocess_func_errors(
    monkeypatch: pytest.MonkeyPatch, func: str, args: list[Any], exc: Type[Exception]
):
    """
    arrange: given functions with subprocess calls that is monkeypatched to raise exceptions.
    act: when the function is called.
    assert: subprocess error is wrapped to expected error.
    """
    monkeypatch.setattr(
        subprocess,
        "check_output",
        MagicMock(side_effect=subprocess.SubprocessError("Test subprocess error")),
    )
    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(side_effect=subprocess.SubprocessError("Test subprocess error")),
    )
    # Bypass decorated retry sleep
    monkeypatch.setattr(time, "sleep", MagicMock())

    with pytest.raises(exc):
        getattr(builder, func)(*args)


def test_initialize(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given sub functions of initialize.
    act: when initialize is called.
    assert: the subfunctions are called.
    """
    monkeypatch.setattr(builder, "_install_dependencies", (install_mock := MagicMock()))
    monkeypatch.setattr(builder, "_enable_network_block_device", (enable_nbd_mock := MagicMock()))

    builder.initialize()

    install_mock.assert_called()
    enable_nbd_mock.assert_called()


def test__install_dependencies_error(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given mocked subprocess.check_output calls that raises CalledProcessError.
    act: when _install_dependencies is called.
    assert: DependencyInstallError is raised.
    """
    monkeypatch.setattr(
        subprocess,
        "check_output",
        MagicMock(
            side_effect=[None, None, subprocess.CalledProcessError(1, [], "Package not found.")]
        ),
    )

    with pytest.raises(DependencyInstallError) as exc:
        builder._install_dependencies()

    assert "Package not found" in str(exc.getrepr())


def test__enable_network_block_device_fail(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given subprocess run that raises CalledProcessError.
    act: when _enable_network_block_device is called.
    assert: NetworkBlockDeviceError is raised.
    """
    monkeypatch.setattr(
        subprocess,
        "check_output",
        MagicMock(side_effect=subprocess.CalledProcessError(1, [], "Module nbd not found")),
    )

    with pytest.raises(NetworkBlockDeviceError) as exc:
        builder._enable_network_block_device()

    assert "Module nbd not found" in str(exc.getrepr())


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
    monkeypatch.setattr(builder, "IMAGE_MOUNT_DIR", MagicMock())
    monkeypatch.setattr(builder, "_download_and_validate_image", MagicMock())
    monkeypatch.setattr(builder, "_resize_image", MagicMock())
    monkeypatch.setattr(builder, "_connect_image_to_network_block_device", MagicMock())
    monkeypatch.setattr(builder, "_resize_mount_partitions", MagicMock())
    monkeypatch.setattr(builder, "_replace_mounted_resolv_conf", MagicMock())
    monkeypatch.setattr(builder, "_install_yq", MagicMock())
    monkeypatch.setattr(builder, "ChrootContextManager", MagicMock())
    monkeypatch.setattr(builder.subprocess, "check_output", MagicMock())
    monkeypatch.setattr(builder, "_disable_unattended_upgrades", MagicMock())
    monkeypatch.setattr(builder, "_configure_system_users", MagicMock())
    monkeypatch.setattr(builder, "_install_yarn", MagicMock())
    monkeypatch.setattr(builder, "_disconnect_image_to_network_block_device", MagicMock())
    monkeypatch.setattr(builder, "_compress_image", MagicMock())
    monkeypatch.setattr(patch_obj, sub_func, mock)

    with pytest.raises(BuildImageError) as exc:
        builder.build_image(arch=MagicMock(), base_image=MagicMock())

    assert expected_message in str(exc.getrepr())


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
            builder,
            "_download_base_image",
            BaseImageDownloadError("Content too short"),
            "Content too short",
            id="Network interrupted",
        ),
        pytest.param(
            builder,
            "_fetch_shasums",
            BaseImageDownloadError("Content too short"),
            "Content too short",
            id="Network interrupted (SHASUM)",
        ),
    ],
)
def test__download_and_validate_image_error(
    patch_obj: Any,
    sub_func: str,
    exception: Exception,
    expected_message: str,
    monkeypatch: pytest.MonkeyPatch,
):
    """
    arrange: given monkeypatched sub functions of _download_and_validate_image that raises \
        exceptions.
    act: when _download_and_validate_image is called.
    assert: A BaseImageDownloadError is raised.
    """
    mock_func = MagicMock(side_effect=exception)
    monkeypatch.setattr(builder, "_get_supported_runner_arch", MagicMock)
    monkeypatch.setattr(builder, "_download_base_image", MagicMock)
    monkeypatch.setattr(builder, "_fetch_shasums", MagicMock)
    monkeypatch.setattr(builder, "_validate_checksum", MagicMock)
    monkeypatch.setattr(patch_obj, sub_func, mock_func)

    with pytest.raises(BaseImageDownloadError) as exc:
        builder._download_and_validate_image(arch=MagicMock(), base_image=MagicMock())

    assert expected_message in str(exc.getrepr())


def test__download_and_validate_image_no_shasum(
    monkeypatch: pytest.MonkeyPatch,
):
    """
    arrange: given monkeypatched _fetch_shasums that returns empty shasums.
    act: when _download_and_validate_image is called.
    assert: A BaseImageDownloadError is raised.
    """
    monkeypatch.setattr(builder, "_get_supported_runner_arch", MagicMock())
    monkeypatch.setattr(builder, "_download_base_image", MagicMock())
    monkeypatch.setattr(builder, "_fetch_shasums", MagicMock(return_value={}))

    with pytest.raises(BaseImageDownloadError) as exc:
        builder._download_and_validate_image(arch=MagicMock(), base_image=MagicMock())

    assert "Corresponding checksum not found." in str(exc.getrepr())


def test__download_and_validate_image_invalid_checksum(
    monkeypatch: pytest.MonkeyPatch,
):
    """
    arrange: given monkeypatched _validate_checksum that returns false.
    act: when _download_and_validate_image is called.
    assert: A BaseImageDownloadError is raised.
    """
    monkeypatch.setattr(builder, "_get_supported_runner_arch", MagicMock(return_value="x64"))
    monkeypatch.setattr(builder, "_download_base_image", MagicMock())
    monkeypatch.setattr(
        builder,
        "_fetch_shasums",
        MagicMock(return_value={"jammy-server-cloudimg-x64.img": "test"}),
    )
    monkeypatch.setattr(builder, "_validate_checksum", MagicMock(return_value=False))

    with pytest.raises(BaseImageDownloadError) as exc:
        builder._download_and_validate_image(arch=Arch.X64, base_image=BaseImage.JAMMY)

    assert "Invalid checksum." in str(exc.getrepr())


def test__download_and_validate_image(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given monkeypatched sub functions of _download_and_validate_image.
    act: when _download_and_validate_image is called.
    assert: the mocked subfunctions are called.
    """
    monkeypatch.setattr(
        builder, "_get_supported_runner_arch", get_arch_mock := MagicMock(return_value="x64")
    )
    monkeypatch.setattr(builder, "_download_base_image", download_base_mock := MagicMock())
    monkeypatch.setattr(
        builder,
        "_fetch_shasums",
        fetch_shasums_mock := MagicMock(return_value={"jammy-server-cloudimg-x64.img": "test"}),
    )
    monkeypatch.setattr(builder, "_validate_checksum", validate_checksum_mock := MagicMock())

    builder._download_and_validate_image(arch=Arch.X64, base_image=BaseImage.JAMMY)

    get_arch_mock.assert_called_once()
    download_base_mock.assert_called_once()
    fetch_shasums_mock.assert_called_once()
    validate_checksum_mock.assert_called_once()


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
def test__get_supported_runner_arch(arch: Arch, expected: SupportedBaseImageArch):
    """
    arrange: given an architecture value that is supported.
    act: when _get_supported_runner_arch is called.
    assert: Expected architecture in cloud_images format is returned.
    """
    assert builder._get_supported_runner_arch(arch) == expected


def test__download_base_image_error(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given monkeypatched urlretrieve function that raises an error.
    act: when _download_base_image is called.
    assert: BaseImageDownloadError is raised.
    """
    # Bypass decorated retry sleep
    monkeypatch.setattr(time, "sleep", MagicMock())
    monkeypatch.setattr(
        builder.urllib.request,
        "urlretrieve",
        MagicMock(side_effect=builder.urllib.error.URLError(reason="Content too short")),
    )

    with pytest.raises(BaseImageDownloadError) as exc:
        builder._download_base_image(
            base_image=MagicMock(), bin_arch=MagicMock(), output_filename=MagicMock()
        )

    assert "Content too short" in str(exc.getrepr())


def test__download_base_image(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given monkeypatched urlretrieve function.
    act: when _download_base_image is called.
    assert: Path from output_filename input is returned.
    """
    monkeypatch.setattr(builder.urllib.request, "urlretrieve", MagicMock())
    test_file_name = "test_file_name"

    assert Path("test_file_name") == builder._download_base_image(
        base_image=MagicMock(), bin_arch=MagicMock(), output_filename=test_file_name
    )


def test__fetch_shasums_error(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given monkeypatched requests function that raises an error.
    act: when _fetch_shasums is called.
    assert: BaseImageDownloadError is raised.
    """
    # Bypass decorated retry sleep
    monkeypatch.setattr(time, "sleep", MagicMock())
    monkeypatch.setattr(
        builder.requests,
        "get",
        MagicMock(side_effect=builder.requests.RequestException("Content too short")),
    )

    with pytest.raises(BaseImageDownloadError) as exc:
        builder._fetch_shasums(base_image=MagicMock())

    assert "Content too short" in str(exc.getrepr())


def test__fetch_shasums(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given monkeypatched requests function that returns mocked contents of SHA256SUMS.
    act: when _fetch_shasums is called.
    assert: a dictionary with filename to shasum is created.
    """
    # Bypass decorated retry sleep
    monkeypatch.setattr(time, "sleep", MagicMock())
    mock_response = MagicMock()
    mock_response.content = bytes(
        """test_shasum1 *file1
test_shasum2 *file2
test_shasum3 *file3
""",
        encoding="utf-8",
    )
    monkeypatch.setattr(builder.requests, "get", MagicMock(return_value=mock_response))

    assert {
        "file1": "test_shasum1",
        "file2": "test_shasum2",
        "file3": "test_shasum3",
    } == builder._fetch_shasums(base_image=MagicMock())


@pytest.mark.parametrize(
    "content, checksum, expected",
    [
        pytest.param(
            "sha256sumteststring",
            "52b60ec50ea69cd09d5f25b75c295b93181eaba18444fdbc537beee4653bad7e",
            True,
        ),
        pytest.param("test", "test", False),
    ],
)
def test__validate_checksum(tmp_path: Path, content: str, checksum: str, expected: bool):
    """
    arrange: given a file content and a checksum pair.
    act: when _validate_checksum is called.
    assert: expected result is returned.
    """
    test_path = tmp_path / "test"
    test_path.write_text(content, encoding="utf-8")

    assert expected == builder._validate_checksum(test_path, checksum)


def test__resize_image_fail(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched subprocess.run that raises an exception.
    act: when _resize_image is called.
    assert: ImageResizeError is raised.
    """
    mock_run = MagicMock(
        side_effect=subprocess.CalledProcessError(
            returncode=1, cmd=[], output="", stderr="resize error"
        )
    )
    monkeypatch.setattr(
        subprocess,
        "check_output",
        mock_run,
    )

    with pytest.raises(ImageResizeError) as exc:
        builder._resize_image(image_path=MagicMock())

    assert "resize error" in str(exc.getrepr())


def test__mount_network_block_device_partition(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched mock subprocess run.
    act: when _mount_network_block_device_partition is called.
    assert: subprocess run call is made.
    """
    monkeypatch.setattr(subprocess, "check_output", (mock_run_call := MagicMock()))

    builder._mount_network_block_device_partition()

    mock_run_call.assert_called_once()


def test__connect_image_to_network_block_device_fail(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched process calls that fails.
    act: when _connect_image_to_network_block_device is called.
    assert: ImageMountError is raised.
    """
    monkeypatch.setattr(
        subprocess,
        "check_output",
        MagicMock(side_effect=subprocess.CalledProcessError(1, [], "", "error mounting")),
    )

    with pytest.raises(ImageConnectError) as exc:
        builder._connect_image_to_network_block_device(image_path=MagicMock())

    assert "error mounting" in str(exc.getrepr())


def test__connect_image_to_network_block_device(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched mock process run calls and \
        _mount_network_block_device_partition call.
    act: when _connect_image_to_network_block_device is called.
    assert: expected calls are made.
    """
    monkeypatch.setattr(subprocess, "check_output", (run_mock := MagicMock()))

    builder._connect_image_to_network_block_device(image_path=MagicMock())

    run_mock.assert_called()


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
        "check_output",
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
    # Bypass decorated retry sleep
    monkeypatch.setattr(time, "sleep", MagicMock())
    monkeypatch.setattr(
        subprocess,
        "check_output",
        MagicMock(
            # tried 3 times via retry
            side_effect=[None, subprocess.CalledProcessError(1, [], "", "Go build error.")]
            * 3
        ),
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
    # Bypass decorated retry sleep
    monkeypatch.setattr(time, "sleep", MagicMock())
    monkeypatch.setattr(builder, "YQ_REPOSITORY_PATH", MagicMock(return_value=True))
    monkeypatch.setattr(subprocess, "check_output", (run_mock := MagicMock()))
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
    # Bypass decorated retry sleep
    monkeypatch.setattr(time, "sleep", MagicMock())
    monkeypatch.setattr(subprocess, "check_output", (run_mock := MagicMock()))
    monkeypatch.setattr(shutil, "copy", (copy_mock := MagicMock()))

    builder._install_yq()

    run_mock.assert_called()
    copy_mock.assert_called()


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
        "check_output",
        MagicMock(
            side_effect=[
                *([None] * 7),
                subprocess.CalledProcessError(1, [], "Failed to disable unattended upgrades", ""),
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
        "check_output",
        MagicMock(
            side_effect=[
                *([None] * 2),
                subprocess.CalledProcessError(1, [], "Failed to add group.", ""),
            ]
        ),
    )

    with pytest.raises(SystemUserConfigurationError) as exc:
        builder._configure_system_users()

    assert "Failed to add group." in str(exc.getrepr())


def test__configure_usr_local_bin(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched subprocess run calls that raises an exception.
    act: when _configure_usr_local_bin is called.
    assert: PermissionConfigurationError is raised.
    """
    monkeypatch.setattr(
        builder.subprocess,
        "check_output",
        MagicMock(
            side_effect=subprocess.CalledProcessError(1, [], "Failed change permissions.", ""),
        ),
    )

    with pytest.raises(PermissionConfigurationError) as exc:
        builder._configure_usr_local_bin()

    assert "Failed change permissions." in str(exc.getrepr())


def test__install_yarn_error(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched subprocess.run that raises an error.
    act: when _install_yarn is called.
    assert: ExternalPackageInstallError is raised.
    """
    # The test mocks use similar codes.
    monkeypatch.setattr(  # pylint: disable=duplicate-code
        subprocess,
        "check_output",
        MagicMock(
            side_effect=[
                None,
                subprocess.CalledProcessError(1, [], "Failed to clean npm cache.", ""),
            ]
        ),
    )

    with pytest.raises(YarnInstallError) as exc:
        builder._install_yarn()

    assert "Failed to clean npm cache." in str(exc.getrepr())


def test__install_yarn(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched functions of _install_yarn.
    act: when _install_yarn is called.
    assert: The function exists without raising an error.
    """
    monkeypatch.setattr(subprocess, "check_output", MagicMock())

    assert builder._install_yarn() is None


def test__disconnect_image_to_network_block_device_fail(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched process calls that fails.
    act: when _disconnect_image_to_network_block_device is called.
    assert: ImageMountError is raised.
    """
    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(side_effect=subprocess.CalledProcessError(1, [], "", "error mounting")),
    )

    with pytest.raises(ImageConnectError) as exc:
        builder._disconnect_image_to_network_block_device()

    assert "error mounting" in str(exc.getrepr())


def test__disconnect_image_to_network_block_device(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given a monkeypatched mock process run calls and \
        _mount_network_block_device_partition call.
    act: when _disconnect_image_to_network_block_device is called.
    assert: expected calls are made.
    """
    monkeypatch.setattr(subprocess, "run", (check_mock := MagicMock()))

    builder._disconnect_image_to_network_block_device()

    check_mock.assert_called()


def test__compress_image_fail(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given subprocess run that raises CalledProcessError.
    act: when _compress_image is called.
    assert: ImageCompressError is raised.
    """
    # Bypass decorated retry sleep
    monkeypatch.setattr(time, "sleep", MagicMock())
    monkeypatch.setattr(
        subprocess, "run", MagicMock(return_value=subprocess.CompletedProcess([], 0, "", ""))
    )
    monkeypatch.setattr(
        subprocess,
        "check_output",
        MagicMock(side_effect=subprocess.CalledProcessError(1, [], "Compression error")),
    )

    with pytest.raises(ImageCompressError) as exc:
        builder._compress_image(image=MagicMock())

    assert "Compression error" in str(exc.getrepr())


def test__compress_image_no_kvm(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given subprocess run for kvm-ok that raises an error.
    act: when _compress_image is called.
    assert: image is renamed.
    """
    # Bypass decorated retry sleep
    monkeypatch.setattr(time, "sleep", MagicMock())
    monkeypatch.setattr(
        subprocess,
        "run",
        MagicMock(side_effect=subprocess.CalledProcessError(1, [], "kvm module not enabled")),
    )
    image_mock = MagicMock()

    builder._compress_image(image=image_mock)
    image_mock.rename.assert_called_once()


def test__compress_image_subprocess_error(monkeypatch: pytest.MonkeyPatch):
    """
    arrange: given subprocess check_output raises an error.
    act: when _compress_image is called.
    assert: ImageCompressError is raised.
    """
    # Bypass decorated retry sleep
    monkeypatch.setattr(time, "sleep", MagicMock())
    monkeypatch.setattr(subprocess, "run", MagicMock())
    monkeypatch.setattr(
        subprocess,
        "check_output",
        MagicMock(side_effect=subprocess.SubprocessError("Image subprocess err")),
    )
    image_mock = MagicMock()

    with pytest.raises(builder.ImageCompressError) as exc:
        builder._compress_image(image=image_mock)

    assert "Image subprocess err" in str(exc.getrepr())
