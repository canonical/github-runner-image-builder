# External builder

The required snaps Juju, Microk8s and LXD cannot be installed within the chroot environment.
Furthermore, to increase the efficiency of the workflow startup times, Juju and Microk8s requires
bootstrapping, which can be done during runtime of the image.

Hence, external builder via OpenStack VMs have been introduced with the snapshot method to
work around the limitations of snaps.
