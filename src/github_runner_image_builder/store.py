# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module for uploading images to shareable storage."""

import logging
from pathlib import Path
from typing import cast

import openstack
import openstack.connection
import openstack.exceptions
from openstack.compute.v2.server import Server
from openstack.image.v2.image import Image

from github_runner_image_builder.config import Arch
from github_runner_image_builder.errors import OpenstackError, UploadImageError

logger = logging.getLogger(__name__)


def create_snapshot(
    arch: Arch, cloud_name: str, image_name: str, server: Server, keep_revisions: int
) -> Image:
    """Upload image to openstack glance.

    Args:
        arch: The image architecture.
        cloud_name: The Openstack cloud to use from clouds.yaml.
        image_name: The image name to upload as.
        server: The running OpenStack server to snapshot.
        keep_revisions: The number of revisions to keep for an image.

    Raises:
        UploadImageError: If there was an error uploading the image to Openstack Glance.

    Returns:
        The created image.
    """
    with openstack.connect(cloud=cloud_name) as connection:
        try:
            image: Image = connection.create_image_snapshot(
                name=image_name,
                server=server.id,
                wait=True,
                allow_duplicates=True,
                properties={"architecture": arch.to_openstack()},
            )
            _prune_old_images(
                connection=connection, image_name=image_name, num_revisions=keep_revisions
            )
            return image
        except openstack.exceptions.OpenStackCloudException as exc:
            raise UploadImageError from exc


def upload_image(
    arch: Arch, cloud_name: str, image_name: str, image_path: Path, keep_revisions: int
) -> str:
    """Upload image to openstack glance.

    Args:
        arch: The image architecture.
        cloud_name: The Openstack cloud to use from clouds.yaml.
        image_name: The image name to upload as.
        image_path: The path to image to upload.
        keep_revisions: The number of revisions to keep for an image.

    Raises:
        UploadImageError: If there was an error uploading the image to Openstack Glance.

    Returns:
        The created image ID.
    """
    with openstack.connect(cloud=cloud_name) as connection:
        try:
            image: Image = connection.create_image(
                name=image_name,
                filename=str(image_path),
                allow_duplicates=True,
                properties={"architecture": arch.to_openstack()},
                wait=True,
            )
            _prune_old_images(
                connection=connection, image_name=image_name, num_revisions=keep_revisions
            )
            return image.id
        except openstack.exceptions.OpenStackCloudException as exc:
            raise UploadImageError from exc


def _prune_old_images(
    connection: openstack.connection.Connection, image_name: str, num_revisions: int
) -> None:
    """Remove old images outside of number of revisions to keep.

    Args:
        connection: The connected openstack cloud instance.
        image_name: The image name to search for.
        num_revisions: The number of revisions to keep.

    Raises:
        OpenstackError: if there was an error deleting the images.
    """
    images = _get_sorted_images_by_created_at(connection=connection, image_name=image_name)
    if not images:
        return
    images_to_prune = images[num_revisions:]
    for image in images_to_prune:
        try:
            if not connection.delete_image(image.id, wait=True):
                raise OpenstackError(f"Failed to delete image: {image.id}")
        except openstack.exceptions.OpenStackCloudException as exc:
            raise OpenstackError from exc


def get_latest_build_id(cloud_name: str, image_name: str) -> str:
    """Fetch the latest image id.

    Args:
        cloud_name: The Openstack cloud to use from clouds.yaml.
        image_name: The image name to search for.

    Returns:
        The image ID if exists, None otherwise.
    """
    with openstack.connect(cloud=cloud_name) as connection:
        images = _get_sorted_images_by_created_at(connection=connection, image_name=image_name)
        if not images:
            return ""
        return images[0].id


def _get_sorted_images_by_created_at(
    connection: openstack.connection.Connection, image_name: str
) -> list[Image]:
    """Fetch the images sorted by created_at date.

    Args:
        connection: The connected openstack cloud instance.
        image_name: The image name to search for.

    Raises:
        OpenstackError: if there was an error fetching the images.

    Returns:
        The images sorted by created_at date with latest first.
    """
    try:
        images = cast(list[Image], connection.search_images(image_name))
    except openstack.exceptions.OpenStackCloudException as exc:
        raise OpenstackError from exc

    return sorted(images, key=lambda image: image.created_at, reverse=True)
