# Sublime Rsync SSH

Keep remote directories in sync with local project folders.

## Description

This plugin will let you sync your project folders to one or more remote servers using rsync and ssh.

## Terminology

- A `remote` is a local project folder configured for sync.
- A `destination` is a path on specific server as a specific user.
- A `remote` can have one or more `destinations`

## Features

- Edit locally, work remotely
- Upload one or more project folders to one or more remote servers.
- Each project folder can have multiple remotes, and each remote can have multiple destinations
- Sync whole project or just a single remote or destination
- Single file save only syncs the file being saved.
- Auto generate initial rsync-ssh configuration for all folders in a project.
- Exclude files, either for the whole project, a single fold or just a single remote.
- Selective sync: Only sync part of a project folder to remote server.
- Hooks for running a command on the remote host before and after sync.
- Enable/Disable remotes.
- Parse arguments to rsync for advanced usage (or features not yet included)
- Detailed console output so you know what gets synced where.

## Requirements

- You must have both `ssh` and `rsync` installed, both locally and on the remote server.
- You must have a ssh-key that allows you to perform login without password. If you have a password on your key, then you must use `ssh-agent`. On OS X you'll need to add your keys to the Keychain by using `ssh-add -K`, once this is done OS X will use `ssh-agent` to query the Keychain for your password.
- On the remote server, you must add your ssh public key to `~/.ssh/authorized_keys`.

For more info on creating and using ssh keys please see this [nice guide](https://help.github.com/articles/set-up-git#password-caching).

## Usage

Note you can see everything this plugin does by viewing its output on the console.

### Initialize configuration

First create a Sublime Project, you do this by adding one or more folders and then saving your project.

Then you go to the `Project` menu and select `Rsync SSH` and then `Initialize Settings`, this will add the `rsync_ssh` block to `settings` with some reasonable defaults and then open the preferences for you to edit.

Be aware that the `--delete` option will destroy the directory you speficy in `remote_path` - as a courtesy I've added `--dry-run` so you can test your config before running `rsync` for real.

### Example `.sublime-project` file

Note that the `.sublime-project` is a JSON file, and as such comments are not supported, fortunately for us Sublime Text uses a a rather lax parser that supports `//` comments.
The comments below have just been added to document the individual sections .

When you initialize your project via `Initialize Settings` the plugin will add the `rsync_ssh` config to your project file.

```yaml
{
    "folders":
    [
        {
            "follow_symlinks": true,
            "path": "my-project-folder"
        }
    ],
    "settings":
    {
        // This is the block the plugin adds to your project file
        "rsync_ssh":
        {
            // To use non-standard ssh specify the path here
            "ssh_binary": "/usr/local/bin/ssh",

            // You may also want to specify rsync executable path, for instance, if using MSYS under Windows
            "rsync_binary": "/usr/local/bin/rsync",

            // To disable sync on save set 'sync_on_save' to false
            "sync_on_save": true,

            // Rsync options
            "options":
            [
                "--dry-run",
                "--delete",
                // Override how we handle permissions, useful for platforms that does not support Unix permissions.
                // Here we tell rsync to use the umask on the destination to set the permissions
                "--no-perms", "--chmod=ugo=rwX"
            ],
            // Stuff we do not want rsync to copy
            "excludes":
            [
                ".git*",
                "_build",
                "blib",
                "Build"
            ],
            // Servers we want to sync to
            "remotes":
            {
                // Each folder from the project will be added here
                "my-project-folder":
                [
                    {
                        // You can disable any destination by setting this value to 0
                        "enabled": 1,
                        // Stuff we do not want rsync to copy, but just for this destination
                        "excludes":
                        [
                        ],
                        // ssh options
                        "remote_host": "my-server.my-domain.tld",
                        "remote_path": "/home/you/Projects/my-project",
                        "remote_port": 22,
                        "remote_user": "you",
                        // Run commands before and after rsync
                        "remote_pre_command": "",
                        "remote_post_command": ""
                    }
                ],
                // Syncing a single subfolder is also supported
                "my-project-folder/subfolder":
                [
                    {
                        // You can disable any destination by setting this value to 0
                        "enabled": 0,
                        // Stuff we do not want rsync to copy, but just for this destination
                        "excludes":
                        [
                        ],
                        // ssh options
                        "remote_host": "my-server.my-domain.tld",
                        "remote_path": "/home/you/Projects/my-subfolder-target",
                        "remote_port": 22,
                        "remote_user": "you",
                        // Run commands before and after rsync
                        "remote_pre_command": "",
                        "remote_post_command": ""
                    }
                ]
            }
        }
    }
}
```

### Sync single file

Just save the file normally, as this will trigger a save event which makes this plugin sync the file to all enabled remotes.

### Sync specific remote or destination

Press ⌘⇧F11 to select a specific remote or destination to sync. When selecting a specific destination the `enabled` flag is overridden and the folder will always be synced.
If you select a remote, and then select the `All` destination, then the `enabled` flag will be respected.
If you select a remote with just one destination sync will started immediately and the `enabled` flag will be overridden.

### Sync full project

Press ⌘⇧F12 to sync all folders to all enabled remotes. - Note you must do this at least once in order to create the project folder on the remote servers.

## Installation

You install this plugin either by cloning this project directly, or by installing it via the excellent [Package Control](http://packagecontrol.io) plugin. Press ⌘⇧P and type `Package Control: Install Package` and select it, then type the package name [rsync-ssh](https://packagecontrol.io/packages/Rsync%20SSH) and select it.

To use this plugin on Windows you must install [Cygwin](https://www.cygwin.com) first.

## F.A.Q.

### When I try to sync, nothing happens

You probably forgot to remove `--dry-run` from the rsync options in the project configuration file.

### I'm on Windows, how do I get sane permissions on the destination

As Windows doesn't have native support for [Unix permissions](https://en.wikipedia.org/wiki/File_system_permissions#Traditional_Unix_permissions), you can't rely on the default sync mode of "preserve permissions".
Instead you can turn off the persission sync with `--no-perms` and then use `--chmod=ugo=rwX` to make `rsync` use the umask on the destination to determine which permissions a file should have.
When you initialize the `rsync-ssh` configuration this will be automatically added to the configuration as shown in the example above.

## TODO

- Rename `remotes` to `folders` (Calling them remotes is kinda silly).

## License

&copy; 2013-2015 David Olrik <[david@olrik.dk](mailto:david@olrik.dk)>.

This is free software. It is licensed under the [Creative Commons Attribution-ShareAlike 3.0 Unported License](http://creativecommons.org/licenses/by-sa/3.0/). Feel free to use this package in your own work. However, if you modify and/or redistribute it, please attribute me in some way, and distribute your work under this or a similar license.

