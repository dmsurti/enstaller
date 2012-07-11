#
# (C) Copyright 2012 Enthought, Inc., Austin, TX
# All right reserved.
#
# This file is open source software distributed according to the terms in
# LICENSE.txt
#

# standard library imports
import os
import re
import json

# local imports
from .abstract_metadata import AbstractMetadata

python_pat = re.compile(r'(.+)\.py(c|o)?$')
namespace_package_pat = re.compile(
    r'\s*__import__\([\'"]pkg_resources[\'"]\)\.declare_namespace'
    r'\(__name__\)\s*$')

def is_namespace(data):
    return namespace_package_pat.match(data) is not None

entry_point_section_pat = re.compile('^\[(?P<section>[^\]]*)\]$')
entry_point_pat = re.compile(r'(?P<name>\S+)\s*=\s*(?P<module>(\w|\.)+)'+
    '(:(?P<attrs>(\w|\.)+)(\s+\[(?P<extras>[^\]]*)\])?)?')
    
class EggMetadata(AbstractMetadata):
    """ Metadata for a self-contained egg
    
    This metadata knows about Enthought eggs arranged as a self-contained
    bundle with the EGG-INFO directory inside the main bundle location.
    
    """
    
    def __init__(self, filename):
        self.filename = filename
        self.egg_name = os.path.splitext(self.filename)[0]
        self.name, self.version = self.egg_name.split('-', 1) \
                if '-' in self.egg_name else (self.egg_name, '')
        self.cname = self.name.lower()
        
    
    def is_pkg_info(self, path, platform):
        """ This file is the special PKG-INFO file
        
        """
        if path == ('EGG-INFO', 'PKG-INFO'):
            return (self.egg_name + '.egg-info',)
        return None
    
    def is_prefix(self, path, platform):
        """ This file should be placed relative to sys.prefix or its analogue
        
        """
        if path[:2] == ('EGG-INFO', 'prefix') or (not platform.is_win and
                path[:2] == ('EGG-INFO', 'usr')):
            return path[2:]
        return None
    
    def is_script(self, path, platform):
        """ This file is an executable script
        
        """
        if path[:2] == ('EGG-INFO', 'scripts'):
            return path[2:]
        return None
    
    def is_metadata(self, path, platform):
        """ This file is general metadata
        
        """
        if path[0] == 'EGG-INFO':
            return path[1:]
        return None

    def is_executable(self, path):
        """ Should the file at this location have its executable flag set?
        
        For Enthought eggs, the basic test is:
            
            * is it in the EGG-INFO's usr/bin or scripts subdirectory?
            * does it end with standard shared library extensions?
            * does it match the pattern EGG-INFO/usr/lib/lib*.so?
        
        """
        if (path[:3] == ('EGG-INFO', 'usr', 'bin') or path[:2] == ('EGG-INFO',
                'scripts') or path[-1].endswith(('.dylib', '.pyd', '.so')) or 
                (path[:3] == ('EGG-INFO', 'usr', 'lib') and path[-1].startswith('lib')
                and path[-1].endswith('.so'))):
            return True
        return False
    
    def get_executables(self, bundle):
        """ Find the executables that need to be installed
        
        """
        executables_path = ('EGG-INFO', 'inst', 'files_to_install.txt')
        if executables_path in bundle:
            return self._parse_executables(bundle.get_bytes(executables_path))
        else:
            return []
    
    def get_library_dirs(self, bundle):
        """ Find the library dirs that contain files that need to be patched
        
        """
        libraries_path = ('EGG-INFO', 'inst', 'targets.dat')
        if libraries_path in bundle:
            return list(bundle.get_bytes(libraries_path).splitlines()) + ['lib']
        else:
            return ['lib']
    
    def get_scripts(self, bundle):
        """ Get the gui and console scripts from the entry_points.txt file
        
        """
        entry_points_path = ('EGG-INFO', 'entry_points.txt')
        if entry_points_path in bundle:
            entry_points = self._parse_entry_points(bundle.get_bytes(entry_points_path))
        else:
            entry_points = {}
            
        gui_scripts = entry_points.get('gui_scripts', {})
        console_scripts = entry_points.get('console_scripts', {})
        return {'gui_scripts': gui_scripts, 'console_scripts': console_scripts}
            

    def get_metadata(self, package):
        """ Extract egg info metadata from a variety of sources
        
        """
        metadata = dict(key=self.filename)
        
        # get basic dependency information
        if ('EGG-INFO', 'spec', 'depend') in package:
            metadata.update(self._parse_depend(package.get_bytes(('EGG-INFO',
                'spec', 'depend'))))
        
        # get info.json information
        if ('EGG-INFO', 'info.json') in package:
            metadata.update(json.loads(package.get_bytes(('EGG-INFO', 'info.json'))))
        
        # remove 'available' key if present
        # XXX copied from enstaller - why is this done?
        metadata.pop('available', None)
        
        return metadata
    
    def _parse_executables(self, data):
        return [line.split() for line in data.splitlines()]
            
    
    def _parse_entry_points(self, data):
        """ Simple parser for an entry points file
        
        This file is a text file with lines which are one of:
            
            [section_name]
                The name of a section
            
            name = module:attr.attr [extras]
                A name associated with a module and optional attrs and extras
        
        This documented more fully in the distribute docs.
        
        """
        sections = {}
        section = None
        for line in data.splitlines():
            print "'%s': " % line,
            text = line.strip()
            if text == '' or text.startswith('#'):
                print 'skip'
                continue
            m = entry_point_section_pat.match(text)
            if m is not None:
                section = m.groupdict()['section']
                sections.setdefault(section, {})
                print 'section', section
                continue
            
            if section is not None:
                m = entry_point_pat.match(text)
                if m is not None:
                    d = m.groupdict()
                    name = d.pop('name')
                    sections[section][name] = d
                    print 'name', name, 'data', d
                else:
                    # XXX bad entry point file - should at least log
                    print 'bad'
                    pass
        
        return sections
        
        
    def _parse_depend(self, data):
        """ Parse info for dependency analysis
        
        """
        namespace = {}
        # XXX exec seems fragile and dangerous - cjw
        exec data.replace('\r', '') in {}, namespace
        return dict((key, namespace[key]) for key in ('name', 'version',
            'build', 'arch', 'platform', 'osdist', 'python', 'packages'))

