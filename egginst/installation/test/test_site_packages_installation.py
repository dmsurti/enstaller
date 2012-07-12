#
# (C) Copyright 2012 Enthought, Inc., Austin, TX
# All right reserved.
#
# This file is open source software distributed according to the terms in
# LICENSE.txt
#

from .test_installation import InstallationTestCase
from ..site_packages_installation import SitePackagesInstallation

class SitePackagesInstallationTestCase(InstallationTestCase):
    
    def test_basic_install(self):
        from egginst.bundle.zip_bundle import ZipBundle
        from egginst.metadata.egg_metadata import EggMetadata
        target_path = 'test_installation'
        import glob
        for egg in glob.glob('*.egg'):
            bundle = ZipBundle(egg)
            metadata = EggMetadata(egg)
            installation = SitePackagesInstallation(target_path)
        
            installation.install(bundle, metadata)
        

    def test_old_inst(self):
        from egginst.main import EggInst
        import glob
        for egg in glob.glob('*.egg'):
            egginst = EggInst(egg, 'test_old_installation')
            egginst.install()
