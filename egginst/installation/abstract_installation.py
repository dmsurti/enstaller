#
# (C) Copyright 2012 Enthought, Inc., Austin, TX
# All right reserved.
#
# This file is open source software distributed according to the terms in
# LICENSE.txt
#


class AbstractInstallation(object):
    
    # public API

    def install(self, bundle, metadata, extra_info=None):
        """ Install a package into this installation
        
        """
        self.remove_old(metadata)
        files = self.write_files(bundle, metadata)
        files += self.install_executables(bundle, metadata)
        files += self.install_scripts(bundle, metadata)
        self.patch_object_code(bundle, metadata, files)
        self.install_app(metadata)
        self.post_install(metadata)
        # last action is to write metadata - failure before this point means a
        # bad install
        self.write_metadata(bundle, metadata, files)

    
    def uninstall(self, egg_name):
        """ Remove a package from this installation
        
        """
        raise NotImplementedError
    
    def get_installed(self):
        """ Return a list of all installed packages
        
        """
        raise NotImplementedError
        
    
    # implementation API
    
    def remove_old(self, metadata):
        """ Remove any old metadata for other versions of this package
        
        As far as a particular installation should be concerned, from this
        point until the commit_install method runs, the package we are trying
        to install is not in the system.
        
        This remove operation should be atomic - either it succeeds, or it
        leaves the old metadata intact, and raises an exception.  It does not
        need to be comprehensive - enstaller and other similar packages are
        responsible for ensuring the uninstall method of the public API is
        called before installing a new version of the API.  This method just
        needs to ensure that whatever method the installation uses to track
        installed packages is absolutely clear of data.
        
        """
        raise NotImplementedError
    
    def write_files(self, package, metadata):
        """ Write all the files from the package into the correct locations
        
        This should also ensure that permissions are correct, if not otherwise
        specified.
        
        This method should generate appropriate progress events for use by
        encore.events listeners.
        
        It should return a manifest of all the files installed, or fail with an
        appropriate exception.
        
        """
        raise NotImplementedError
        
    def install_executables(self, bundle, metadata):
        """ Install executable files in locations as directed by metadata
        
        """
        raise NotImplementedError    
        
    def patch_object_code(self, metadata, files):
        """ Patch object code to replace placeholder paths
        
        """
        raise NotImplementedError    
    
    def install_scripts(self, metadata):
        """ Ensure that script entry-points work
        
        """
        raise NotImplementedError    
    
    def install_app(self, metadata):
        """ Call out to appinst to install any applications that may exist
        
        """
        raise NotImplementedError    
            
    def post_install(self, metadata):
        """ Run post_install.py, if it exists
        
        """
        raise NotImplementedError    
    
    def write_metadata(self, bundle, metadata, files):
        """ Assuming all else works, finalize the installation
        
        The command which performs the finalization should be atomic.  Until it
        is complete, the system should treat the package as not being installed
        (even if it is otherwise visible and usable from Python).
        
        """
        raise NotImplementedError    
