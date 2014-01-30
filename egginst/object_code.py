# Changes library path in object code (ELF and Mach-O).

import logging
import sys
import re
from os.path import abspath, join, islink, isfile, exists

logger = logging.getLogger(__name__)

verbose = False

# alt_replace_func is an optional function, which is applied to the
# replacement string (after the placeholders haven substituted)
alt_replace_func = None


# extensions which are assumed to belong to files which don't contain
# object code
NO_OBJ = ('.py', '.pyc', '.pyo', '.h', '.a', '.c', '.txt', '.html', '.xml',
          '.png', '.jpg', '.gif')

MAGIC = {
    '\xca\xfe\xba\xbe': 'MachO-universal',
    '\xce\xfa\xed\xfe': 'MachO-i386',
    '\xcf\xfa\xed\xfe': 'MachO-x86_64',
    '\xfe\xed\xfa\xce': 'MachO-ppc',
    '\xfe\xed\xfa\xcf': 'MachO-ppc64',
    '\x7fELF': 'ELF',
}

# list of target direcories where shared object files are found
_targets = []


def get_object_type(path):
    """
    Return the object file type of the specified file (not link).
    Otherwise, if the file is not an object file, returns None.
    """
    if path.endswith(NO_OBJ) or islink(path) or not isfile(path):
        return None
    fi = open(path, 'rb')
    head = fi.read(4)
    fi.close()
    return MAGIC.get(head)


def find_lib(fn):
    for tgt in _targets:
        dst = abspath(join(tgt, fn))
        if exists(dst):
            return dst
    logger.error("ERROR: library %r not found" % fn)
    return join('/ERROR/path/not/found', fn)


def macho_path_as_data(path, pad_to=4):
    """ Encode a path as data for a MachO header.

    Namely, this will encode the text according to the filesystem
    encoding and zero-pad the result out to 4 bytes.
    """
    from egginst.macho.util import fsencoding
    path = fsencoding(path) + b'\x00'
    rem = len(path) % pad_to
    if rem > 0:
        path += b'\x00' * (pad_to - rem)
    return path

def macho_add_rpath_to_header(header, rpath):
    """ Add an LC_RPATH load command to a MachOHeader.
    """
    from egginst.macho import mach_o
    from egginst.macho.ptypes import sizeof
    if header.header.magic in (mach_o.MH_MAGIC, mach_o.MH_CIGAM):
        pad_to = 4
    else:
        pad_to = 8
    data = macho_path_as_data(rpath, pad_to=pad_to)
    header_size = sizeof(mach_o.load_command) + sizeof(mach_o.rpath_command)
    command_size = header_size + len(data)
    cmd = mach_o.rpath_command(header_size, _endian_=header.endian)
    lc = mach_o.load_command(mach_o.LC_RPATH, command_size,
        _endian_=header.endian)
    header.commands.append((lc, cmd, data))
    header.header.ncmds += 1
    header.changedHeaderSizeBy(command_size)

def macho_delete_placehold(header):
    """ Remove LC_RPATH commands that refer to /PLACEHOLD.
    """
    from egginst.macho import mach_o
    to_delete = []
    for lc, cmd, data in header.commands:
        if lc.cmd == mach_o.LC_RPATH and data.startswith('/PLACEHOLD'):
            to_delete.append((lc, cmd, data))
    for l_c_d in to_delete:
        header.commands.remove(l_c_d)
        header.header.ncmds -= 1
        header.changedHeaderSizeBy(-l_c_d[0].cmdsize)

def macho_add_rpaths_to_file(filename, rpaths):
    """ Add LC_RPATH load commands to all headers in a MachO file.
    """
    from egginst.macho import MachO
    macho = MachO.MachO(filename)
    for header in macho.headers:
        macho_delete_placehold(header)
        for rpath in rpaths:
            macho_add_rpath_to_header(header, rpath)
    with open(filename, 'rb+') as f:
        for header in macho.headers:
            f.seek(0)
            header.write(f)

placehold_pat = re.compile(5 * '/PLACEHOLD' + '([^\0\\s]*)\0')
def fix_object_code(path):
    tp = get_object_type(path)
    if tp is None:
        return
    
    f = open(path, 'r+b')
    data = f.read()
    matches = list(placehold_pat.finditer(data))
    if not matches:
        f.close()
        return

    if verbose:
        logger.info("Fixing placeholders in:", path)
    for m in matches:
        rest = m.group(1)
        original_r = rest
        while rest.startswith('/PLACEHOLD'):
            rest = rest[10:]

        if tp.startswith('MachO-') and rest.startswith('/'):
            # If the /PLACEHOLD is found in a LC_LOAD_DYLIB command
            r = find_lib(rest[1:])
        else:
            # If the /PLACEHOLD is found in a LC_RPATH command (Mach-O) or in
            # R(UN)PATH on ELF
            assert rest == '' or rest.startswith(':')
            rpaths = list(_targets)
            # extend the list with rpath which were already in the binary,
            # if any
            rpaths.extend(p for p in rest.split(':') if p)
            r = ':'.join(rpaths)

        if verbose:
            logger.info("replacing rpath {} with {}".format(original_r, r))
        if alt_replace_func is not None:
            r = alt_replace_func(r)

        padding = len(m.group(0)) - len(r)
        if padding < 1: # we need at least one null-character
            raise Exception("placeholder %r too short" % m.group(0))
        r += padding * '\0'
        assert m.start() + len(r) == m.end()
        f.seek(m.start())
        f.write(r)
    f.close()


def fix_files(egg):
    """
    Tries to fix the library path for all object files installed by the egg.
    """
    global _targets

    prefixes = [egg.prefix] if egg.prefix != abspath(sys.prefix) else [sys.prefix]

    _targets = []
    for prefix in prefixes:
        for line in egg.lines_from_arcname('EGG-INFO/inst/targets.dat'):
            _targets.append(join(prefix, line))
        _targets.append(join(prefix, 'lib'))

    if verbose:
        logger.info('Target directories:')
        for tgt in _targets:
            logger.info('    %r' % tgt)

    for p in egg.files:
        fix_object_code(p)
