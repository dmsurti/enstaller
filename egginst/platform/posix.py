#
# (C) Copyright 2012 Enthought, Inc., Austin, TX
# All right reserved.
#
# This file is open source software distributed according to the terms in
# LICENSE.txt
#

import sys

name = 'posix'

is_win = False

bin_dir_name = 'bin'

# XXX this will cause problems if we ever are installing into a different
# Python's site packages...
rel_site_packages = ('lib', 'python%i.%i' % sys.version_info[:2], 'site-packages')

def remove_file(path):
    """ Remove or unlink a file or directory
    
    """
    import os
    if os.path.isdir(path):
        import shutil
        shutil.rmtree(path)
    else:
        os.unlink(path)

def install_file(base_path, src, target):
    """ Create a link to the src called target
    
    """
    import os
    if target == 'False':
        return []
    
    if not os.path.isdir(os.path.dirname(target)):
        os.makedirs(os.path.dirname(target))
    
    if os.path.exists(target):
        remove_file(target)
    
    src_path = os.path.join(base_path, *src)
    os.symlink(target, src_path)
    return [target]

def script_extras(path, name, script_type):
    """ Not used on posix
    
    """
    return []
    

def get_executable(gui=False):
    """ Return the python executable
    
    The gui argument is ignored on posix systems.
    
    """
    import sys
    return sys.executable

