from __future__ import absolute_import

import os.path
import shutil
import sys
import tempfile
import textwrap

if sys.version_info[:2] < (2, 7):
    import unittest2 as unittest
else:
    import unittest

import mock

from enstaller.main import main_noexc
from enstaller.config import _encode_auth

from enstaller.tests.common import (
    mock_print, fail_authenticate, mock_input_auth)

from .common import no_initial_configuration_context, without_any_configuration

FAKE_USER = "nono"
FAKE_PASSWORD = "le petit robot"
FAKE_CREDS = _encode_auth(FAKE_USER, FAKE_PASSWORD)

class TestAuth(unittest.TestCase):
    def setUp(self):
        self.d = tempfile.mkdtemp()
        self.config = os.path.join(self.d, ".enstaller4rc")

    def tearDown(self):
        shutil.rmtree(self.d)

    def test_auth_requested_without_config(self):
        """
        Ensure we ask for authentication if no .enstaller4rc is found.
        """
        with no_initial_configuration_context(self.config):
            with mock_print() as m:
                with self.assertRaises(SystemExit):
                    main_noexc([])

        self.assertEqual(m.value, "No authentication configured, required "
                                  "to continue.To login, type 'enpkg --userpass'.\n")

    @without_any_configuration
    def test_userpass_without_config(self):
        """
        Ensure we don't crash when empty information is input in --userpass
        prompt (no .enstaller4rc found).
        """
        with no_initial_configuration_context(self.config):
            with mock.patch("__builtin__.raw_input", return_value="") as m:
                with self.assertRaises(SystemExit):
                    main_noexc(["--userpass"])

        self.assertEqual(m.call_count, 3)

    @fail_authenticate
    def test_userpass_with_config(self):
        """
        Ensure enpkg --userpass doesn't crash when creds are invalid
        """
        r_output = ("Could not authenticate. Please check your credentials "
                    "and try again.\nNo modification was written.\n")

        with no_initial_configuration_context(self.config):
            with mock_print() as m:
                with mock_input_auth("nono", "robot"):
                    with self.assertRaises(SystemExit):
                        main_noexc(["--userpass"])

        self.assertMultiLineEqual(m.value, r_output)

    @fail_authenticate
    def test_enpkg_req_with_invalid_auth(self):
        """
        Ensure 'enpkg req' doesn't crash when creds are invalid
        """
        r_output = textwrap.dedent("""\
            Could not authenticate with user 'nono'.
            You can change your authentication details with 'enpkg --userpass'
            """)

        with open(self.config, "w") as fp:
            fp.write("EPD_auth = '{0}'".format(FAKE_CREDS))

        with mock_print() as m:
            with no_initial_configuration_context(self.config):
                with self.assertRaises(SystemExit):
                    main_noexc(["nono"])

        self.assertMultiLineEqual(m.value, r_output)
