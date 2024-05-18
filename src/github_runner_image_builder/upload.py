# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Module for uploading images to shareable storage."""

import dataclasses
import logging
from pathlib import Path
from typing import Any, cast

import openstack
import openstack.connection
import openstack.exceptions
from openstack.image.v2.image import Image

from github_runner_image_builder.config import Arch, BaseImage
from github_runner_image_builder.errors import (
    OpenstackConnectionError,
    UnauthorizedError,
    UploadImageError,
)

logger = logging.getLogger(__name__)


@dataclasses.dataclass
class UploadImageConfig:
    """Configuration values for creating image.

    Attributes:
        arch: The architecture the image was built for.
        base: The ubuntu OS base the image was created with.
        image_name: The image name to upload as.
        num_revisions: The number of revisions to keep for an image.
        src_path: The path to image to upload.
    """

    arch: Arch
    base: BaseImage
    image_name: str
    num_revisions: int
    src_path: Path


class OpenstackManager:
    """Class to manage interactions with Openstack."""

    def __init__(self, cloud_name: str):
        """Initialize the openstack manager class.

        Args:
            cloud_name: The Openstack cloud to use.

        Raises:
            UnauthorizedError: If an invalid openstack credentials was given.
        """
        try:
            with openstack.connect(cloud=cloud_name) as conn:
                conn.authorize()
        # pylint thinks this isn't an exception, but does inherit from Exception class.
        except openstack.exceptions.HttpException as exc:  # pylint: disable=bad-exception-cause
            raise UnauthorizedError("Unauthorized credentials.") from exc

        self.conn = openstack.connect(cloud_name)

    def __enter__(self) -> "OpenstackManager":
        """Dunder method placeholder for context management.

        Returns:
            Self with established connection.
        """
        return self

    def __exit__(self, *_args: Any, **_kwargs: Any) -> None:
        """Dunder method to close initialized connection to openstack."""
        self.conn.close()

    def _get_images_by_latest(self, image_name: str) -> list[Image]:
        """Fetch the images sorted by latest.

        Args:
            image_name: The image name to search for.

        Raises:
            OpenstackConnectionError: if there was an error fetching the images.

        Returns:
            The images sorted in latest first order.
        """
        try:
            images = cast(list[Image], self.conn.search_images(image_name))
        except openstack.exceptions.OpenStackCloudException as exc:
            raise OpenstackConnectionError from exc

        return sorted(images, key=lambda image: image.created_at, reverse=True)

    def _prune_old_images(self, image_name: str, num_revisions: int) -> None:
        """Remove old images outside of number of revisions to keep.

        Args:
            image_name: The image name to search for.
            num_revisions: The number of revisions to keep.
        """
        images = self._get_images_by_latest(image_name=image_name)
        images_to_prune = images[num_revisions:]
        for image in images_to_prune:
            try:
                if not self.conn.delete_image(image.id, wait=True):
                    logger.error("Failed to delete old image, %s", image.id)
            except openstack.exceptions.OpenStackCloudException as exc:
                logger.error("Failed to prune old image, %s", exc)
                continue

    def upload_image(self, config: UploadImageConfig) -> str:
        """Upload image to openstack glance.

        Args:
            config: Configuration values for creating image.

        Raises:
            UploadImageError: If there was an error uploading the image to Openstack Glance.

        Returns:
            The created image ID.
        """
        try:
            self._prune_old_images(
                image_name=config.image_name, num_revisions=config.num_revisions - 1
            )
            image: Image = self.conn.create_image(
                name=config.image_name,
                filename=str(config.src_path),
                allow_duplicates=True,
                wait=True,
            )
            return image.id
        except openstack.exceptions.OpenStackCloudException as exc:
            raise UploadImageError from exc
