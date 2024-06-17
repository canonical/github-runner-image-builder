# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Helper utilities for integration tests."""

import collections
import inspect
import logging
import platform
import tarfile
import time
from functools import partial
from pathlib import Path
from string import Template
from typing import Awaitable, Callable, ParamSpec, TypeVar, cast

from fabric import Connection as SSHConnection
from fabric import Result
from invoke.exceptions import UnexpectedExit
from openstack.compute.v2.server import Server
from openstack.connection import Connection
from paramiko.ssh_exception import NoValidConnectionsError
from pylxd import Client
from pylxd.models.image import Image
from pylxd.models.instance import Instance, InstanceState
from requests_toolbelt import MultipartEncoder

from tests.integration import types

logger = logging.getLogger(__name__)

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


def create_lxd_vm_image(lxd_client: Client, img_path: Path, image: str, tmp_path: Path) -> Image:
    """Create LXD VM image.

    1. Creates the metadata.tar.gz file with the corresponding Ubuntu OS image and a pre-defined
    templates directory. See testdata/templates.
    2. Uploads the created VM image to LXD - metadata and image of qcow2 format is required.
    3. Tags the uploaded image with an alias for test use.

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


IMAGE_TO_TAG = {"jammy": "22.04", "noble": "24.04"}


def _create_metadata_tar_gz(image: str, tmp_path: Path) -> Path:
    """Create metadata.tar.gz contents.

    Args:
        image: The ubuntu LTS image name.
        tmp_path: Temporary dir.

    Returns:
        The path to created metadata.tar.
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


# This is a workaround until https://github.com/canonical/pylxd/pull/577 gets merged.
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
        public: Whether the image should be publicly available.

    Returns:
        The created LXD Image instance.
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
        "config": {"limits.cpu": "3", "limits.memory": "8192MiB"},
    }
    instance: Instance = lxd_client.instances.create(  # pylint: disable=no-member
        instance_config, wait=True
    )
    instance.start(timeout=10 * 60, wait=True)
    await wait_for(partial(_instance_running, instance))

    return instance


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
        result = instance.execute(
            ["sudo", "--user", "ubuntu", "sudo", "systemctl", "is-active", "snapd.seeded.service"]
        )
    except BrokenPipeError:
        return False
    return result.exit_code == 0


# All the arguments are necessary
async def wait_for_valid_connection(  # pylint: disable=too-many-arguments
    connection: Connection,
    server_name: str,
    network: str,
    ssh_key: Path,
    timeout: int = 30 * 60,
    proxy: types.ProxyConfig | None = None,
) -> SSHConnection:
    """Wait for a valid SSH connection from Openstack server.

    Args:
        connection: The openstack connection client to communicate with Openstack.
        server_name: Openstack server to find the valid connection from.
        network: The network to find valid connection from.
        ssh_key: The path to public ssh_key to create connection with.
        timeout: Number of seconds to wait before raising a timeout error.
        proxy: The proxy to configure on host runner.

    Raises:
        TimeoutError: If no valid connections were found.

    Returns:
        SSHConnection.
    """
    start_time = time.time()
    while time.time() - start_time <= timeout:
        server: Server | None = connection.get_server(name_or_id=server_name)
        if not server or not server.addresses:
            time.sleep(10)
            continue
        for address in server.addresses[network]:
            ip = address["addr"]
            logger.info("Trying SSH into %s using key: %s...", ip, str(ssh_key.absolute()))
            ssh_connection = SSHConnection(
                host=ip,
                user="ubuntu",
                connect_kwargs={"key_filename": str(ssh_key.absolute())},
                connect_timeout=10 * 60,
            )
            try:
                result: Result = ssh_connection.run("echo 'hello world'")
                if result.ok:
                    await _install_proxy(conn=ssh_connection, proxy=proxy)
                    return ssh_connection
            except (NoValidConnectionsError, TimeoutError) as exc:
                logger.warning("Connection not yet ready, %s.", str(exc))
        time.sleep(10)
    raise TimeoutError("No valid ssh connections found.")


async def _install_proxy(conn: SSHConnection, proxy: types.ProxyConfig | None = None):
    """Run commands to install proxy.

    Args:
        conn: The SSH connection instance.
        proxy: The proxy to apply if available.
    """
    if not proxy or not proxy.http:
        return
    await wait_for(partial(_snap_ready, conn))

    command = "sudo snap install aproxy --edge"
    logger.info("Running command: %s", command)
    result: Result = conn.run(command)
    assert result.ok, "Failed to install aproxy"

    proxy_str = proxy.http.replace("http://", "").replace("https://", "")
    command = f"sudo snap set aproxy proxy={proxy_str}"
    logger.info("Running command: %s", command)
    result = conn.run(command)
    assert result.ok, "Failed to setup aproxy"

    # ignore line too long since it is better read without line breaks
    command = """/usr/bin/sudo nft -f - << EOF
define default-ip = $(ip route get $(ip route show 0.0.0.0/0 | grep -oP 'via \\K\\S+') | grep -oP 'src \\K\\S+')
define private-ips = { 10.0.0.0/8, 127.0.0.1/8, 172.16.0.0/12, 192.168.0.0/16 }
table ip aproxy
flush table ip aproxy
table ip aproxy {
    chain prerouting {
            type nat hook prerouting priority dstnat; policy accept;
            ip daddr != \\$private-ips tcp dport { 80, 443 } counter dnat to \\$default-ip:8443
    }

    chain output {
            type nat hook output priority -100; policy accept;
            ip daddr != \\$private-ips tcp dport { 80, 443 } counter dnat to \\$default-ip:8443
    }
}
EOF"""  # noqa: E501
    logger.info("Running command: %s", command)
    result = conn.run(command)
    assert result.ok, "Failed to configure iptable rules"


def _snap_ready(conn: SSHConnection) -> bool:
    """Checks whether snapd is ready.

    Args:
        conn: The SSH connection instance.

    Returns:
        Whether snapd is ready.
    """
    command = "sudo systemctl is-active snapd.seeded.service"
    logger.info("Running command: %s", command)
    try:
        result: Result = conn.run(command)
        return result.ok
    except UnexpectedExit:
        return False
