# Build your first image

## What you'll do

- Install the CLI
- Initialise the builder
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

### Initialise the builder

- Run `github-runner-image-builder init` to install the dependencies for building the image.

### Run the image build

- Run 
```
CLOUD_NAME=<OpenStack cloud name from clouds.yaml>
IMAGE_NAME=<your desired image name>
github-runner-image-builder run <cloud-name> <image-name>
```
to start building the image.

### Verify that the image is available on OpenStack

- Run `openstack image list | grep <image-name>` to see the image in "active" status.

### Cleanup

- Run `openstack image delete <image-name>` after you're done following the tutorial to clean up.
