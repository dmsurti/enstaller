from __future__ import print_function

import sys
import hashlib
from os.path import abspath, expanduser, getmtime, getsize, isdir, isfile, join

import urllib
import urlparse

from verlib import NormalizedVersion, IrrationalVersionError


PY_VER = '%i.%i' % sys.version_info[:2]


def abs_expanduser(path):
    return abspath(expanduser(path))


def canonical(s):
    """
    return the canonical representations of a project name
    DON'T USE THIS IN NEW CODE (ONLY (STILL) HERE FOR HISTORICAL REASONS)
    """
    # eventually (once Python 2.6 repo eggs are no longer supported), this
    # function should only return s.lower()
    s = s.lower()
    s = s.replace('-', '_')
    if s == 'tables':
        s = 'pytables'
    return s

def normalize_version_string(version_string):
    """
    Normalize the given version string to a string that can be converted to
    a NormalizedVersion.

    This function applies various special cases needed for EPD/Canopy and not
    handled in NormalizedVersion parser.

    Parameters
    ----------
    version_string: str
        The version to convert

    Returns
    -------
    normalized_version: str
        The normalized version string. Note that this is not guaranteed to be
        convertible to a NormalizedVersion
    """
    # This hack makes it possible to use 'rc' in the version, where
    # 'rc' must be followed by a single digit.
    version_string = version_string.replace('rc', '.dev99999')
    # This hack allows us to deal with single number versions (e.g.
    # pywin32's style '214').
    if not "." in version_string:
        version_string += ".0"

    if version_string.endswith(".dev"):
        version_string += "1"
    return version_string

def comparable_version(version):
    """
    Given a version string (e.g. '1.3.0.dev234'), return an object which
    allows correct comparison. For example:
        comparable_version('1.3.10') > comparable_version('1.3.8')  # True
    whereas:
        '1.3.10' > '1.3.8'  # False
    """
    try:
        ver = normalize_version_string(version)
        return NormalizedVersion(ver)
    except IrrationalVersionError:
        # If obtaining the RationalVersion object fails (for example for
        # the version '2009j'), simply return the string, such that
        # a string comparison can be made.
        return version


def md5_file(path):
    """
    Returns the md5sum of the file (located at `path`) as a hexadecimal
    string of length 32.
    """
    fi = open(path, 'rb')
    h = hashlib.new('md5')
    while True:
        chunk = fi.read(65536)
        if not chunk:
            break
        h.update(chunk)
    fi.close()
    return h.hexdigest()


def info_file(path):
    return dict(size=getsize(path),
                mtime=getmtime(path),
                md5=md5_file(path))


def cleanup_url(url):
    """
    Ensure a given repo string, i.e. a string specifying a repository,
    is valid and return a cleaned up version of the string.
    """
    if url.startswith(('http://', 'https://')):
        if not url.endswith('/'):
            url += '/'

    elif url.startswith('file://'):
        dir_path = url[7:]
        if dir_path.startswith('/'):
            # Unix filename
            if not url.endswith('/'):
                url += '/'
        else:
            # Windows filename
            if not url.endswith('\\'):
                url += '\\'

    elif isdir(abs_expanduser(url)):
        return cleanup_url('file://' + abs_expanduser(url))

    else:
        raise Exception("Invalid URL or non-existing file: %r" % url)

    return url


def fill_url(url):
    import plat

    url = url.replace('{ARCH}', plat.arch)
    url = url.replace('{SUBDIR}', plat.subdir)
    url = url.replace('{PLATFORM}', plat.custom_plat)
    return cleanup_url(url)

def exit_if_sudo_on_venv(prefix):
    """ Exits the running process with a message to run as non-sudo user.

    All the following conditions should match:
        - if the platform is non-windows
        - if we are running inside a venv
        - and the script is run as root/sudo

    """

    if sys.platform == 'win32':
        return

    if not isfile(join(prefix, 'pyvenv.cfg')):
        return

    import os

    if os.getuid() != 0:
        return

    print('You are running enpkg as a root user inside a virtual environment. ' \
          'Please run it as a normal user')

    sys.exit(1)

def path_to_uri(path):
    """Convert the given path string to a valid URI.

    It produces URI that are recognized by the windows
    shell API on windows, e.g. 'C:\\foo.txt' will be
    'file:///C:/foo.txt'"""
    return urlparse.urljoin("file:", urllib.pathname2url(path))

def uri_to_path(uri):
    """Convert a valid file uri scheme string to a native
    path.

    The returned path should be recognized by the OS and
    the native path functions, but is not guaranteed to use
    the native path separator (e.g. it could be C:/foo.txt
    on windows instead of C:\\foo.txt)."""
    urlpart = urlparse.urlparse(uri)
    if urlpart.scheme == "file":
        return urllib.url2pathname(urlpart.path)
    else:
        raise ValueError("Invalid file uri: {0}".format(uri))
