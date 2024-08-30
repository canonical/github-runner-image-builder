# Quick start

## What you'll do

- Install the CLI
- Initialize the builder
- Run the image build

## Requirements

- [Pipx installed](https://pipx.pypa.io/stable/installation/)
- Apt packages gcc, pipx, python3-dev
  - `sudo apt-get install -y python3-dev gcc pipx`
- Working [OpenStack environment](https://microstack.run/docs/single-node)
- A clouds.yaml configuration with the OpenStack environment

## Steps

### Install the CLI

- Install the CLI
  - `pipx install git+https://github.com/canonical/github-runner-image-builder@stable`

### Initialize the builder

- `github-runner-image-builder init`

### Run the image build

- `github-runner-image-builder run <cloud-name> <image-name>`

### Verify that the image is available on OpenStack

- `openstack image list | grep <image-name>`
