import os
import sys
from unittest import TestCase

import sublime
import sublime_plugin

rsync_ssh = sys.modules["sublime-rsync-ssh.rsync_ssh"]


class TestFunctions(TestCase):
    def tearDown(self):
        sublime.active_window().run_command("show_panel", {"panel": "output.UnitTesting", "toggle": False})

    def test_console_print(self):
        console_print = rsync_ssh.console_print

        self.assertEquals(console_print("host", "prefix", "output"), "[rsync-ssh] host[prefix]: output")
        self.assertEquals(console_print("", "", "c"), "[rsync-ssh] c")
        self.assertEquals(console_print("host", "", "output"), "[rsync-ssh] host: output")
        self.assertEquals(console_print("", "prefix", "output"), "[rsync-ssh] prefix: output")

    def test_console_show(self):
        self.assertEquals(sublime.active_window().active_panel(), "output.UnitTesting")
        rsync_ssh.console_show()
        self.assertEquals(sublime.active_window().active_panel(), "console")

    def test_normalize_path(self):
        self.assertEquals(rsync_ssh.normalize_path("asdf"), "asdf")


class TestUserFunction(TestCase):
    def setUp(self):
        self.old_environ = os.environ
        os.environ = os.environ.copy()
        if "USER" in os.environ:
            del os.environ["USER"]
        if "USERNAME" in os.environ:
            del os.environ["USERNAME"]

    def tearDown(self):
        os.environ = self.old_environ

    def test_no_current_user(self):
        assert rsync_ssh.current_user() == "username"

    def test_current_user_USER_set(self):
        os.environ["USER"] = "alice"
        assert rsync_ssh.current_user() == "alice"

    def test_current_user_USERNAME_set(self):
        os.environ["USERNAME"] = "bob"
        assert rsync_ssh.current_user() == "bob"

    def test_current_user_USERNAME_and_USER_set(self):
        os.environ["USERNAME"] = "bob"
        os.environ["USER"] = "alice"
        assert rsync_ssh.current_user() == "alice"


class TestCheckOutput(TestCase):
    def test_check_output(self):
        output = rsync_ssh.check_output("echo 1", shell=True)
        self.assertEquals(output.strip(), "1")

    def test_check_output_exception(self):
        with self.assertRaises(Exception):
            rsync_ssh.check_output("bin/false")
