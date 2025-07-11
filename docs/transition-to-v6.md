---
description: This is the walk through for transitioning from V4, V5 or V6 to v7
icon: arrow-up-to-bracket
layout:
  title:
    visible: true
  description:
    visible: true
  tableOfContents:
    visible: true
  outline:
    visible: false
  pagination:
    visible: true
---

# Transition from V4, V5 or V6 to V7

{% hint style="danger" %}
V6 introduced some breaking changes: Using a more strict config validation logic, replacing `md5` with `xxh128` as the default hashing algorithm, using a new database schema, among others.

It's recommended to do a manual backup of your current `AppData` folder. You won't be able to rollback to a previous version after the transfer is completed.

You can learn more about these changes on the [release announcement](https://github.com/jbsparrow/CyberDropDownloader/blob/master/CHANGELOG.md#600---2024-12-23)
{% endhint %}

{% hint style="warning" %}
Even after a successful configuration migration, the program may not start if some values from the previous version’s config are no longer valid. Please follow the on-screen instructions to resolve the issue.

You can use the [Config Options page](reference/configuration-options/README.md) as reference for valid config values
{% endhint %}

## Import V5 or V6 config into V7

Good news! If you have a v5 config, CDL can import it. The program will automatically detect the config in the current folder and handle the migration process for you.

All you have to do is replace your old start script (for Windows, that's the `.bat` file) with the v7 start script. If CDL does not update automatically to v7, delete the `.venv` folder inside CDL's folder and run the start script again.

Please note that after the migration is complete, you may still need to manually adjust some values in the config.

If you are migrating from v5 and the migration fails, the database will be rolled back to its previous state. An automatic backup is also made before the migration begins. However, keep in mind that the backup only includes the database, not the config files.

## Import V4 config

{% hint style="warning" %}
V4 import is no longer supported. Last version with v4 support was `6.5.0`. To upgrade to the latest version, you need to perform a sequential upgrade. First, update CDL to `6.5.0`, import your v4 files, and then update to the latest version.

You can install `6.5.0` with pip by running:

```shell
pip install cyberdrop-dl-patched==6.5.0
```

{% endhint %}

Built into Cyberdrop-DL is a tool that allows you to import both your configs and your history DB from a v4 version of Cyberdrop-DL. You can use it by selecting "Import V4 Items".

### Import Your V4 Configs</a>

The config files will be located in the folder that you were previously running Cyberdrop-DL in. Start CDL, choose the option `Import v4 config` and follow the on screen instructions

{% hint style="info" %}
If you weren't using the config previously, you don't need to import it.

However, if you were primarily using CLI Arguments with V4, some of the arguments has been replaced.
{% endhint %}

If you don't end up using the import feature, make sure you also change the default config in the program if that's something you want to do.

### Import Your V4 Database</a>

For a lot of people, the `download_history.sqlite` file will be in the same folder as your start file (or wherever you are running Cyberdrop-DL).

If it's not there, you can find it here:

Windows:
```shell
C:\Users\<USER>\AppData\Local\Cyberdrop-DL\Cyberdrop-DL\download_history.sqlite
```

macOS:
```shell
/Library/Application Support/Cyberdrop-DL/Cyberdrop-DL/download_history.sqlite
```

Linux:
```shell
/home/<USER>/.local/share/Cyberdrop-DL/Cyberdrop-DL/download_history.sqlite
```

To import it, start CDL, choose the option `Import v4 database` and follow the on screen instructions

{% hint style="info" %}
The old `download_history.sqlite` file is no longer used by Cyberdrop-DL. After you import it, you can delete the old one.

If you don't want to import previous download history, you can just delete it.
{% endhint %}
