# Sublime Rsync SSH

Keep remote directories in sync with local projects.

## Description

This plugin will let you sync your project folders to one or more remote servers using rsync and ssh.

## Features

- Create default configuration for all folders in project.
- Upload current file to one or more remote servers.
- Upload one or more project folders to one or more remote server.

## Usage

Note you can see everything this plugin does by viewing its output on the console.

### Initialize configuration

Go to the `Project` menu and select `Rsync SSH` and then `Initialize Settings`, this will add the `rsync_ssh` block to `settings` with some reasonable defaults and then open the preferences for you to edit.

Be aware that the `--delete` option will destroy the directoy you speficy in `remote_path` - as a courtesy I've added `--dry-run` so you can test your config before running `rsync` for real.

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
        # This is the block the plugin adds to your project file
        "rsync_ssh":
        {
            # Rsync options
            "options":
            [
                "--dry-run",
                "--delete"
            ],
            # Stuff we don't want rsync to copy
            "excludes":
            [
                ".git*",
                "_build",
                "blib",
                "Build"
            ],
            # Servers we want to sync to
            "remotes":
            {
                # Each folder from the project will be added here
                "my-project-folder":
                [
                    {
                        # You can disable any remote by setting this value to 0
                        "enabled": 1,
                        # Stuff we don't want rsync to copy, but just for this remote
                        "excludes":
                        [
                        ],
                        # ssh options
                        "remote_host": "my-server.my-domain.tld",
                        "remote_path": "/home/you/Projects/my-project",
                        "remote_port": 22,
                        "remote_user": "you"
                    }
                ]
            }
        }
    }
}
```

### Sync single file

Saving a file normally will trigger a save event which will make this plugin sync it to all enabled remotes.

### Sync whole project

Press ⇧⌘F12 to sync all folders to all enabled remotes. - Note you must do this at least once in order to create the project folder on the remote servers.

## Install

You install this plugin either by cloning this project directly, or by installing it via the excellent [Package Control](https://sublime.wbond.net) plugin.

To get notifications upon successfull saves, please install [Terminal Notifications](https://github.com/davidolrik/sublime-terminal-notifier).

## License

&copy; 2013 David Olrik <david@olrik.dk>.

This is free software. It is licensed under the [Creative Commons Attribution-ShareAlike 3.0 Unported License](http://creativecommons.org/licenses/by-sa/3.0/). Feel free to use this package in your own work. However, if you modify and/or redistribute it, please attribute me in some way, and distribute your work under this or a similar license.

