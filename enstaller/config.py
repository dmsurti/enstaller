# Copyright by Enthought, Inc.
# Author: Ilan Schnell <ischnell@enthought.com>

import _ast
import ast
import base64
import copy
import json
import re
import os
import sys
import textwrap
import platform
import urllib2

from getpass import getpass
from os.path import isfile, join

from enstaller import __version__
from enstaller.errors import AuthFailedError, EnstallerException, InvalidConfiguration
from utils import PY_VER, abs_expanduser, fill_url

def __import_new_keyring():
    """
    Import keyring >= 1.1.
    """
    import keyring.backends.OS_X
    import keyring.backends.Gnome
    import keyring.backends.Windows
    import keyring.backends.kwallet

    keyring.core.init_backend()
    if keyring.get_keyring().priority < 0:
        keyring = None
    return keyring

def __import_old_keyring():
    import keyring
    import keyring.backend
    # don't use keyring backends that require console input or just do
    # more or less the same thing we're already doing
    keyring.backend._all_keyring = [keyring.backend.OSXKeychain(),
                                    keyring.backend.GnomeKeyring(),
                                    keyring.backend.KDEKWallet(),
                                    keyring.backend.Win32CryptoKeyring(),
                                    keyring.backend.Win32CryptoRegistry(),
                                    keyring.backend.WinVaultKeyring()]
    keyring.core.init_backend()
    if keyring.get_keyring().supported() < 0:
        keyring = None
    return keyring

try:
    import keyring
except ImportError, KeyError:
    # The KeyError happens when USERPROFILE env var is not defined on windows
    keyring = None
else:
    try:
        keyring = __import_new_keyring()
    except ImportError:
        try:
            keyring = __import_old_keyring()
        except ImportError:
            keyring = None

KEYRING_SERVICE_NAME = 'Enthought.com'

config_fn = ".enstaller4rc"
home_config_path = abs_expanduser("~/" + config_fn)
system_config_path = join(sys.prefix, config_fn)

def get_default_url():
    import plat
    return 'https://api.enthought.com/eggs/%s/' % plat.custom_plat

class PythonConfigurationParser(ast.NodeVisitor):
    def __init__(self):
        self._data = {}

    def parse(self, s):
        self._data.clear()

        root = ast.parse(s)
        self.visit(root)
        return self._data

    def generic_visit(self, node):
        if type(node) != _ast.Module:
            raise ValueError("Unexpected expression @ line {0}".format(node.lineno))
        super(PythonConfigurationParser, self).generic_visit(node)

    def visit_Assign(self, node):
        value = ast.literal_eval(node.value)
        for target in node.targets:
            self._data[target.id] = value

RC_TMPL = """\
# enstaller configuration file
# ============================
#
# This file contains the default package repositories and configuration
# used by enstaller %(version)s for the Python %(py_ver)s environment:
#
#   sys.prefix = %(sys_prefix)r
#
# This file was initially created by running the enpkg command.

%(auth_section)s

# `use_webservice` refers to using 'https://api.enthought.com/eggs/'.
# The default is True; that is, the webservice URL is used for fetching
# eggs.  Uncommenting changes this behavior to using the explicit
# IndexedRepos listed below.
#use_webservice = False

# When use_webservice is True, one can control the webservice entry point enpkg
# will talk to. If not specified, a default will be used. Mostly useful for
# testing
#webservice_entry_point = "https://acme.com/api/{PLATFORM}/"

# The enpkg command searches for eggs in the list `IndexedRepos` defined
# below.  When enpkg searches for an egg, it tries each repository in
# this list in order and selects the first one that matches, ignoring
# remaining repositories.  Therefore, the order of this list matters.
#
# For local repositories, the index file is optional.  Remember that on
# Windows systems backslashes in a directory path need to escaped, e.g.:
# r'file://C:\\repository\\' or 'file://C:\\\\repository\\\\'
IndexedRepos = [
#  'https://www.enthought.com/repo/ets/eggs/{SUBDIR}/',
  'https://www.enthought.com/repo/epd/GPL-eggs/{SUBDIR}/',
  'https://www.enthought.com/repo/epd/eggs/{SUBDIR}/',
# The Enthought PyPI build mirror:
  'http://www.enthought.com/repo/pypi/eggs/{SUBDIR}/',
]

# Install prefix (enpkg --prefix and --sys-prefix options overwrite
# this).  When this variable is not provided, it will default to the
# value of sys.prefix (within the current interpreter running enpkg).
#prefix = %(sys_prefix)r

# When running enpkg behind a firewall it might be necessary to use a
# proxy to access the repositories.  The URL for the proxy can be set
# here.  Note that the enpkg --proxy option will overwrite this setting.
%(proxy_line)s

# Uncomment the next line to disable application menu-item installation.
# This only affects the few packages that install menu items, such as
# IPython.
#noapp = True

# Uncomment the next line to turn off automatic prompts to update
# enstaller.
#autoupdate = False
"""


class Configuration(object):
    @classmethod
    def _get_default_config(cls):
        config_filename = get_path()
        if config_filename is not None:
            return cls.from_file(config_filename)
        else:
            return cls()

    @classmethod
    def from_file(cls, filename):
        def _create(fp):
            ret = cls()
            for k, v in parser.parse(fp.read()).iteritems():
                setattr(ret, k, v)
            return ret

        parser = PythonConfigurationParser()
        if isinstance(filename, basestring):
            with open(filename, "rt") as fp:
                return _create(fp)
        else:
            return _create(fp)

    def __init__(self):
        self.proxy = None
        self.noapp = False
        self.EPD_auth = None
        self.EPD_username = None
        self.use_webservice = True
        self.autoupdate =  True

        self._prefix = sys.prefix
        self._local = join(sys.prefix, 'LOCAL-REPO')
        self._IndexedRepos = []
        self._webservice_entry_point = fill_url(get_default_url())

        self.repository_cache = self.local

    def set_auth(self, username, password):
        self.EPD_auth = None
        self.EPD_username = None

        if username is None or password is None:
            raise InvalidConfiguration(
                    "invalid authentication arguments: "
                    "{0}:{1}".format(username, password))

        if keyring:
            self.EPD_username = username
            keyring.set_password(KEYRING_SERVICE_NAME, username, password)
        else:
            self.EPD_auth = base64.encodestring('%s:%s' % (username, password))

    def reset_auth(self):
        if keyring and self.EPD_username is not None:
            keyring.set_password(KEYRING_SERVICE_NAME, username, "")

        self.EPD_auth = None
        self.EPD_username = None

    def get_auth(self):
        old_auth = self.EPD_auth
        if old_auth:
            decoded_auth = old_auth.decode('base64')
            parts = decoded_auth.split(":")
            if len(parts) != 2:
                raise InvalidConfiguration("Authentication string is corrupted")
            else:
                return tuple(parts)

        username = self.EPD_username
        if username:
            password = None
            if keyring:
                password = keyring.get_password(KEYRING_SERVICE_NAME, username)
            if password:
                return username, password
            else:
                return None, None
        else:
            return None, None

    def _default_filename(self):
        if sys.platform != 'win32' and os.getuid() == 0:
            return system_config_path
        else:
            return home_config_path

    def write(self, filename=None):
        if filename is None:
            filename = self._default_filename()

        username, password = self.get_auth()
        if username and password:
            if keyring:
                authline = 'EPD_username = %r' % self.EPD_username
            else:
                authline = 'EPD_auth = %r' % self.EPD_auth.strip()
            auth_section = textwrap.dedent("""
            # EPD subscriber authentication is required to access the EPD
            # repository.  To change your credentials, use the 'enpkg --userpass'
            # command, which will ask you for your email address (or username) and
            # password.
            %s
            """ % authline)
        else:
            auth_section = ''

        py_ver = PY_VER
        sys_prefix = sys.prefix
        version = __version__

        if self.proxy:
            proxy_line = 'proxy = %r' % self.proxy
        else:
            proxy_line = ('#proxy = <proxy string>  '
                          '# e.g. "http://<user>:<passwd>@123.0.1.2:8080"')

        with open(filename, "wt") as fo:
            fo.write(RC_TMPL % locals())

    def _change_auth(self, filename=None):
        if filename is None:
            filename = self._default_filename()

        # XXX: should we really just write the file in this case instead of
        # erroring-out ?
        if not os.path.isfile(filename):
            self.write(filename)
            return
        else:
            pat = re.compile(r'^(EPD_auth|EPD_username)\s*=.*$', re.M)
            with open(filename, 'rt') as fi:
                data = fi.read()

            if not self.is_auth_configured:
                if pat.search(data):
                    data = pat.sub("", data)
                with open(filename, 'wt') as fo:
                    fo.write(data)
                return

            if keyring:
                authline = 'EPD_username = %r' % self.EPD_username
            else:
                authline = 'EPD_auth = %r' % self.EPD_auth.strip()

            if pat.search(data):
                data = pat.sub(authline, data)
            else:
                lines = data.splitlines()
                lines.append(authline)
                data = '\n'.join(lines) + '\n'

            with open(filename, 'wt') as fo:
                fo.write(data)

    def _checked_change_auth(self, filename=None, remote=None):
        if not self.is_auth_configured:
            raise InvalidConfiguration("No auth configured: cannot "
                                       "change auth.")
        user = {}

        try:
            user = authenticate(self, remote)
        except AuthFailedError as e:
            print e
            print "No credential saved."
        else:
            self._change_auth(filename)
            print subscription_message(self, user)
        return user

    @property
    def is_auth_configured(self):
        """
        Returns True if authentication is setup for this configuration object.

        Note
        ----
        This only checks whether the auth is configured, not whether the
        authentication information is correct.
        """
        # FIXME: this does not really belong here, and should be put in the
        # configuration object once it is not a module-level global
        if self.EPD_auth:
            return True
        else:
            username = self.EPD_username
            if username and keyring:
                return True
            else:
                return False

    @property
    def local(self):
        return self._local

    @local.setter
    def local(self, value):
        self._local = abs_expanduser(value)

    @property
    def prefix(self):
        return self._prefix

    @prefix.setter
    def prefix(self, value):
        self._prefix = abs_expanduser(value)

    @property
    def IndexedRepos(self):
        return self._IndexedRepos

    @IndexedRepos.setter
    def IndexedRepos(self, urls):
        self._IndexedRepos = [fill_url(url) for url in urls]

    @property
    def webservice_entry_point(self):
        return self._webservice_entry_point

    @webservice_entry_point.setter
    def webservice_entry_point(self, url):
        self._webservice_entry_point = fill_url(url)


def get_path():
    """
    Return the absolute path to the config file.
    """
    if isfile(home_config_path):
        return home_config_path
    if isfile(system_config_path):
        return system_config_path
    return None


def input_auth():
    """
    Prompt user for username and password.  Return (username, password)
    tuple or (None, None) if left blank.
    """
    print """\
Please enter the email address (or username) and password for your
EPD or EPD Free subscription.  If you are not subscribed to EPD,
just press Enter.
"""
    username = raw_input('Email (or username): ').strip()
    if not username:
        return None, None
    return username, getpass('Password: ')


def web_auth(auth,
        api_url='https://api.enthought.com/accounts/user/info/'):
    """
    Authenticate a user's credentials (an `auth` tuple of username,
    password) using the web API.  Return a dictionary containing user
    info.

    Function taken from Canopy and modified.
    """
    # Make basic local checks
    username, password = auth
    if username is None or password is None:
        raise AuthFailedError("Authentication error: User login is required.")

    # Authenticate with the web API
    auth = 'Basic ' + (':'.join(auth).encode('base64').strip())
    req = urllib2.Request(api_url, headers={'Authorization': auth})

    try:
        f = urllib2.urlopen(req)
    except urllib2.URLError as e:
        raise AuthFailedError("Authentication error: %s" % e.reason)

    try:
        res = f.read()
    except urllib2.HTTPError as e:
        raise AuthFailedError("Authentication error: %s" % e.reason)

    # See if web API refused to authenticate
    user = json.loads(res)
    if not(user['is_authenticated']):
        raise AuthFailedError('Authentication error: Invalid user login.')

    return user


def subscription_level(user):
    """
    Extract the level of EPD subscription from the dictionary (`user`)
    returned by the web API.
    """
    if 'has_subscription' in user:
        if user.get('is_authenticated', False) and user.get('has_subscription', False):
            return 'EPD Basic or above'
        elif user.get('is_authenticated', False) and not(user.get('has_subscription', False)):
            return 'EPD Free'
        else:
            return None
    else:  # don't know the subscription level
        if user.get('is_authenticated', False):
            return 'EPD'
        else:
            return None


def subscription_message(config, user):
    """
    Return a 'subscription level' message based on the `user`
    dictionary.

    `user` is a dictionary, probably retrieved from the web API, that
    may contain `is_authenticated`, and `has_subscription`.
    """
    message = ""

    if user.get('is_authenticated', False):
        username, password = config.get_auth()
        login = "You are logged in as %s" % username
        subscription = "Subscription level: %s" % subscription_level(user)
        name = user.get('first_name', '') + ' ' + user.get('last_name', '')
        name = name.strip()
        if name:
            name = ' (' + name + ')'
        message = login + name + '.\n' + subscription
    else:
        message = "You are not logged in.  To log in, type 'enpkg --userpass'."

    return message


def prepend_url(url):
    f = open(get_path(), 'r+')
    data = f.read()
    pat = re.compile(r'^IndexedRepos\s*=\s*\[\s*$', re.M)
    if not pat.search(data):
        sys.exit("Error: IndexedRepos section not found")
    data = pat.sub(r"IndexedRepos = [\n  '%s'," % url, data)
    f.seek(0)
    f.write(data)
    f.close()

def authenticate(configuration, remote=None):
    """
    Attempt to authenticate the user's credentials by the appropriate
    means.

    `remote` is enpkg.remote, required if not using the web API to
    authenticate

    If 'use_webservice' is set, authenticate with the web API and return
    a dictionary containing user info on success.

    Else, authenticate with remote.connect and return a dict containing
    is_authenticated=True on success.

    If authentication fails, raise an exception.
    """
    # FIXME: remove passing remote hack.

    if not configuration.is_auth_configured:
        raise EnstallerException("No valid auth information in "
                                 "configuration, cannot authenticate.")

    user = {}
    auth = configuration.get_auth()

    if configuration.use_webservice:
        # check credentials using web API
        try:
            user = web_auth(auth)
            assert user['is_authenticated']
        except Exception as e:
            raise AuthFailedError('Authentication failed: %s.' % e)
    else:
        # check credentials using remote.connect
        try:
            remote.connect(auth)
            user = dict(is_authenticated=True)
        except KeyError:
            raise AuthFailedError('Authentication failed:'
                    ' Invalid user login.')
        except Exception as e:
            raise AuthFailedError('Authentication failed: %s.' % e)
    return user


def print_config(config, remote, prefix):
    print "Python version:", PY_VER
    print "enstaller version:", __version__
    print "sys.prefix:", sys.prefix
    print "platform:", platform.platform()
    print "architecture:", platform.architecture()[0]
    print "use_webservice:", config.use_webservice
    print "config file:", get_path()
    print "settings:"
    print "    prefix = %s" % prefix
    print "    %s = %r" % ("local", config.local)
    print "    %s = %r" % ("noapp", config.noapp)
    print "    %s = %r" % ("proxy", config.proxy)
    print "    IndexedRepos:", '(not used)' if config.use_webservice else ''
    for repo in config.IndexedRepos:
        print '        %r' % repo

    user = {}
    try:
        user = authenticate(config, remote)
    except Exception as e:
        print e
    print subscription_message(config, user)
