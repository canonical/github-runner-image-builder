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

## <kbd>class</kbd> `Snap`
The snap to install. 



**Attributes:**
 
 - <b>`name`</b>:  The snap to install. 
 - <b>`channel`</b>:  The snap channel to install from. 
 - <b>`classic`</b>:  Whether the snap should be installed in --classic mode. 

<a href="../<string>"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(name: str, channel: str, classic: bool) → None
```








---

<a href="../src/github_runner_image_builder/config.py#L154"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>classmethod</kbd> `from_str`

```python
from_str(value: str) → Snap
```

Parse snap datastruct from string. 



**Args:**
 
 - <b>`value`</b>:  The string value to parse. 



**Raises:**
 
 - <b>`ValueError`</b>:  if there was an error parsing the snap configuration from input string. 



**Returns:**
 The parsed snap dataclass. 

---

<a href="../src/github_runner_image_builder/config.py#L182"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `to_string`

```python
to_string() → str
```

Format to cloud-init installable string. 



**Returns:**
 
 - <b>`The <name>`</b>: <channel>:<classic> formatted string for cloud-init script. 


---

<a href="../src/github_runner_image_builder/config.py#L191"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `ImageConfig`
The build image configuration values. 



**Attributes:**
 
 - <b>`arch`</b>:  The architecture of the target image. 
 - <b>`base`</b>:  The ubuntu base OS of the image. 
 - <b>`runner_version`</b>:  The GitHub runner version to install on the VM. Defaults to latest. 
 - <b>`name`</b>:  The image name to upload on OpenStack. 
 - <b>`snaps`</b>:  list of snaps to install. 

<a href="../<string>"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

### <kbd>method</kbd> `__init__`

```python
__init__(
    arch: Arch,
    base: BaseImage,
    runner_version: str,
    name: str,
    snaps: list[Snap]
) → None
```









