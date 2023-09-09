import sys
from unittest import TestCase

rsync_ssh = sys.modules["sublime-rsync-ssh.rsync_ssh"]


class TestFunctions(TestCase):
    def test_console_print(self):
        console_print = rsync_ssh.console_print

        self.assertEquals(console_print("host", "prefix", "output"), "[rsync-ssh] host[prefix]: output")
        self.assertEquals(console_print("", "", "c"), "[rsync-ssh] c")
        self.assertEquals(console_print("host", "", "output"), "[rsync-ssh] host: output")
        self.assertEquals(console_print("", "prefix", "output"), "[rsync-ssh] prefix: output")
