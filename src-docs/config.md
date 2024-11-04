<!-- markdownlint-disable -->

<a href="../src/github_runner_image_builder/config.py#L0"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

# <kbd>module</kbd> `config`
Module containing configurations. 

**Global Variables**
---------------
- **ARCHITECTURES_ARM64**
- **ARCHITECTURES_X86**
- **LTS_IMAGE_VERSION_TAG_MAP**
- **BASE_CHOICES**
- **IMAGE_DEFAULT_APT_PACKAGES**
- **LOG_LEVELS**

---

<a href="../src/github_runner_image_builder/config.py#L46"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>function</kbd> `get_supported_arch`

```python
get_supported_arch() → <enum 'Arch'>
```

Get current machine architecture. 



**Raises:**
 
 - <b>`UnsupportedArchitectureError`</b>:  if the current architecture is unsupported. 



**Returns:**
 
 - <b>`Arch`</b>:  Current machine architecture. 


---

<a href="../src/github_runner_image_builder/config.py#L17"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `Arch`
Supported system architectures. 



**Attributes:**
 
 - <b>`ARM64`</b>:  Represents an ARM64 system architecture. 
 - <b>`X64`</b>:  Represents an X64/AMD64 system architecture. 





---

<a href="../src/github_runner_image_builder/config.py#L65"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `BaseImage`
The ubuntu OS base image to build and deploy runners on. 



**Attributes:**
 
 - <b>`JAMMY`</b>:  The jammy ubuntu LTS image. 
 - <b>`NOBLE`</b>:  The noble ubuntu LTS image. 





---

<a href="../src/github_runner_image_builder/config.py#L140"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `ImageConfig`
The build image configuration values. 



**Attributes:**
 
 - <b>`arch`</b>:  The architecture of the target image. 
 - <b>`base`</b>:  The ubuntu base OS of the image. 
 - <b>`microk8s`</b>:  The MicroK8s snap channel to install. 
 - <b>`juju`</b>:  The Juju channel to install and bootstrap. 
 - <b>`runner_version`</b>:  The GitHub runner version to install on the VM. Defaults to latest. 
 - <b>`name`</b>:  The image name to upload on OpenStack. 

<a href="../<string>"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(
    arch: Arch,
    base: BaseImage,
    microk8s: str,
    juju: str,
    runner_version: str,
    name: str
) → None
```









