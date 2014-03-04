import sys

if sys.version_info[:2] < (2, 7):
    import unittest2 as unittest
else:
    import unittest

import mock

from enstaller.main import main, main_noexc

from enstaller.tests.common import mock_print, with_default_configuration

class TestMisc(unittest.TestCase):
    @with_default_configuration
    def test_list_bare(self):
        with mock.patch("enstaller.main.print_installed"):
            with mock_print() as m:
                main_noexc(["--list"])
            self.assertMultiLineEqual(m.value, "prefix: {0}\n\n".format(sys.prefix))

    @with_default_configuration
    def test_print_version(self):
        # XXX: this is lousy test: we'd like to at least ensure we're printing
        # the correct version, but capturing the stdout is a bit tricky. Once
        # we replace print by proper logging, we should be able to do better.
        try:
            main(["--version"])
        except SystemExit as e:
            self.assertEqual(e.code, 0)

    @with_default_configuration
    def test_help_runs_and_exits_correctly(self):
        try:
            main(["--help"])
        except SystemExit as e:
            self.assertEqual(e.code, 0)

    @with_default_configuration
    def test_print_env(self):
        try:
            main(["--env"])
        except SystemExit as e:
            self.assertEqual(e.code, 0)
