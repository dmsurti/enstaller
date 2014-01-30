import errno
import logging
import os
import sys
import shutil
import tempfile
import zipfile

from os.path import basename, isdir, isfile, islink, join

logger = logging.getLogger(__name__)

if sys.version_info[:2] < (2, 7):
    class ZipFile(zipfile.ZipFile):
        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc_value, traceback):
            self.close()
else:
    ZipFile = zipfile.ZipFile

on_win = bool(sys.platform == 'win32')

if on_win:
    bin_dir_name = 'Scripts'
    rel_site_packages = r'Lib\site-packages'
else:
    bin_dir_name = 'bin'
    rel_site_packages = 'lib/python%i.%i/site-packages' % sys.version_info[:2]

ZIP_SOFTLINK_ATTRIBUTE_MAGIC = 0xA1ED0000L

def rm_empty_dir(path):
    """
    Remove the directory `path` if it is a directory and empty.
    If the directory does not exist or is not empty, do nothing.
    """
    try:
        os.rmdir(path)
    except OSError: # directory might not exist or not be empty
        pass


def rm_rf(path, verbose=False):
    if not on_win and islink(path):
        # Note that we have to check if the destination is a link because
        # exists('/path/to/dead-link') will return False, although
        # islink('/path/to/dead-link') is True.
        if verbose:
            logger.info("Removing: %r (link)" % path)
        os.unlink(path)

    elif isfile(path):
        if verbose:
            logger.info("Removing: %r (file)" % path)
        if on_win:
            try:
                os.unlink(path)
            except (WindowsError, IOError):
                os.rename(path, join(tempfile.mkdtemp(), basename(path)))
        else:
            os.unlink(path)

    elif isdir(path):
        if verbose:
            logger.info("Removing: %r (directory)" % path)
        if on_win:
            try:
                shutil.rmtree(path)
            except (WindowsError, IOError):
                os.rename(path, join(tempfile.mkdtemp(), basename(path)))
        else:
            shutil.rmtree(path)


def get_executable(prefix):
    if on_win:
        paths = [prefix, join(prefix, bin_dir_name)]
        for path in paths:
            executable = join(path, 'python.exe')
            if isfile(executable):
                return executable
    else:
        path = join(prefix, bin_dir_name, 'python')
        if isfile(path):
            from subprocess import Popen, PIPE
            cmd = [path, '-c', 'import sys;print sys.executable']
            p = Popen(cmd, stdout=PIPE)
            return p.communicate()[0].strip()
    return sys.executable


def human_bytes(n):
    """
    Return the number of bytes n in more human readable form.
    """
    if n < 1024:
        return '%i B' % n
    k = (n - 1) / 1024 + 1
    if k < 1024:
        return '%i KB' % k
    return '%.2f MB' % (float(n) / (2**20))

def makedirs(path):
    """Recursive directory creation function that does not fail if the
    directory already exists."""
    try:
        os.makedirs(path)
    except OSError as e:
        if e.errno != errno.EEXIST:
            raise

def ensure_dir(path):
    """
    Create the parent directory of the give path, recursively is necessary.
    """
    makedirs(os.path.dirname(path))

def is_zipinfo_symlink(zip_info):
    """Return True if the given zip_info instance refers to a symbolic link."""
    return zip_info.external_attr == ZIP_SOFTLINK_ATTRIBUTE_MAGIC

def zip_write_symlink(fp, link_name, source):
    """Add to the zipfile the given link_name as a softlink to source

    Parameters
    ----------
    fp: file object
        ZipFile instance
    link_name: str
        Path of the symlink
    source: str
        Path the symlink points to (the output of os.readlink)
    """
    zip_info = zipfile.ZipInfo(link_name)
    zip_info.create_system = 3
    zip_info.external_attr = ZIP_SOFTLINK_ATTRIBUTE_MAGIC
    fp.writestr(zip_info, source)
