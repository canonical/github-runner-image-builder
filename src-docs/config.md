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

<a href="../src/github_runner_image_builder/config.py#L45"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

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

<a href="../src/github_runner_image_builder/config.py#L16"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `Arch`
Supported system architectures. 



**Attributes:**
 
 - <b>`ARM64`</b>:  Represents an ARM64 system architecture. 
 - <b>`X64`</b>:  Represents an X64/AMD64 system architecture. 





---

<a href="../src/github_runner_image_builder/config.py#L64"><img align="right" style="float:right;" src="https://img.shields.io/badge/-source-cccccc?style=flat-square"></a>

## <kbd>class</kbd> `BaseImage`
The ubuntu OS base image to build and deploy runners on. 



**Attributes:**
 
 - <b>`JAMMY`</b>:  The jammy ubuntu LTS image. 
 - <b>`NOBLE`</b>:  The noble ubuntu LTS image. 





