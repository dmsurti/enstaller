#
# (C) Copyright 2012 Enthought, Inc., Austin, TX
# All right reserved.
#
# This file is open source software distributed according to the terms in
# LICENSE.txt
#

import sys
import os
import re
import errno
import json
import cStringIO
import time
import logging

from encore.events.api import ProgressManager

from .site_packages_installation import SitePackagesInstallation

# set up logger
logger = logging.getLogger(__name__)

python_pat = re.compile(r'(.+)\.py(c|o)?$')
namespace_package_pat = re.compile(
    r'\s*__import__\([\'"]pkg_resources[\'"]\)\.declare_namespace'
    r'\(__name__\)\s*$')
hashbang_pat = re.compile(r'#!.+$', re.M)

def is_namespace(data):
    return namespace_package_pat.match(data) is not None

entry_point_template = '''\
#!%(executable)s
# This script was created by egginst when installing:
#
#   %(egg_name)s.egg
#
if __name__ == '__main__':
    import sys
    from %(module)s import %(importable)s

    sys.exit(%(callable)s())
'''

class ImportHookInstallation(SitePackagesInstallation):
    """ This is a standard install target in site packages
    
    Internally, until the point where files are written, everything is a tuple
    relative to the base path.
    
    Notes
    =====
    
    This is intended to be bug-for-bug compatible with the current enstaller
    behaviour.
    
    The file layout that this produces looks like this::
        
        <path>/
            EGG-INFO/
                foo/
                    egginst.json
                    ... egg info metadata for package foo ...
                bar/
                    egginst.json
                    ... egg info metadata for package bar ...
            <platform.bin_dir_name>/
                ... scripts from foo, bar, etc. ...
            <platform.site_packages>/
                foo.egginfo
                foo/
                    __init__.py
                    ... foo's files ...
                bar.egginfo
                bar/
                    __init__.py
                    ... bar's files
    
    """
    
    def __init__(self, path=sys.prefix, packages_path=None, platform=None, interpreters=None):
        self.path = os.path.abspath(path)
        if platform is None:
            from ..platform import get_platform
            platform = get_platform()
        self.platform = platform
        
        if interpreters is None:
            interpreters = {
                'console_scripts': self.platform.get_interpreter(),
                'gui_scripts': self.platform.get_interpreter(gui=True)
            }
        elif isinstance(interpreters, basestring):
            interpreters = {
                'console_scripts': interpreters,
                'gui_scripts': interpreters
            }
        self.interpreters = interpreters
        
        # sub-path tuples
        self.packages_path = packages_path if packages_path is not None else ('pkgs',)
        self.py_path = self.packages_path
        self.egginfo_path = self.packages_path+('EGG-INFO',)
        self.bin_dir = self.platform.bin_dir
        self.registry_txt = self.egginfo_path+('registry.txt')
        
        logger.debug('New ImportHookInstallation() object for "%s" % self.path')

    # Public API
        
    def uninstall(self, cname):
        """ Remove a package from this installation
        
        """
        metadata = self.read_meta(cname)
        files = [os.path.join(self.path, *path.split('/')[1:])
            for path in metadata['files']]
        dirs = set(tuple(path.split('/')[1:-1]) for path in metadata['files'])
        
        progress = ProgressManager(
            message="uninstalling egg",
            steps=len(files) + len(dirs),
            progress_type="uninstalling",
        )
        completion = 0

        with progress:
            self.uninstall_app(cname)
            for file in files:
                self._remove(file)
                if file.endswith('.py'):
                    self._remove(file+'c')
                    self._remove(file+'o')
                completion += 1
                progress(step=completion)
            
            for dir in dirs:
                self._remove_empty(dir)
                completion += 1
                progress(step=completion)
            
            self._remove_empty(self.egginfo_path)

    # implementation API
    
    def install_scripts(self, package, metadata, progress):
        """ Install all entry point scripts
        
        """
        # don't install entry point scripts when using install hooks
        return []
    
    def install_app(self, metadata, progress):
        """ Run appinst to do additional installation for the package
        
        """
        # don't install apps when using install hooks
        pass
    
    def uninstall_app(self, cname, progress):
        """ Run appinst to do additional uninstallation for the package
        
        """
        # don't uninstall apps when using install hooks
        pass
    
    def write_metadata(self, bundle, metadata, files, progress):
        """ Write out installation metadata
        
        This is used by tools that gather information about the state of the
        Installation, and by the uninstall method.
        
        """
        logger.info('Writing metadata for "%s" in installation at "%s"'
            % (metadata.egg_name, self.path))
        rel_path = self.egginfo_path + (metadata.cname,)
        meta_dir = os.path.join(self.path, *rel_path)
        try:
            os.makedirs(meta_dir)
        except OSError as exc:
            if exc.errno != errno.EEXIST:
                raise
        
        # XXX why do we have 2 different metadata files?
        meta_info = os.path.join(meta_dir, '_info.json')
        info = metadata.get_metadata(bundle)
        info['ctime'] = time.ctime() #FIXME: timestamps should be UTC!
        info['hook'] = True
        info['type'] = 'egg'
        with open(meta_info, 'wb') as f:
            json.dump(info, f, indent=2, sort_keys=True)
        
        meta_json = (rel_path) + ('egginst.json',)
        meta = {
            'egg_name': metadata.filename,
            'prefix': os.path.abspath(self.path),
            'installed_size': bundle.installed_size,
            'files': [('./'+'/'.join(path)) for path in files] +
                [os.path.join('.', *meta_json)]
        }
        with open(os.path.join(self.path, *meta_json), 'wb') as f:
            json.dump(meta, f, indent=2, sort_keys=True)        

        import registry
        registry.create_file(self)
        
    # private API 
            
    def get_dest_path(self, path, metadata):
        """ Get the appropriate path for this file.
        
        """
        destinations = {
            'prefix': (),
            'script': self.bin_dir,
            'metadata': self.egginfo_path + (metadata.cname,),
            'default': self.py_path,
        }

        for classification in ('prefix', 'script', 'metadata'):
            test = getattr(metadata, 'is_'+classification,
                lambda path, platform: None)
            result = test(path, self.platform)
            if result is not None:
                self.handle_classification(classification, result)
                break
        else:
            classification = 'default'
            result = path
        
        return classification, destinations[classification] + result
    
    def handle_script(self, path):
        """ For directly installed scripts (as opposed to entry points) we need
        to hardcode the correct Python interpreter in the #!
        
        """
        # don't do this for install hooks scripts
        pass
