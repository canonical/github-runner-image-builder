# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Fixtures for github runner image builder integration tests."""
import string
from pathlib import Path
from typing import Optional

import openstack
import pytest
import yaml
from openstack.connection import Connection
from openstack.image.v2.image import Image

from github_runner_image_builder.cli import main


@pytest.fixture(scope="module", name="image")
def image_fixture(pytestconfig: pytest.Config) -> str:
    """The ubuntu image base to build from."""
    image = pytestconfig.getoption("--image")
    assert image, "Please specify the --image command line option"
    return image


@pytest.fixture(scope="module", name="openstack_clouds_yaml")
def openstack_clouds_yaml_fixture(pytestconfig: pytest.Config) -> str:
    """Configured clouds-yaml setting."""
    clouds_yaml = pytestconfig.getoption("--openstack-clouds-yaml")
    return clouds_yaml


@pytest.fixture(scope="module", name="private_endpoint_clouds_yaml")
def private_endpoint_clouds_yaml_fixture(pytestconfig: pytest.Config) -> Optional[str]:
    """The openstack private endpoint clouds yaml."""
    auth_url = pytestconfig.getoption("--openstack-auth-url")
    password = pytestconfig.getoption("--openstack-password")
    project_domain_name = pytestconfig.getoption("--openstack-project-domain-name")
    project_name = pytestconfig.getoption("--openstack-project-name")
    user_domain_name = pytestconfig.getoption("--openstack-user-domain-name")
    user_name = pytestconfig.getoption("--openstack-user-name")
    region_name = pytestconfig.getoption("--openstack-region-name")
    if any(
        not val
        for val in (
            auth_url,
            password,
            project_domain_name,
            project_name,
            user_domain_name,
            user_name,
            region_name,
        )
    ):
        return None
    return string.Template(
        Path("tests/integration/data/clouds.yaml.tmpl").read_text(encoding="utf-8")
    ).substitute(
        {
            "auth_url": auth_url,
            "password": password,
            "project_domain_name": project_domain_name,
            "project_name": project_name,
            "user_domain_name": user_domain_name,
            "username": user_name,
            "region_name": region_name,
        }
    )


@pytest.fixture(scope="module", name="clouds_yaml_contents")
def clouds_yaml_contents_fixture(
    openstack_clouds_yaml: Optional[str], private_endpoint_clouds_yaml: Optional[str]
):
    """The Openstack clouds yaml or private endpoint cloud yaml contents."""
    clouds_yaml_contents = openstack_clouds_yaml or private_endpoint_clouds_yaml
    assert clouds_yaml_contents, (
        "Please specify --openstack-clouds-yaml or all of private endpoint arguments "
        "(--openstack-auth-url, --openstack-password, --openstack-project-domain-name, "
        "--openstack-project-name, --openstack-user-domain-name, --openstack-user-name, "
        "--openstack-region-name)"
    )
    return clouds_yaml_contents


@pytest.fixture(scope="module", name="cloud_name")
def cloud_name_fixture(clouds_yaml_contents: str) -> str:
    """The cloud to use from cloud config."""
    clouds_yaml = yaml.safe_load(clouds_yaml_contents)
    clouds_yaml_path = Path("clouds.yaml")
    clouds_yaml_path.write_text(data=clouds_yaml_contents, encoding="utf-8")
    first_cloud = next(iter(clouds_yaml["clouds"].keys()))
    return first_cloud


@pytest.fixture(scope="module", name="openstack_connection")
def openstack_connection_fixture(cloud_name: str) -> Connection:
    """The openstack connection instance."""
    return openstack.connect(cloud_name)


@pytest.fixture(scope="module", name="callback_result_path")
def callback_result_path_fixture() -> Path:
    """The file created when the callback script is run."""
    return Path("callback_complete")


@pytest.fixture(scope="module", name="callback_script")
def callback_script_fixture(callback_result_path: Path) -> Path:
    """The callback script to use with the image builder."""
    callback_script = Path("callback")
    callback_script.write_text(
        f"""#!/bin/bash
IMAGE_ID=$1
echo $IMAGE_ID | tee {callback_result_path}
""",
        encoding="utf-8",
    )
    callback_script.chmod(0o775)
    return callback_script


@pytest.fixture(scope="module", name="openstack_image_name")
def openstack_image_name_fixture() -> str:
    """The image name to upload to openstack."""
    return "image-builder-test-image"


@pytest.fixture(scope="module", name="cli_run")
def cli_run_fixture(
    image: str,
    cloud_name: str,
    callback_script: Path,
    openstack_connection: Connection,
    openstack_image_name: str,
):
    """A CLI run."""
    main(["init"])
    main(
        [
            "run",
            cloud_name,
            openstack_image_name,
            "--base-image",
            image,
            "--keep-revisions",
            "2",
            "--callback-script",
            str(callback_script),
        ]
    )

    yield

    openstack_image: Image
    for openstack_image in openstack_connection.search_images(openstack_image_name):
        openstack_connection.delete_image(openstack_image.id)
