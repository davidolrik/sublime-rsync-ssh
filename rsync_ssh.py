"""sublime-rsync-ssh: A Sublime Text 3 plugin for syncing local folders to remote servers."""
import os
import re
import shlex
import subprocess
import threading

import sublime
import sublime_plugin


def console_print(host, prefix, output):
    """Print message to console"""
    if host and prefix:
        host = host + "[" + prefix + "]: "
    elif host and not prefix:
        host = host + ": "
    elif not host and prefix:
        host = os.path.basename(prefix) + ": "

    output = "[rsync-ssh] " + host + output.replace("\n", "\n[rsync-ssh] " + host)
    print(output)


def console_show(window=sublime.active_window()):
    """Show console panel"""
    window.run_command("show_panel", {"panel": "console", "toggle": False})


def normalize_path(path):
    """Normalizes path to Unix format, converting back- to forward-slashes."""
    return path.strip().replace("\\", "/")


def current_user():
    """Get current username from the environment"""
    if "USER" in os.environ:
        return os.environ["USER"]
    elif "USERNAME" in os.environ:
        return os.environ["USERNAME"]
    else:
        return "username"


def check_output(*args, **kwargs):
    """Runs specified system command using subprocess.check_output()"""
    startupinfo = None
    if sublime.platform() == "windows":
        # Don't let console window pop-up on Windows.
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE

    return subprocess.check_output(*args, universal_newlines=True, startupinfo=startupinfo, **kwargs)


def rsync_ssh_settings(view=sublime.active_window().active_view()):
    """Get settings from the sublime project file"""
    project_data = view.window().project_data()

    # Not all windows have project data
    if project_data == None:
        return None

    settings = view.window().project_data().get("settings", {}).get("rsync_ssh")
    return settings


class RsyncSshInitSettingsCommand(sublime_plugin.TextCommand):
    """Sublime Command for creating the rsync_ssh block in the project settings file"""

    def run(self, edit, **args):  # pylint: disable=W0613
        """Generate settings for rsync-ssh"""
        # Load project configuration
        project_data = self.view.window().project_data()

        if project_data == None:
            console_print(
                "",
                "",
                "Unable to initialize settings, you must have a .sublime-project file.",
            )
            console_print("", "", "Please use 'Project -> Save Project As...' first.")
            console_show(self.view.window())
            return

        # If no rsync-ssh config exists, then create it
        if not project_data.get("settings", {}).get("rsync_ssh"):
            if not project_data.get("settings"):
                project_data["settings"] = {}
            project_data["settings"]["rsync_ssh"] = {}
            project_data["settings"]["rsync_ssh"]["sync_on_save"] = True
            project_data["settings"]["rsync_ssh"]["sync_all_on_save"] = False
            project_data["settings"]["rsync_ssh"]["ssh_args"] = []
            project_data["settings"]["rsync_ssh"]["excludes"] = [
                ".git*",
                "_build",
                "blib",
                "Build",
            ]
            project_data["settings"]["rsync_ssh"]["options"] = [
                "--dry-run",
                "--delete",
            ]
            # Add sane permission defaults when using windows (cygwin)
            if sublime.platform() == "windows":
                project_data["settings"]["rsync_ssh"]["options"].insert(0, "--chmod=ugo=rwX")
                project_data["settings"]["rsync_ssh"]["options"].insert(0, "--no-perms")

            project_data["settings"]["rsync_ssh"]["remotes"] = {}

            if project_data.get("folders") == None:
                console_print(
                    "",
                    "",
                    "Unable to initialize settings, you must have at least one folder in your .sublime-project file.",
                )
                console_print("", "", "Please use 'Add Folder to Project...' first.")
                console_show(self.view.window())
                return

            for folder in project_data.get("folders"):
                # Handle folder named '.'
                # User has added project file inside project folder, so we use the directory from the project file
                path = folder.get("path")
                if path == ".":
                    path = os.path.basename(os.path.dirname(self.view.window().project_file_name()))

                project_data["settings"]["rsync_ssh"]["remotes"][path] = [
                    {
                        "remote_host": "my-server.my-domain.tld",
                        "remote_path": "/home/" + current_user() + "/Projects/" + os.path.basename(path),
                        "remote_port": 22,
                        "remote_user": current_user(),
                        "remote_pre_command": "",
                        "remote_post_command": "",
                        "command": "rsync",
                        "enabled": 1,
                        "options": [],
                        "excludes": [],
                    }
                ]

            # Save configuration
            self.view.window().set_project_data(project_data)

        # We won't clobber an existing configuration
        else:
            console_print("", "", "rsync_ssh configuration already exists.")

        # Open configuration in new tab
        self.view.window().run_command("open_file", {"file": "${project}"})


class RsyncSshSyncSpecificRemoteCommand(sublime_plugin.TextCommand):
    """Start rsync for a specific remote"""

    remotes = []
    hosts = []

    def run(self, edit, **args):  # pylint: disable=W0613
        """Let user select which remote/destination to sync using the quick panel"""

        settings = rsync_ssh_settings(self.view)
        if not settings:
            console_print("", "", "Aborting! - rsync ssh is not configured!")
            return

        self.remotes = []
        for remote_key in settings.get("remotes").keys():
            for destination in settings.get("remotes").get(remote_key):
                # print(remote)
                if destination.get("enabled", True) == True:
                    if remote_key not in self.remotes:
                        self.remotes.append(remote_key)

        selected_remote = self.view.settings().get("rsync_ssh_sync_specific_remote", 0)
        self.view.window().show_quick_panel(
            self.remotes,
            self.sync_remote,
            sublime.MONOSPACE_FONT,
            selected_remote,
        )

    def sync_remote(self, choice):
        """Call rsync_ssh_command with the selected remote"""

        if choice >= 0:
            self.view.settings().set("rsync_ssh_sync_specific_remote", choice)

            destinations = rsync_ssh_settings(self.view).get("remotes").get(self.remotes[choice])

            # Remote has no destinations, which makes no sense
            if len(destinations) == 0:
                return
            # If remote only has one destination, we'll just initiate the sync
            elif len(destinations) == 1:
                # Start command thread to keep ui responsive
                self.view.run_command(
                    "rsync_ssh_sync",
                    {
                        "path_being_saved": self.remotes[choice],
                        "restrict_to_destinations": None,
                        "force_sync": True,
                    },
                )
            else:
                self.hosts = [["All", "Sync to all destinations"]]
                for destination in destinations:
                    d = []
                    remote_user = destination.get("remote_user")
                    if remote_user:
                        d.append(remote_user + "@")
                    d.append(destination.get("remote_host"))
                    d.append(":" + str(destination.get("remote_port")))
                    self.hosts.append(["".join(d), destination.get("remote_path")])

                selected_destination = self.view.settings().get("rsync_ssh_sync_specific_destination", 0)
                self.view.window().show_quick_panel(
                    self.hosts,
                    self.sync_destination,
                    sublime.MONOSPACE_FONT,
                    selected_destination,
                )

    def sync_destination(self, choice):
        """Sync single destination"""

        selected_remote = self.view.settings().get("rsync_ssh_sync_specific_remote", 0)

        # 0 == All destinations > 0 == specific destination
        if choice > -1:
            self.view.settings().set("rsync_ssh_sync_specific_destination", choice)

            # Build restriction string
            restrict_to_destinations = None if choice == 0 else self.hosts[choice][0] + ":" + self.hosts[choice][1]

            # Start command thread to keep ui responsive
            self.view.run_command(
                "rsync_ssh_sync",
                {
                    "path_being_saved": self.remotes[selected_remote],
                    "restrict_to_destinations": restrict_to_destinations,
                    # When selecting a specific destination we'll force the sync
                    "force_sync": False if choice == 0 else True,
                },
            )


class RsyncSshSaveCommand(sublime_plugin.EventListener):
    """Sublime Command for syncing a single file when user saves"""

    def on_post_save(self, view):
        """Invoked each time the user saves a file."""

        # Get settings
        settings = rsync_ssh_settings(view)

        # Don't do anything if rsync-ssh hasn't been configured
        if not settings:
            return
        # Don't sync single file if user has disabled sync on save
        elif settings.get("sync_on_save", True) == False:
            return

        # Don't sync git commit message buffer
        if os.path.basename(view.file_name()) == "COMMIT_EDITMSG":
            return

        # Return if we are already syncing the file
        if view.get_status("00000_rsync_ssh_status"):
            if settings.get("debug", False) == True:
                print("Sync already in progress")
            return

        # Block other instances of the same file from initiating sync (e.g. files open in more than one view)
        view.set_status("00000_rsync_ssh_status", "Sync initiated")

        options = {}
        if not settings.get("sync_all_on_save", False):
            options["path_being_saved"] = view.file_name()

        # Execute sync with the name of file being saved
        view.run_command("rsync_ssh_sync", options)


class RsyncSshSyncCommand(sublime_plugin.TextCommand):
    """Sublime Command for invoking the actual sync process"""

    def run(self, edit, **args):  # pylint: disable=W0613
        """Start thread with rsync to keep ui responsive"""

        # Get settings
        settings = rsync_ssh_settings(self.view)
        if not settings:
            console_print("", "", "Aborting! - rsync ssh is not configured!")
            return

        # Start command thread to keep ui responsive
        thread = RsyncSSH(
            self.view,
            settings,
            args.get("path_being_saved", ""),
            args.get("restrict_to_destinations", None),
            args.get("force_sync", False),
        )
        thread.start()


def build_ssh_destination_string(destination):
    """Build SSH destination string: (user@)host(:port)"""

    user = destination.get("remote_user")
    host = destination.get("remote_host")
    port = destination.get("remote_port")

    parts = [
        user + "@" if user else None,
        host,
        ":" + str(port) if port else None,
    ]
    return "".join(filter(None, parts))


def build_rsync_destination_string(destination, path=None):
    if path is None:
        path = destination.get("remote_path")
    return build_ssh_destination_string(destination) + ":" + shlex.quote(path)


class RsyncSSH(threading.Thread):
    """Rsync path to remote"""

    def __init__(
        self,
        view,
        settings,
        path_being_saved="",
        restrict_to_destinations=None,
        force_sync=False,
    ):
        """Set the stage"""
        self.view = view
        self.settings = settings
        self.path_being_saved = normalize_path(path_being_saved)
        self.restrict_to_destinations = restrict_to_destinations
        self.force_sync = force_sync
        threading.Thread.__init__(self)

    def run(self):
        """Iterate over remotes and destinations and sync all paths that match the saved path"""

        # Merge settings with defaults
        global_excludes = [".DS_Store"]
        global_excludes.extend(self.settings.get("excludes", []))

        global_options = []
        global_options.extend(self.settings.get("options", []))

        connect_timeout = self.settings.get("timeout", 10)

        # Get path to local ssh binary
        ssh_binary = self.settings.get("ssh_binary", self.settings.get("ssh_command", "ssh"))

        # Each rsync is started in a separate thread
        threads = []

        # Iterate over project folders, as we need to know where they are in the file system (they are the containers)
        for folder_path_full in self.view.window().folders():
            folder_path_basename = os.path.basename(folder_path_full)

            # Iterate over remotes which is indexed by the local folder path
            for remote_key in self.settings.get("remotes").keys():
                # Disallow use of . as remote_key when more than one remote is present
                if remote_key == "." and len(self.settings.get("remotes").keys()) > 1:
                    console_print(
                        "",
                        folder_path_basename,
                        "Use of . is ambiguous when project has more than one folder.",
                    )
                    continue

                # Resolve local path to absolute path
                local_path = ""

                # Setup logging prefix - default to base name of the container folder
                prefix = folder_path_basename

                # We have a remote with a regular path, lets update the prefix with subfolder name if it exists
                if remote_key != ".":
                    # Just continue if remote_key doesn't contain the folder_path_basename, it means
                    # the remote_key(local_path) is not within the directory we are processing now
                    if not folder_path_basename in remote_key:
                        continue

                    # Look for subfolder in remote_key
                    # If remote key is relative also get the split prefix so we can compose the container folder later
                    [split_prefix, subfolder] = str.rsplit(remote_key, folder_path_basename, 1)
                    # If split prefix is absolute, we'll remove it to get a nice short prefix
                    if split_prefix.startswith("/"):
                        split_prefix = ""
                    folder_path_basename = split_prefix + folder_path_basename

                    # Get container folder from real folder, ignore the rest
                    container_folder = (str.rsplit(folder_path_full, folder_path_basename, 1))[0]

                    # Update prefix with subfolder and remove container folder to get nice short prefix
                    prefix = split_prefix + prefix + subfolder
                    prefix = prefix.replace(container_folder, "")

                    # Remote key with absolute path and subfolder
                    if remote_key.startswith(container_folder) and len(subfolder) > 0:
                        local_path = container_folder + folder_path_basename + subfolder
                    # Remote key with absolute path and no subfolder
                    elif remote_key.startswith(container_folder) and len(subfolder) == 0:
                        local_path = container_folder + folder_path_basename
                    # Remote key with relative  path and subfolder
                    elif remote_key.startswith(folder_path_basename) and len(subfolder) > 0:
                        local_path = container_folder + folder_path_basename + subfolder
                    # Remote key with relative  path and no subfolder
                    elif remote_key.startswith(folder_path_basename) and len(subfolder) == 0:
                        local_path = container_folder + folder_path_basename + subfolder
                    # We tried everything, it should have worked ;-)
                    else:
                        console_print(
                            "",
                            "",
                            "Unable to determine local path for " + remote_key,
                        )
                        continue
                # We have a remote with '.' as path
                else:
                    # Remote key is current path, will only work with a single folder project
                    local_path = os.path.dirname(self.view.window().project_file_name())

                # Might have mixed slash characters on Windows.
                local_path = normalize_path(local_path)

                # For each remote destination iterate over each destination and start a rsync thread
                for destination in self.settings.get("remotes").get(remote_key):
                    # Don't sync if saving single file outside of current remotes local file path
                    if (
                        self.path_being_saved
                        and os.path.isfile(self.path_being_saved)
                        and not self.path_being_saved.startswith(local_path + "/")
                    ):
                        continue

                    # Don't sync if directory path being saved does not match the local path
                    if self.path_being_saved and os.path.isdir(self.path_being_saved) and self.path_being_saved != local_path:
                        continue

                    destination_string = build_rsync_destination_string(destination)

                    # If this remote has restrictions, we'll respect them
                    if self.restrict_to_destinations and destination_string not in self.restrict_to_destinations:
                        continue

                    # Merge local settings with global defaults
                    local_excludes = list(global_excludes)
                    local_excludes.extend(destination.get("excludes", []))

                    local_options = list(global_options)
                    local_options.extend(destination.get("options", []))

                    thread = Rsync(
                        self.view,
                        ssh_binary,
                        local_path,
                        prefix,
                        destination,
                        local_excludes,
                        local_options,
                        connect_timeout,
                        self.path_being_saved,
                        self.force_sync,
                    )
                    threads.append(thread)

                    # Update status message
                    status_bar_message = "Rsyncing to " + str(len(threads)) + " destination"
                    if len(self.view.window().folders()) > 1:
                        status_bar_message += "s"
                    self.view.set_status("00000_rsync_ssh_status", status_bar_message)

                    thread.start()

        # Wait for all threads to finish
        if threads:
            for thread in threads:
                thread.join()
            status_bar_message = self.view.get_status("00000_rsync_ssh_status")
            self.view.set_status("00000_rsync_ssh_status", "")
            sublime.status_message(status_bar_message + " - done.")
            console_print("", "", "done")
        else:
            status_bar_message = self.view.get_status("00000_rsync_ssh_status")
            self.view.set_status("00000_rsync_ssh_status", "")
            sublime.status_message(status_bar_message + " - done.")

        # Unblock sync
        self.view.set_status("00000_rsync_ssh_status", "")
        return
        # # Don't sync if saving single file outside of project path
        # if self.path_being_saved and not self.path_being_saved.startswith(folder_path_full+"/"):
        #     continue


class Rsync(threading.Thread):
    """rsync executor"""

    def __init__(
        self,
        view,
        ssh_binary,
        local_path,
        prefix,
        destination,
        excludes,
        options,
        timeout,
        specific_path,
        force_sync=False,
    ):
        self.ssh_binary = ssh_binary
        self.view = view
        self.local_path = local_path
        self.prefix = prefix
        self.destination = destination
        self.excludes = excludes
        self.options = options
        self.timeout = timeout
        self.specific_path = specific_path
        self.force_sync = force_sync
        self.rsync_path = ""
        threading.Thread.__init__(self)

    def ssh_command_with_default_args(self):
        """Get ssh command with defaults"""

        # Build list with defaults
        ssh_command = [
            self.ssh_binary,
            "-q",
            "-T",
            "-o",
            "ConnectTimeout=" + str(self.timeout),
        ]
        if self.destination.get("remote_port"):
            ssh_command.extend(["-p", str(self.destination.get("remote_port"))])

        custom_ssh_args = rsync_ssh_settings(self.view).get("ssh_args", [])
        ssh_command.extend(custom_ssh_args)

        return ssh_command

    def run(self):
        # Cygwin version of rsync is assumed on Windows. Local path needs to be converted using cygpath.
        if sublime.platform() == "windows":
            try:
                self.local_path = check_output(["cygpath", self.local_path]).strip()
                if self.specific_path:
                    self.specific_path = check_output(["cygpath", self.specific_path]).strip()
            except subprocess.CalledProcessError as error:
                console_show(self.view.window())
                console_print(
                    self.destination.get("remote_host"),
                    self.prefix,
                    "ERROR: Failed to run cygpath to convert local file path. Can't continue.",
                )
                console_print(
                    self.destination.get("remote_host"),
                    self.prefix,
                    error.output,
                )
                return

        # Skip disabled destinations, unless we explicitly force a sync (e.g. for specific destinations)
        if not self.force_sync and not self.destination.get("enabled", 1):
            console_print(
                self.destination.get("remote_host"),
                self.prefix,
                "Skipping, destination is disabled.",
            )
            return

        # What to rsync
        source_path = self.local_path + "/"
        destination_path = self.destination.get("remote_path")

        # Handle specific path syncs (e.g. save events and specific remote)
        if self.specific_path and os.path.isfile(self.specific_path) and self.specific_path.startswith(self.local_path + "/"):
            source_path = self.specific_path
            destination_path = self.destination.get("remote_path") + self.specific_path.replace(self.local_path, "")
        elif self.specific_path and os.path.isdir(self.specific_path) and self.specific_path.startswith(self.local_path + "/"):
            source_path = self.specific_path + "/"
            destination_path = self.destination.get("remote_path") + self.specific_path.replace(self.local_path, "")

        # Check ssh connection, and get path of rsync on the remote host
        check_command = self.ssh_command_with_default_args()
        check_command.extend(
            [
                build_ssh_destination_string(self.destination),
                "LANG=C which rsync",
            ]
        )

        settings = self.view.window().settings()
        self.rsync_path = settings.get("rsync_ssh_path", "")
        if not self.rsync_path:
            try:
                console_print("", "", "checking")
                rsync_path = check_output(check_command, timeout=self.timeout, stderr=subprocess.STDOUT).rstrip()
                if not rsync_path.endswith("/rsync"):
                    console_show(self.view.window())
                    message = "ERROR: Unable to locate rsync on " + self.destination.get("remote_host")
                    console_print(self.destination.get("remote_host"), self.prefix, message)
                    console_print(
                        self.destination.get("remote_host"),
                        self.prefix,
                        rsync_path,
                    )
                    return
                settings.set("rsync_ssh_path", rsync_path)
                self.rsync_path = rsync_path
            except subprocess.TimeoutExpired as error:
                console_show(self.view.window())
                console_print(
                    self.destination.get("remote_host"),
                    self.prefix,
                    "ERROR: " + error.output,
                )
                return
            except subprocess.CalledProcessError as error:
                console_show(self.view.window())
                if error.returncode == 255 and error.output == "":
                    console_print(
                        self.destination.get("remote_host"),
                        self.prefix,
                        "ERROR: ssh check command failed, have you accepted the remote host key?",
                    )
                    console_print(
                        self.destination.get("remote_host"),
                        self.prefix,
                        "       Try running the ssh command manually in a terminal:",
                    )
                    console_print(
                        self.destination.get("remote_host"),
                        self.prefix,
                        "       " + " ".join(error.cmd),
                    )
                else:
                    console_print(
                        self.destination.get("remote_host"),
                        self.prefix,
                        "ERROR: " + error.output,
                    )

                return

        # Remote pre command
        if self.destination.get("remote_pre_command"):
            pre_command = self.ssh_command_with_default_args()
            pre_command.extend(
                [
                    build_ssh_destination_string(self.destination),
                    '$SHELL -l -c "LANG=C cd '
                    + self.destination.get("remote_path")
                    + " && "
                    + self.destination.get("remote_pre_command")
                    + '"',
                ]
            )
            try:
                console_print(
                    self.destination.get("remote_host"),
                    self.prefix,
                    "Running pre command: " + self.destination.get("remote_pre_command"),
                )
                output = check_output(pre_command, stderr=subprocess.STDOUT)
                if output:
                    output = re.sub(r"\n$", "", output)
                    console_print(self.destination.get("remote_host"), self.prefix, output)
            except subprocess.CalledProcessError as error:
                console_show(self.view.window())
                console_print(
                    self.destination.get("remote_host"),
                    self.prefix,
                    "ERROR: " + error.output + "\n",
                )

        # Build rsync command
        rsync_command = [
            rsync_ssh_settings(self.view).get("command", "rsync"),
            "-v",
            "-zar",
            "-e",
            " ".join(self.ssh_command_with_default_args()),
        ]

        # We allow options to be specified as "--foo bar" in the config so we need to split all options on first space after the option name
        for option in self.options:
            if "=" not in option:
                rsync_command.extend(option.split(" ", 1))
            else:
                rsync_command.append(option)

        rsync_command.extend(
            [
                source_path,
                build_rsync_destination_string(self.destination, destination_path),
            ]
        )

        # Add excludes
        for exclude in set(self.excludes):
            rsync_command.append("--exclude=" + exclude)

        rsync_path_prefix = rsync_ssh_settings(self.view).get("rsync_path_prefix", "").rstrip() + " "

        # Add mkdir unless we have a --dry-run flag
        if len([option for option in rsync_command if "--dry-run" in option]) == 0:
            rsync_command.extend(
                [
                    "--rsync-path",
                    rsync_path_prefix
                    + "mkdir -p '"
                    + os.path.dirname(destination_path)
                    + "' && "
                    + rsync_path_prefix
                    + self.rsync_path,
                ]
            )

        # Show actual rsync command in the console
        console_print(
            self.destination.get("remote_host"),
            self.prefix,
            " ".join(shlex.quote(a) for a in rsync_command),
        )

        # Execute rsync
        try:
            output = check_output(rsync_command, stderr=subprocess.STDOUT)
            # Fix rsync output to include relative remote path
            if self.specific_path and os.path.isfile(self.specific_path):
                destination_file_relative = re.sub(
                    self.destination.get("remote_path") + "/?",
                    "",
                    destination_path,
                )
                destination_file_basename = os.path.basename(destination_file_relative)
                output = re.sub(destination_file_basename, destination_file_relative, output)
            console_print(self.destination.get("remote_host"), self.prefix, output)
            if len([option for option in rsync_command if "--dry-run" in option]) != 0:
                console_print(
                    self.destination.get("remote_host"),
                    self.prefix,
                    "NOTICE: Nothing synced. Remove --dry-run from options to sync.",
                )
        except subprocess.CalledProcessError as error:
            console_show(self.view.window())
            if len([option for option in rsync_command if "--dry-run" in option]) != 0 and re.search(
                "No such file or directory", error.output, re.MULTILINE
            ):
                console_print(
                    self.destination.get("remote_host"),
                    self.prefix,
                    "WARNING: Unable to do dry run, remote directory " + os.path.dirname(destination_path) + " does not exist.",
                )
            else:
                console_print(
                    self.destination.get("remote_host"),
                    self.prefix,
                    "ERROR: " + error.output + "\n",
                )

        # Remote post command
        if self.destination.get("remote_post_command"):
            post_command = self.ssh_command_with_default_args()
            post_command.extend(
                [
                    build_ssh_destination_string(self.destination),
                    '$SHELL -l -c "LANG=C cd \\"'
                    + self.destination.get("remote_path")
                    + '\\" && '
                    + self.destination.get("remote_post_command")
                    + '"',
                ]
            )
            try:
                console_print(
                    self.destination.get("remote_host"),
                    self.prefix,
                    "Running post command: " + self.destination.get("remote_post_command"),
                )
                output = check_output(
                    post_command,
                    stdin=subprocess.DEVNULL,
                    stderr=subprocess.STDOUT,
                )
                if output:
                    output = re.sub(r"\n$", "", output)
                    console_print(self.destination.get("remote_host"), self.prefix, output)
            except subprocess.CalledProcessError as error:
                console_show(self.view.window())
                console_print(
                    self.destination.get("remote_host"),
                    self.prefix,
                    "ERROR: " + error.output + "\n",
                )

        # End of run
        return
