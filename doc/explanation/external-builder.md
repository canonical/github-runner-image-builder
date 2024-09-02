# External builder

In order to pre-bootstrap LXD, Microk8s snaps to Juju, external VMs are spanwed and then run with
cloud-init script that installs the required components. Then, it is snapshot to work around
the limitation of booting up a fresh image with snaps with state perseverance.
