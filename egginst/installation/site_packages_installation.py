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
import shutil
import tempfile

from .abstract_installation import AbstractInstallation

python_pat = re.compile(r'(.+)\.py(c|o)?$')
namespace_package_pat = re.compile(
    r'\s*__import__\([\'"]pkg_resources[\'"]\)\.declare_namespace'
    r'\(__name__\)\s*$')

def is_namespace(data):
    return namespace_package_pat.match(data) is not None

entry_point_template = '''\
#!%(executable)s
# This script was created by egginst when installing:
#
#   %(egg_name)s
#
if __name__ == '__main__':
    import sys
    from %(module)s import %(attrs)s

    sys.exit(%(attrs)s())
'''

class SitePackagesInstallation(AbstractInstallation):
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
    
    def __init__(self, path=sys.prefix, platform=None, interpreter=None):
        self.path = os.path.abspath(path)
        if platform is None:
            from ..platform import get_platform
            platform = get_platform()
        self.platform = platform
        
        if interpreter is None:
            pass
        
        # sub-path tuples
        self.py_path = self.platform.rel_site_packages
        self.egginfo_path = ('EGG-INFO',)
        self.bin_dir = (self.platform.bin_dir_name,)

    # implementation API
    
    def remove_old(self, metadata):
        """ Remove the egginst.json file from any old egg info
        
        Ideally this should have been removed by enstaller prior to this being
        called, but we are using the existence of this file as a flag for a
        successful install within the egginst world.
        
        """
        rel_path = self.egginfo_path + (metadata.cname, 'egginst.json')
        meta_json = os.path.join(self.path, *rel_path)
        if os.path.isfile(meta_json):
            self._remove(meta_json)
    
    def write_files(self, package, metadata):
        """ Write all files in the package to the installation
        
        """
        files_written = []
        for path in package:
            if self.skip_file(package, path):
                continue
            classification, dest_path = self.get_dest_path(path, metadata)
            self.write_file(package, path, dest_path)
            files_written.append(dest_path)
            
            files_written += self.handle_classification(classification, dest_path)
            
            if metadata.is_executable(path):
                os.chmod(os.path.join(self.path, *dest_path), 0755)
        
        return files_written
    
    def install_executables(self, bundle, metadata):
        """ Install executable files in locations as directed by metadata
        
        """
        files_written = []
        for path, target in metadata.get_executables(bundle):
            dest_path = self.get_dest_path(path, metadata)
            files_written += self.platform.link_executable(self.path, dest_path,
                target, self.interpreter)
        return files_written
        
    def patch_object_code(self, bundle, metadata, files):
        """ Patch object code to replace placeholder paths
        
        """
        targets = [os.path.join(self.path, path)
            for path in metadata.get_library_dirs(bundle)]
        for path in files:
            self.platform.fix_object_code(os.path.join(self.path, *path), targets)

    def install_scripts(self, package, metadata):
        """ Install all entry point scripts
        
        """
        files_written = []
        for script_type, scripts in metadata.get_scripts(package).items():
            for name, entry_point in scripts.items():
                fname = self.platform.script_name(name, script_type)
                self.write_script(fname, metadata.egg_name, script_type)
                files_written.append(fname)
                files_written += self.platform.script_extras(name, script_type)
        return files_written
    
    def install_app(self, metadata):
        rel_path = self.egginfo_path + (metadata.cname, 'inst', 'appinst.dat')
        path = os.path.join(self.path, *rel_path)
        if os.path.isfile(path):
            try:
                import appinst
                appinst.install_from_dat(path)
            except ImportError:
                # XXX probably should log this...
                return
            except Exception as exc:
                # XXX should log properly
                print 'Error installing app:', exc
    
    def uninstall_app(self, metadata):
        path = os.path.join(self.egginfo_path, metadata.cname, 'inst',
            'appinst.dat')
        if sys.path.isfile(path):
            try:
                import appinst
                appinst.uninstall_from_dat(path)
            except ImportError:
                return
            except Exception as exc:
                # XXX should log properly
                print 'Error uninstalling app:', exc
    
    def write_metadata(self, bundle, metadata, files):
        """ Write out installation metadata
        
        This is used by tools that gather information about the state of the
        Installation, and by the uninstall method.
        
        """
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
        
        

    def post_install(self, metadata):
        rel_path = self.egginfo_path + (metadata.cname, 'post_egginst.py')
        path = os.path.join(self.path, *rel_path)
        self.run(path)
   
    # private API 
            
    def get_dest_path(self, path, metadata):
        destinations = {
            'pkg_info': self.py_path,
            'prefix': (),
            'script': self.bin_dir,
            'metadata': self.egginfo_path + (metadata.cname,),
            'default': self.py_path,
        }

        for classification in ('pkg_info', 'prefix', 'script', 'metadata'):
            test = getattr(metadata, 'is_'+classification,
                lambda path, platform: None)
            result = test(path, self.platform)
            if result is not None:
                self.handle_classification(classification, result)
                break
        else:
            classification = 'default'
            result = path
        
        print destinations[classification], result
        return classification, destinations[classification] + result
    
    
    def skip_file(self, package, path):
        """ Should we skip this file?
        
        """
        # skip directories and certain patterns which indicate an unused file
        if path[0].startswith('.unused'):
            return True
        
        # skip .py and .pyc which are next to a .so or .pyd
        match = python_pat.match(path[-1])
        if match:
            corresponding_pylib = path[:-1] + (match.group(1) +
                    self.platform.pylib_ext,)
            if corresponding_pylib in package:
                return True
        
        # skip __init__.pyc files if corresponding __init__.py is a namespace package
        if path[-1] == '__init__.pyc':
            init = path[:-1] + (path[-1][:-1],)
            if init in package and is_namespace(package.get_bytes(init)):
                return True


    def write_file(self, package, path, dest_path):
        
        actual_path = os.path.join(self.path, *dest_path)
        # remove contents if __init__.py is a namespace package
        if path[-1] == '__init__.py' and is_namespace(package.get_bytes(path)):
            data = cStringIO.StringIO('')
        else:
            data = package.open(path)
        
        try:
            # ensure that directory exists
            directory, filename = os.path.split(actual_path)
            if os.path.exists(directory) and not os.path.isdir(directory):
                self._remove(directory)
            try:
                os.makedirs(directory)
            except OSError as exc:
                if exc.errno != errno.EEXIST or not os.path.isdir(directory):
                    raise
            
            # blow away old file if it exists
            self._remove(actual_path)
            
            with open(actual_path, 'wb') as fp:
                while True:
                    bytes = data.read(1<<20)
                    if not bytes:
                        break
                    fp.write(bytes)
        finally:
            data.close()
            
    def write_script(self, fname, egg_name, entry_point):
        script = entry_point_template % dict(
            egg_name=egg_name,
            module=entry_point['module'],
            importable=entry_point['attr'].split('.')[0],
            callable=entry_point['attr'],
            executable=self.executable,
        )
        
    def run(self, path):
        if not os.path.isfile(path):
            return
        from subprocess import call
        call([sys.executable, '-E', path, '--prefix', self.prefix],
             cwd=os.path.dirname(path))
    
    def handle_classification(self, classification, path):
        """ Do any special-processing needed by a particular type of file
        
        """
        return getattr(self, 'handle_'+classification, lambda path: ())(path)
    
    def handle_script(self, path):
        """ For directly installed scripts (as opposed to entry points) we need
        to hardcode the correct Python interpreter in the #!
        
        """
        
        return []
    
    def _remove(self, path):
        # we want the actual platform here so we do the right file ops
        if not os.path.exists(path):
            return
        from ..platform import get_platform
        platform = get_platform()
        platform.remove_file(path)
