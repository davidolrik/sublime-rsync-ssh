import sublime, sublime_plugin
import subprocess, os, re, threading, time

def console_print(host, prefix, output):
    if host and prefix:
        host = host + "[" + prefix + "]: "
    elif host and not prefix:
        host = host + ": "
    elif not host and prefix:
        host = os.path.basename(prefix) + ": "

    output = "[rsync-ssh] " + host + output.replace("\n", "\n[rsync-ssh] "+ host)
    print(output)

def console_show():
    sublime.active_window().run_command("show_panel", {"panel": "console", "toggle": False})

def current_user():
    if 'USER' in os.environ:
        return os.environ['USER']
    elif 'USERNAME' in os.environ:
        return os.environ['USERNAME']
    else:
        return 'user'

class RsyncSshInitSettingsCommand(sublime_plugin.TextCommand):
    def run(self, edit):
        # Load project configuration
        project_data = sublime.active_window().project_data()

        if project_data == None:
            console_print("", "", "Unable to initialize settings, you must have a .sublime-project file.")
            console_print("", "", "Please use 'Project -> Save Project As...' first.")
            console_show()
            return

        # If no rsync-ssh config exists, then create it
        if not project_data.get('settings',{}).get("rsync_ssh"):
            if not project_data.get('settings'):
                project_data['settings'] = {}
            project_data['settings']["rsync_ssh"] = {}
            project_data['settings']["rsync_ssh"]["sync_on_save"] = True
            project_data['settings']["rsync_ssh"]["excludes"] = [
                '.git*', '_build', 'blib', 'Build'
            ]
            project_data['settings']["rsync_ssh"]["options"] = [
                "--dry-run",
                "--delete"
            ]

            project_data['settings']["rsync_ssh"]["remotes"] = {}

            if project_data.get("folders") == None:
                console_print("", "", "Unable to initialize settings, you must have at least one folder in your .sublime-project file.")
                console_print("", "", "Please use 'Add Folder to Project...' first.")
                console_show()
                return

            for folder in project_data.get("folders"):
                # Handle folder named '.'
                # User has added project file inside project folder, so we use the directory from the project file
                path = folder.get("path")
                if path == ".":
                    path = os.path.basename(os.path.dirname(sublime.active_window().project_file_name()))

                project_data['settings']["rsync_ssh"]["remotes"][path] = [{
                    "remote_host": "my-server.my-domain.tld",
                    "remote_path": "/home/" + current_user() + "/Projects/" + os.path.basename(path),
                    "remote_port": 22,
                    "remote_user": current_user(),
                    "remote_pre_command": "",
                    "remote_post_command": "",
                    "enabled": 1,
                    "options": [],
                    "excludes": []
                }]

            # Save configuration
            sublime.active_window().set_project_data(project_data)

        # We won't clobber an existing configuration
        else:
            console_print("","","rsync_ssh configuration already exists.")

        # Open configuration in new tab
        sublime.active_window().run_command("open_file",  {"file": "${project}"})


class RsyncSshSaveCommand(sublime_plugin.EventListener):
    def on_post_save(self,view):
        # Get settings
        settings = sublime.active_window().active_view().settings().get("rsync_ssh")

        # Don't do anything if rsync-ssh hasn't been configured
        if not settings:
            return
        # Don't sync single file if user has disabled sync on save
        elif settings.get("sync_on_save", True) == False:
            return

        # Return if we are already syncing the file
        if sublime.active_window().active_view().get_status("00000_rsync_ssh_status"):
            if settings.get("debug", False) == True:
                print("Sync already in progress")
            return

        # Block other instances of the same file from initiating sync
        sublime.active_window().active_view().set_status("00000_rsync_ssh_status", "Sync initiated")

        # Execute sync with the name of file being saved
        view.run_command("rsync_ssh_sync", {"file_being_saved": view.file_name()})


class RsyncSshSyncCommand(sublime_plugin.TextCommand):
    def run(self, edit, **args):
        # Get settings
        settings = sublime.active_window().active_view().settings().get("rsync_ssh")

        # Don't try to sync if User pressed ⌘⇧12 and rsync-ssh is unconfigured
        if not settings and not args.get("file_being_saved"):
            console_print("", "", "Aborting! - rsync ssh is not configured!")
            sublime.active_window().active_view().set_status("00000_rsync_ssh_status", "")
            return
        # Don't try to sync when we have no settings
        elif not settings:
            sublime.active_window().active_view().set_status("00000_rsync_ssh_status", "")
            return

        # Start command thread to keep ui responsive
        thread = RsyncSSH(settings, args.get("file_being_saved", ""))
        thread.start()


class RsyncSSH(threading.Thread):
    def __init__(self, settings, file_being_saved):
        self.settings         = settings
        self.file_being_saved = file_being_saved
        threading.Thread.__init__(self)

    def run(self):
        # Don't sync git commit message buffer
        if self.file_being_saved and os.path.basename(self.file_being_saved) == "COMMIT_EDITMSG":
            sublime.active_window().active_view().set_status("00000_rsync_ssh_status", "")
            return

        # Merge settings with defaults
        global_excludes = [ ".DS_Store" ]
        global_excludes.extend( self.settings.get("excludes", []) )

        global_options = []
        global_options.extend( self.settings.get("options", []) )

        connect_timeout = self.settings.get("timeout", 10)

        # Get path to local ssh binary
        ssh_binary = self.settings.get("ssh_binary", self.settings.get("ssh_command", "ssh"))

        # Iterate over all active folders and start a sync thread for each one
        threads = []
        status_bar_message = "Rsyncing " + str(len(sublime.active_window().folders())) + " folder"
        if len(sublime.active_window().folders()) > 1:
            status_bar_message += "s"
        sublime.active_window().active_view().set_status("00000_rsync_ssh_status", status_bar_message)

        # Iterate over all project folders
        for folder_path_full in sublime.active_window().folders():
            folder_path_basename = os.path.basename(folder_path_full)

            # Don't sync if saving single file outside of project path
            if self.file_being_saved and not self.file_being_saved.startswith(folder_path_full+"/"):
                continue

            # Default prefix is the folder name
            prefix = folder_path_basename

            # Build dict of matching remotes index by full local path
            remotes = {}

            # Iterate over remotes which is indexed by the local path
            for remote_key in self.settings.get("remotes").keys():
                # Disallow use of . as remote_key when more than one folder is present
                if remote_key == '.' and len(sublime.active_window().folders()) > 1:
                    console_print("", prefix, "Use of . is ambiguous when project has more than one folder.")
                    continue

                if remote_key != ".":
                    # Just continue if remote_key doesn't contain folder_path_basename, it means remote_key
                    # doesn't correspond to local project dir
                    if not folder_path_basename in remote_key:
                        continue

                    # Get subfolder from remote key
                    # If remote key is relative also get the split prefix so we can get the container folder later
                    [split_prefix, subfolder] = str.rsplit(remote_key, folder_path_basename, 1)
                    if split_prefix.startswith("/"):
                        # Split prefix is not relative, so we clear it
                        split_prefix = ""
                    folder_path_basename = split_prefix+folder_path_basename

                    # Get container folder from real folder, ignore the rest
                    [container_folder, ignore]   = str.rsplit(folder_path_full, folder_path_basename, 1)

                    # Update prefix with prefix and suffix
                    prefix = split_prefix+prefix+subfolder
                    prefix = prefix.replace(container_folder, "")

                # Compute local path
                local_path = ""
                # Remote key is current path, will only work with a single folder project
                if remote_key == ".":
                    local_path = folder_path_full
                # Remote key with absolute path and subfolder
                elif remote_key.startswith(container_folder) and len(subfolder) > 0:
                    local_path = container_folder+folder_path_basename+subfolder
                # Remote key with absolute path and no subfolder
                elif remote_key.startswith(container_folder) and len(subfolder) == 0:
                    local_path = container_folder+folder_path_basename
                # Remote key with relative  path and subfolder
                elif remote_key.startswith(folder_path_basename) and len(subfolder) > 0:
                    local_path = container_folder+folder_path_basename+subfolder
                # Remote key with relative  path and no subfolder
                elif remote_key.startswith(folder_path_basename) and len(subfolder) == 0:
                    local_path = container_folder+folder_path_basename+subfolder
                # We tried everything, it should have worked ;-)
                else:
                    console_print("","","Unable to determine local path for "+remote_key)
                    continue

                # Store remote from config indexed by full local path
                remotes[local_path] = self.settings.get("remotes").get(remote_key)

            # Don't sync if no remotes are defined
            if len(remotes.keys()) == 0:
                console_print("", prefix, "No remotes defined for "+folder_path_basename)
                continue

            for local_path in remotes.keys():
                # Don't sync if saving single file outside of current remotes local file path
                if self.file_being_saved and not self.file_being_saved.startswith(local_path+"/"):
                    continue

                for remote in remotes.get(local_path):
                    local_excludes = list(global_excludes)
                    local_excludes.extend(remote.get("excludes", []))

                    local_options = list(global_options)
                    local_options.extend(remote.get("options", []))

                    thread = Rsync(
                        ssh_binary,
                        local_path,
                        prefix,
                        remote,
                        local_excludes,
                        local_options,
                        connect_timeout,
                        self.file_being_saved
                    )
                    threads.append(thread)
                    thread.start()
        # Wait for all threads to finish
        if threads:
            [thread.join() for thread in threads]
            sublime.active_window().active_view().set_status("00000_rsync_ssh_status", "")
            sublime.status_message(status_bar_message + " - done.")
            console_print("", "", "done")
        else:
            sublime.active_window().active_view().set_status("00000_rsync_ssh_status", "")
            sublime.status_message(status_bar_message + " - done.")


class Rsync(threading.Thread):
    def __init__(self, ssh_binary, local_path, prefix, remote, excludes, options, timeout, single_file):
        self.ssh_binary  = ssh_binary
        self.local_path   = local_path
        self.prefix       = prefix
        self.remote       = remote
        self.excludes     = excludes
        self.options      = options
        self.timeout      = timeout
        self.single_file  = single_file
        threading.Thread.__init__(self)

    def run(self):
        # Skip disabled remotes
        if not self.remote.get("enabled", 1):
            console_print(self.remote.get("remote_host"), self.prefix, "Skipping, host is disabled.")
            return

        # What to rsync
        source_path      = self.local_path + "/"
        destination_path = self.remote.get("remote_path")

        # Handle single file syncs (save events)
        if self.single_file and self.single_file.startswith(self.local_path+"/"):
            source_path = self.single_file
            destination_path = self.remote.get("remote_path") + self.single_file.replace(self.local_path, "")

        # Check ssh connection, and get path of rsync on the remote host
        check_command = [
            self.ssh_binary, "-q", "-T", "-p", str(self.remote.get("remote_port", "22")),
            self.remote.get("remote_user")+"@"+self.remote.get("remote_host"),
            "LANG=C which rsync"
        ]
        try:
            self.rsync_path = subprocess.check_output(check_command, universal_newlines=True, timeout=self.timeout, stderr=subprocess.STDOUT).rstrip()
            if not self.rsync_path.endswith("/rsync"):
                console_show()
                message = "ERROR: Unable to locate rsync on "+self.remote.get("remote_host")
                console_print(self.remote.get("remote_host"), self.prefix, message)
                console_print(self.remote.get("remote_host"), self.prefix, self.rsync_path)
                return
        except subprocess.TimeoutExpired as e:
            console_show()
            console_print(self.remote.get("remote_host"), self.prefix, "ERROR: "+e.output)
            return
        except subprocess.CalledProcessError as e:
            console_show()
            if e.returncode == 255 and e.output == '':
                console_print(self.remote.get("remote_host"), self.prefix, "ERROR: ssh check command failed, have you accepted the remote host key?")
                console_print(self.remote.get("remote_host"), self.prefix, "       Try running the ssh command manually on in a terminal:")
                console_print(self.remote.get("remote_host"), self.prefix, "       "+" ".join(e.cmd))
            else:
                console_print(self.remote.get("remote_host"), self.prefix, "ERROR: "+e.output)

            return

        # Remote pre command
        if self.remote.get("remote_pre_command"):
            pre_command = [
                self.ssh_binary, "-q", "-T", "-p", str(self.remote.get("remote_port", "22")),
                self.remote.get("remote_user")+"@"+self.remote.get("remote_host"),
                "$SHELL -l -c \"LANG=C cd "+self.remote.get("remote_path")+" && "+self.remote.get("remote_pre_command")+"\""
            ]
            try:
                console_print(self.remote.get("remote_host"), self.prefix, "Running pre command: "+self.remote.get("remote_pre_command"))
                output = subprocess.check_output(pre_command, universal_newlines=True, stderr=subprocess.STDOUT)
                if output:
                    output = re.sub(r'\n$', "", output)
                    console_print(self.remote.get("remote_host"), self.prefix, output)
            except subprocess.CalledProcessError as e:
                console_show()
                console_print(self.remote.get("remote_host"), self.prefix, "ERROR: "+e.output+"\n")

        # Build rsync command
        rsync_command = [
            "rsync", "-v", "-zar",
            "-e", self.ssh_binary + " -q -T -p " + str(self.remote.get("remote_port", "22")) + " -o ConnectTimeout="+str(self.timeout)
        ]
        # We allow options to be specified as "--foo bar" in the config so we need to split all options on first space after the option name
        for option in self.options:
            rsync_command.extend( option.split(" ", 1) )

        rsync_command.extend([
            source_path,
            self.remote.get("remote_user")+"@"+self.remote.get("remote_host")+":"+destination_path
        ])

        # Add excludes
        for exclude in set(self.excludes):
            rsync_command.append("--exclude="+exclude)

        # Show actual rsync command in the console
        console_print(self.remote.get("remote_host"), self.prefix, " ".join(rsync_command))

        # Add mkdir unless we have a --dry-run flag
        if  len([option for option in rsync_command if '--dry-run' in option]) == 0:
            rsync_command.extend([
                "--rsync-path",
                "mkdir -p '" + os.path.dirname(destination_path) + "' && " + self.rsync_path
            ])

        # Execute rsync
        try:
            output = subprocess.check_output(rsync_command, universal_newlines=True, stderr=subprocess.STDOUT)
            console_print(self.remote.get("remote_host"), self.prefix, output)
            if  len([option for option in rsync_command if '--dry-run' in option]) != 0:
                console_print(self.remote.get("remote_host"), self.prefix, "NOTICE: Nothing synced. Remove --dry-run from options to sync.")
        except subprocess.CalledProcessError as e:
            console_show()
            if  len([option for option in rsync_command if '--dry-run' in option]) != 0 and re.search("No such file or directory", e.output, re.MULTILINE):
                console_print(self.remote.get("remote_host"), self.prefix, "WARNING: Unable to do dry run, remote directory "+os.path.dirname(destination_path)+" does not exist.")
            else:
                console_print(self.remote.get("remote_host"), self.prefix, "ERROR: "+e.output+"\n")

        # Remote post command
        if self.remote.get("remote_post_command"):
            post_command = [
                self.ssh_binary, "-q", "-T", "-p", str(self.remote.get("remote_port", "22")),
                self.remote.get("remote_user")+"@"+self.remote.get("remote_host"),
                "$SHELL -l -c \"LANG=C cd "+self.remote.get("remote_path")+" && "+self.remote.get("remote_post_command")+"\""
            ]
            try:
                console_print(self.remote.get("remote_host"), self.prefix, "Running post command: "+self.remote.get("remote_post_command"))
                output = subprocess.check_output(post_command, universal_newlines=True, stdin=subprocess.DEVNULL, stderr=subprocess.STDOUT)
                if output:
                    output = re.sub(r'\n$', "", output)
                    console_print(self.remote.get("remote_host"), self.prefix, output)
            except subprocess.CalledProcessError as e:
                console_show()
                console_print(self.remote.get("remote_host"), self.prefix, "ERROR: "+e.output+"\n")

        # End of run
        return
