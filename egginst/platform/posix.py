#
# (C) Copyright 2012 Enthought, Inc., Austin, TX
# All right reserved.
#
# This file is open source software distributed according to the terms in
# LICENSE.txt
#

import sys
import logging

# set up logger
logger = logging.getLogger(__name__)

name = 'posix'

is_win = False

bin_dir = ('bin',)

# XXX this will cause problems if we ever are installing into a different
# Python's site packages...
rel_site_packages = ('lib', 'python%i.%i' % sys.version_info[:2], 'site-packages')

pylib_ext = '.so'

def remove_file(path):
    """ Remove or unlink a file or directory
    
    """
    import os
    logging.debug("removing '%s'" % path)
    if os.path.isdir(path):
        import shutil
        shutil.rmtree(path)
    else:
        os.unlink(path)

def link_executable(base_path, src, target):
    """ Create a link to the src called target
    
    """
    import os
    if target == 'False':
        return []
    
    if not os.path.isdir(os.path.dirname(target)):
        logging.debug("creating directory '%s'" % os.path.dirname(target))
        os.makedirs(os.path.dirname(target))
    
    if os.path.exists(target):
        remove_file(target)
    
    src_path = os.path.join(base_path, *src)
    logging.debug("linking '%s' to '%s'" % (src_path, target))
    os.symlink(target, src_path)
    return [target]

def script_name(name, script_type):
    return name

def script_extras(path, name, script_type):
    """ Not used on posix
    
    """
    return []
    

def get_interpreter(gui=False):
    """ Return the python executable
    
    The gui argument is ignored on posix systems.
    
    """
    return sys.executable

def fix_object_code(path, targets):
    # XXX probably should bring this into this module
    from egginst.object_code import get_object_type, macho_add_rpaths_to_file, \
        placehold_pat, alt_replace_func
    
    tp = get_object_type(path)
    if tp is None:
        return
    if tp.startswith('MachO-'):
        # Use MachO-specific routines.
        logging.debug("fixing placeholders in MachO file '%s'" % path)
        rpaths = list(targets)
        macho_add_rpaths_to_file(path, rpaths)
        return

    f = open(path, 'r+b')
    data = f.read()
    matches = list(placehold_pat.finditer(data))
    if not matches:
        f.close()
        return

    logging.debug("fixing placeholders in file '%s'" % path)
    for m in matches:
        rest = m.group(1)
        while rest.startswith('/PLACEHOLD'):
            rest = rest[10:]

        assert rest == '' or rest.startswith(':')
        rpaths = list(targets)
        # extend the list with rpath which were already in the binary,
        # if any
        rpaths.extend(p for p in rest.split(':') if p)
        r = ':'.join(rpaths)

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
