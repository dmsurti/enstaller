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

from .abstract_installation import AbstractInstallation

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
    
    def __init__(self, path=sys.prefix, platform=None, interpreters=None):
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
        self.py_path = self.platform.rel_site_packages
        self.egginfo_path = ('EGG-INFO',)
        self.bin_dir = self.platform.bin_dir
        
        logger.debug('New SitePackagesInstallation() object for "%s" % self.path')

    # Public API
        
    def uninstall(self, cname):
        """ Remove a package from this installation
        
        """
        metadata = self.read_meta(cname)
        files = [os.path.join(self.path, *path.split('/')[1:])
            for path in metadata['files']]
        dirs = set(tuple(path.split('/')[1:-1]) for path in metadata['files'])
        
        self.uninstall_app(cname)
        for file in files:
            self._remove(file)
            if file.endswith('.py'):
                self._remove(file+'c')
                self._remove(file+'o')
        
        for dir in dirs:
            self._remove_empty(dir)
        
        self._remove_empty(self.egginfo_path)
    
    def get_installed(self):
        """ Return an iterator of all installed packages
        
        """
        egg_info_dir = os.path.join(self.path, *self.egginfo_path)
        if not os.path.isdir(egg_info_dir):
            return
        pat = re.compile(r'([a-z0-9_.]+)$')
        for cname in sorted(os.listdir(egg_info_dir)):
            if not pat.match(cname):
                continue
            d = self.read_meta(cname)
            if d is None:
                continue
            yield d['egg_name']

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
            logger.info('Removing old egginst.json "%s" from installation at "%s"'
                % (metadata.cname, self.path))
            self._remove(meta_json)
    
    def write_files(self, package, metadata):
        """ Write all files in the package to the installation
        
        """
        logger.info('Writing files for "%s" to installation at "%s"'
            % (metadata.egg_name, self.path))
        files_written = []
        for path in package:
            if self.skip_file(package, path):
                logger.debug("skipping '%s'" % '/'.join(path))
                continue
            classification, dest_path = self.get_dest_path(path, metadata)
            self.write_file(package, path, dest_path)
            files_written.append(dest_path)
            
            files_written += self.handle_classification(classification, dest_path)
            
            if metadata.is_executable(path):
                logger.debug('chmod %s 0755' % '/'.join(dest_path))
                os.chmod(os.path.join(self.path, *dest_path), 0755)
        
        return files_written
    
    def install_executables(self, bundle, metadata):
        """ Install executable files in locations as directed by metadata
        
        """
        logger.info('Installing executables for "%s" in installation at "%s"'
            % (metadata.egg_name, self.path))
        files_written = []
        for path, target in metadata.get_executables(bundle):
            dest_path = self.get_dest_path(path, metadata)
            files_written += self.platform.link_executable(self.path, dest_path,
                target, self.interpreter)
        return files_written
        
    def patch_object_code(self, bundle, metadata, files):
        """ Patch object code to replace placeholder paths
        
        """
        logger.info('Patching object code for "%s" in installation at "%s"'
            % (metadata.egg_name, self.path))
        targets = [os.path.join(self.path, path)
            for path in metadata.get_library_dirs(bundle)]
        for path in files:
            self.platform.fix_object_code(os.path.join(self.path, *path), targets)

    def install_scripts(self, package, metadata):
        """ Install all entry point scripts
        
        """
        logger.info('Installing scripts for "%s" in installation at "%s"'
            % (metadata.egg_name, self.path))
        bin_dir = os.path.join(self.path, *self.bin_dir)
        files_written = []
        for script_type, scripts in metadata.get_scripts(package).items():
            for name, entry_point in scripts.items():
                if not os.path.exists(bin_dir):
                    os.makedirs(bin_dir)
                fname = self.platform.script_name(name, script_type)
                self.write_script(bin_dir, fname, metadata.egg_name, script_type, entry_point)
                files_written.append(self.bin_dir + (fname,))
                files_written += self.platform.script_extras(bin_dir, name, script_type)
        return files_written
    
    def install_app(self, metadata):
        """ Run appinst to do additional installation for the package
        
        """
        rel_path = self.egginfo_path + (metadata.cname, 'inst', 'appinst.dat')
        path = os.path.join(self.path, *rel_path)
        if os.path.isfile(path):
            logger.info('Installing apps for "%s" in installation at "%s"'
                % (metadata.egg_name, self.path))
            try:
                import appinst
            except ImportError:
                logger.error('Could not import appinst, skipping')

            try:
                appinst.install_from_dat(path)
            except Exception as exc:
                logger.error('Error installing app for "%s" in installation at "%s"'
                    % (metadata.egg_name, self.path))
                logger.exception(exc)
                # XXX should we perhaps just fail here?
    
    def uninstall_app(self, cname):
        """ Run appinst to do additional uninstallation for the package
        
        """
        path = os.path.join(self.egginfo_path, cname, 'inst',
            'appinst.dat')
        if sys.path.isfile(path):
            logger.info('Uninstalling apps for "%s" in installation at "%s"'
                % (cname, self.path))
            try:
                import appinst
            except ImportError:
                logger.error('Could not import appinst, skipping')

            try:
                appinst.uninstall_from_dat(path)
            except Exception as exc:
                logger.error('Error installing app for "%s" in installation at "%s"'
                    % (cname, self.path))
                logger.exception(exc)
                # XXX should we perhaps just fail here?
    
    def write_metadata(self, bundle, metadata, files):
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
        info['hook'] = False
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
        
    def read_meta(self, cname):
        """ Read the metadata for the package defined by cname
        
        If it does not exist, return None
        
        """
        egg_info_dir = os.path.join(self.path, *self.egginfo_path)
        meta_json = os.path.join(egg_info_dir, cname, 'egginst.json')
        if os.path.isfile(meta_json):
            logger.debug('reading metadata at "%s"' % meta_json)
            return json.load(open(meta_json))
        logger.debug('no metadata for "%s"' % cname)
        return None

    def post_install(self, metadata):
        rel_path = self.egginfo_path + (metadata.cname, 'post_egginst.py')
        path = os.path.join(self.path, *rel_path)
        if os.path.exists(path):
            logger.info('Running post install script for "%s" in installation at "%s"'
                % (metadata.egg_name, self.path))
            self.run(path)
   
    # private API 
            
    def get_dest_path(self, path, metadata):
        """ Get the appropriate path for this file.
        
        """
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
        """ Write the data from a bundle entry into a file
        
        """
        actual_path = os.path.join(self.path, *dest_path)
        # remove contents if __init__.py is a namespace package
        if path[-1] == '__init__.py' and is_namespace(package.get_bytes(path)):
            logger.info("ignoring namespace packages for '%s'" % '.'.join(path[:-1]))
            data = cStringIO.StringIO('')
        else:
            data = package.open(path)
        
        try:
            # ensure that directory exists
            directory, filename = os.path.split(actual_path)
            if os.path.exists(directory) and not os.path.isdir(directory):
                self._remove(directory)
            try:
                logger.debug("creating directory '%s'" % directory)
                os.makedirs(directory)
            except OSError as exc:
                if exc.errno != errno.EEXIST or not os.path.isdir(directory):
                    raise
            
            # blow away old file if it exists
            self._remove(actual_path)

            logger.debug("writing '%s' to '%s'" % ('/'.join(path), actual_path))
            
            with open(actual_path, 'wb') as fp:
                while True:
                    bytes = data.read(1<<20)
                    if not bytes:
                        break
                    fp.write(bytes)
        finally:
            data.close()
            
    def write_script(self, path, fname, egg_name, script_type, entry_point):
        """ Write an entry point script to the specified path
        
        """
        script = entry_point_template % dict(
            egg_name=egg_name,
            module=entry_point['module'],
            importable=entry_point['attrs'].split('.')[0],
            callable=entry_point['attrs'],
            executable=self.interpreters[script_type],
        )
        logger.debug("writing entry point script '%s' to '%s'" % (fname, path))
        with open(os.path.join(path, fname), 'w') as fp:
            fp.write(script)
        os.chmod(path, 0755)
        
    def run(self, path):
        """ Run the script at the path
        
        """
        if not os.path.isfile(path):
            return
        from subprocess import call
        logger.debug("running '%s'" % path)
        # XXX should we run this with self.interpreters['console_script'] instead?
        # XXX should we capture stdout/stderr?
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
        src_path = os.path.join(self.path, *path)
        if os.path.islink(src_path) or not os.path.isfile(src_path):
            return []
        with open(src_path) as fp:
            code = fp.read()
        match = hashbang_pat.match(code)
        if match is None or 'python' not in match.group().lower():            
            return []
        
        python = self.platform.get_executable()
        if self.platform.is_win:
            python = '"'+python+'"'
        new_code = hashbang_pat.sub('#!'+python.replace('\\', r'\\'), code,
            count=1)
        logger.debug("updating #! executable in '%s'" % src_path)
        with open(src_path, 'w') as fp:
            fp.write(new_code)
    
    def _remove(self, path):
        # we want the actual platform here so we do the right file ops
        if not os.path.exists(path):
            return
        from ..platform import get_platform
        platform = get_platform()
        platform.remove_file(path)
    
    def _remove_empty(self, directory):
        """ Remove a directory if it is empty
        
        """
        try:
            logger.debug("attempting to remove directory '%s'" % directory)
            os.rmdir(directory)
        except OSError as exc: # directory might not exist or not be empty
            logger.info("directory '%s' not empty or otherwise unable to remove:"
                % directory)
            logger.info(exc)
            pass
