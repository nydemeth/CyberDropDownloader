# `enabled`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Send unsupported URLs to JDownloader. All other JDownloader settings are ignored if this is `false`

```yaml
jdownloader:
  enabled: false
```

# `deprecated_api`

| Type                | Default |
| ------------------- | ------- |
| `HttpURL` or `None` | `null`  |

HTTP URL of a local JDownloader instance to connect to via their deprecated API (insecure, default port=3128)

The 'Deprecated API' options need to be enabled on JDownloader instance (`Settings` -> `Advanced Options`)

```yaml
jdownloader:
  deprecated_api: null
```

# `autostart`

| Type   | Default |
| ------ | ------- |
| `bool` | `false` |

Request to JDownloader start downloads as immediately.

If disabled, downloads will be added to the LinkGrabber queue and you have to manually start them on JDDownloader itself

```yaml
jdownloader:
  autostart: false
```

# `download_folder`

| Type             | Default |
| ---------------- | ------- |
| `Path` or `null` | `null`  |

The `download_folder` jdownloader will use. A `null` value (the default) will use the same value as CDL's download folder (`--download-folder`).

Use this option as path mapping when JDownloader is running on a different host / docker.

```yaml
jdownloader:
  download_folder: null
```

# `whitelist`

| Type                | Default |
| ------------------- | ------- |
| `list[NonEmptyStr]` | `[]`    |

List of domain names. An unsupported URL will only be sent to JDownloader if its host is found on the list.

An empty whitelist will send _any_ unsupported URL to jdownloader.

```yaml
jdownloader:
  whitelist: []
```
