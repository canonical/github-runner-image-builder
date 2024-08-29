# How to use external builder vm

This guide will cover how to use an external OpenStack builder VM to build and snapshot images.

### Command

Run the following command to create a snapshot image of a VM launched by the 
github-runner-image-builder.

To find out what flavor is available, run `openstack list flavor`.
To find out what network is available, run `openstack list network`.

```
FLAVOR=<available openstack flavor>
NETWORK=<openstack network for builder VMs>
github-runner-image-builder --experimental-external True --flavor $FLAVOR --network $NETWORK
```
