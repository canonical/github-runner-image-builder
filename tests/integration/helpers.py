# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper utilities for integration tests."""

import collections
import inspect
import platform
import tarfile
import time
from functools import partial
from pathlib import Path
from string import Template
from typing import Awaitable, Callable, ParamSpec, TypeVar, cast

from pylxd import Client
from pylxd.models.image import Image
from pylxd.models.instance import Instance, InstanceState
from requests_toolbelt import MultipartEncoder

P = ParamSpec("P")
R = TypeVar("R")
S = Callable[P, R] | Callable[P, Awaitable[R]]


async def wait_for(
    func: S,
    timeout: int | float = 300,
    check_interval: int = 10,
) -> R:
    """Wait for function execution to become truthy.

    Args:
        func: A callback function to wait to return a truthy value.
        timeout: Time in seconds to wait for function result to become truthy.
        check_interval: Time in seconds to wait between ready checks.

    Raises:
        TimeoutError: if the callback function did not return a truthy value within timeout.

    Returns:
        The result of the function if any.
    """
    deadline = time.time() + timeout
    is_awaitable = inspect.iscoroutinefunction(func)
    while time.time() < deadline:
        if is_awaitable:
            if result := await cast(Awaitable, func()):
                return result
        else:
            if result := func():
                return cast(R, result)
        time.sleep(check_interval)

    # final check before raising TimeoutError.
    if is_awaitable:
        if result := await cast(Awaitable, func()):
            return result
    else:
        if result := func():
            return cast(R, result)
    raise TimeoutError()


IMAGE_TO_TAG = {"jammy": "22.04", "noble": "24.04"}


def _create_metadata_tar_gz(image: str, tmp_path: Path) -> Path:
    """Create metadata.tar.gz contents.

    Args:
        image: The ubuntu LTS iamge name.
        tmp_path: Temporary dir.
    """
    # Create metadata.yaml
    template = Template(
        Path("tests/integration/testdata/metadata.yaml.tmpl").read_text(encoding="utf-8")
    )
    metadata_contents = template.substitute(
        {"arch": platform.machine(), "tag": IMAGE_TO_TAG[image], "image": image}
    )
    meta_path = tmp_path / "metadata.yaml"
    meta_path.write_text(metadata_contents, encoding="utf-8")

    # Pack templates/ and metada.yaml
    templates_path = Path("tests/integration/testdata/templates")
    metadata_tar = tmp_path / Path("metadata.tar.gz")

    with tarfile.open(metadata_tar, "w:gz") as tar:
        tar.add(meta_path, arcname=meta_path.name)
        tar.add(templates_path, arcname=templates_path.name)

    return metadata_tar


# This is a workaround until https://github.com/canonical/pylxd/pull/577 get's merged.
def _post_vm_img(
    client: Client,
    image_data: bytes,
    metadata: bytes | None = None,
    public: bool = False,
) -> Image:
    """Create an LXD VM image.

    Args:
        client: The LXD client.
        image_data: Image qcow2 (.img) file contents in bytes.
        metadata: The metadata.tar.gz contents in bytes.
        public: Whether the image should be publically available.
    """
    headers = {}
    if public:
        headers["X-LXD-Public"] = "1"

    if metadata is not None:
        # Image uploaded as chunked/stream (metadata, rootfs)
        # multipart message.
        # Order of parts is important metadata should be passed first
        files = collections.OrderedDict(
            {
                "metadata": ("metadata", metadata, "application/octet-stream"),
                # rootfs is container, rootfs.img is VM
                "rootfs.img": ("rootfs.img", image_data, "application/octet-stream"),
            }
        )
        data = MultipartEncoder(files)
        headers.update({"Content-Type": data.content_type})
    else:
        data = image_data

    response = client.api.images.post(data=data, headers=headers)
    operation = client.operations.wait_for_operation(response.json()["operation"])
    return Image(client, fingerprint=operation.metadata["fingerprint"])


def create_lxd_vm_image(lxd_client: Client, img_path: Path, image: str, tmp_path: Path) -> Image:
    """Create LXD VM image.

    Args:
        lxd_client: PyLXD client.
        img_path: qcow2 (.img) file path to upload.
        tmp_path: Temporary dir.
        image: The Ubuntu image name.

    Returns:
        The created LXD image.
    """
    metadata_tar = _create_metadata_tar_gz(image=image, tmp_path=tmp_path)
    lxd_image = _post_vm_img(
        lxd_client, img_path.read_bytes(), metadata_tar.read_bytes(), public=True
    )
    lxd_image.add_alias(image, f"Ubuntu {image} {IMAGE_TO_TAG[image]} image.")
    return lxd_image


def _instance_running(instance: Instance) -> bool:
    """Check if the instance is running.

    Args:
        instance: The lxd instance.

    Returns:
        Whether the instance is running.
    """
    state: InstanceState = instance.state()
    if state.status != "Running":
        return False
    try:
        result = instance.execute(["echo", "'hello world'"])
    except BrokenPipeError:
        return False
    return result.exit_code == 0


async def create_lxd_instance(lxd_client: Client, image: str) -> Instance:
    """Create and wait for LXD instance to become active.

    Args:
        lxd_client: PyLXD client.
        image: The Ubuntu image name.

    Returns:
        The created and running LXD instance.
    """
    instance_config = {
        "name": f"test-{image}",
        "source": {"type": "image", "alias": image},
        "type": "virtual-machine",
        "config": {"limits.cpu": "2"},
    }
    instance: Instance = lxd_client.instances.create(  # pylint: disable=no-member
        instance_config, wait=True
    )
    instance.start(timeout=10 * 60, wait=True)
    await wait_for(partial(_instance_running, instance))

    return instance
