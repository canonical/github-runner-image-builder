<!-- markdownlint-disable -->

<a href="../src/github_runner_image_builder/builder.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `builder`
Module for interacting with qemu image builder. 

**Global Variables**
---------------
- **IMAGE_DEFAULT_APT_PACKAGES**
- **APT_DEPENDENCIES**
- **APT_NONINTERACTIVE_ENV**
- **SNAP_GO**
- **RESIZE_AMOUNT**
- **APT_TIMER**
- **APT_SVC**
- **APT_UPGRADE_TIMER**
- **APT_UPGRAD_SVC**
- **UBUNTU_USER**
- **DOCKER_GROUP**
- **MICROK8S_GROUP**
- **LXD_GROUP**
- **SUDOERS_GROUP**
- **YQ_REPOSITORY_URL**
- **IMAGE_HWE_PKG_FORMAT**

---

<a href="../src/github_runner_image_builder/builder.py#L99"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `initialize`

```python
initialize() → None
```

Configure the host machine to build images. 


---

<a href="../src/github_runner_image_builder/builder.py#L163"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `run`

```python
run(arch: Arch, base_image: BaseImage, runner_version: str) → None
```

Build and save the image locally. 



**Args:**
 
 - <b>`arch`</b>:  The CPU architecture to build the image for. 
 - <b>`base_image`</b>:  The ubuntu image to use as build base. 
 - <b>`runner_version`</b>:  The GitHub runner version to embed. 



**Raises:**
 
 - <b>`BuildImageError`</b>:  If there was an error building the image. 


