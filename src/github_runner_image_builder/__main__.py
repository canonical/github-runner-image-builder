# Copyright 2024 Canonical Ltd.
# See LICENSE file for licensing details.

"""Main entrypoint for github-runner-image-builder."""

import sys
from github_runner_image_builder.cli import main


if __name__ == "__main__":
    sys.exit(main())
