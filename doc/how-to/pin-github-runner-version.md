# How to pin GitHub runner version

In order to pin a specific GitHub [actions runner](https://github.com/actions/runner) version, add
the `--runner-version` argument with the desired version during the build.

```
github-runner-image-builder <cloud-name> <image-name> --runner-version=<runner-version>
```

Find out what versions of runner versions are available 
[here](https://github.com/actions/runner/releases).
