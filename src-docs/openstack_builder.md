<!-- markdownlint-disable -->

<a href="../src/github_runner_image_builder/openstack_builder.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `openstack_builder`
Module for interacting with external openstack VM image builder. 

**Global Variables**
---------------
- **IMAGE_DEFAULT_APT_PACKAGES**
- **CLOUD_YAML_PATHS**
- **BUILDER_SSH_KEY_NAME**
- **SHARED_SECURITY_GROUP_NAME**
- **IMAGE_SNAPSHOT_NAME**
- **CREATE_SERVER_TIMEOUT**
- **MIN_CPU**
- **MIN_RAM**
- **MIN_DISK**

---

<a href="../src/github_runner_image_builder/openstack_builder.py#L58"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `determine_cloud`

```python
determine_cloud(cloud_name: str | None = None) → str
```

Automatically determine cloud to use from clouds.yaml by selecting the first cloud. 



**Args:**
 
 - <b>`cloud_name`</b>:  str 



**Raises:**
 
 - <b>`CloudsYAMLError`</b>:  if clouds.yaml was not found. 



**Returns:**
 The cloud name to use. 


---

<a href="../src/github_runner_image_builder/openstack_builder.py#L91"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `initialize`

```python
initialize(arch: Arch, cloud_name: str) → None
```

Initialize the OpenStack external image builder. 

Upload ubuntu base images to openstack to use as builder base. This is a separate method to mitigate race conditions from happening during parallel runs (multiprocess) of the image builder, by creating shared resources beforehand. 



**Args:**
 
 - <b>`arch`</b>:  The architecture of the image to seed. 
 - <b>`cloud_name`</b>:  The cloud to use from the clouds.yaml file. 


---

<a href="../src/github_runner_image_builder/openstack_builder.py#L211"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `run`

```python
run(
    arch: Arch,
    base: BaseImage,
    cloud_config: CloudConfig,
    runner_version: str,
    keep_revisions: int
) → str
```

Run external OpenStack builder instance and create a snapshot. 



**Args:**
 
 - <b>`arch`</b>:  The architecture of the image to seed. 
 - <b>`base`</b>:  The Ubuntu base to use as builder VM base. 
 - <b>`cloud_config`</b>:  The OpenStack cloud configuration values for builder VM. 
 - <b>`runner_version`</b>:  The GitHub runner version to install on the VM. Defaults to latest. 
 - <b>`keep_revisions`</b>:  The number of image to keep for snapshot before deletion. 



**Returns:**
 The Openstack snapshot image ID. 


---

<a href="../src/github_runner_image_builder/openstack_builder.py#L192"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `CloudConfig`
The OpenStack cloud configuration values. 



**Attributes:**
 
 - <b>`cloud_name`</b>:  The OpenStack cloud name to use. 
 - <b>`flavor`</b>:  The OpenStack flavor to launch builder VMs on. 
 - <b>`network`</b>:  The OpenStack network to launch the builder VMs on. 
 - <b>`proxy`</b>:  The proxy to enable on builder VMs. 
 - <b>`upload_cloud_name`</b>:  The OpenStack cloud name to upload the snapshot to. (Default same cloud) 

<a href="../<string>"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(
    cloud_name: str,
    flavor: str,
    network: str,
    proxy: str,
    upload_cloud_name: str | None
) → None
```









