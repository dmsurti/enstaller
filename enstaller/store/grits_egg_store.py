from enstaller import plat

from grits_client.storage.client_store import GritsClientStore

class GritsEggStore(GritsClientStore):
    def __init__(self, url):
        super(GritsEggStore, self).__init__(url)
        self.metadata_cache = {}

    def query(self, **kwargs):
        kwargs['platform'] = plat.custom_plat
        ret = [(self.egg_name(k), self._default_metadata(v))
               for k, v in super(GritsEggStore, self).query(**kwargs)]
        self.metadata_cache.update(dict(ret))
        return ret

    def get(self, egg):
        return super(GritsEggStore, self).get(self.key_name(egg))

    def get_data(self, egg):
        return super(GritsEggStore, self).get_data(self.key_name(egg))

    def get_metadata(self, egg):
        if egg in self.metadata_cache:
            return self.metadata_cache[egg]
        else:
            metadata = self._default_metadata(super(GritsEggStore, self).
                                              get_metadata(self.key_name(egg)))
            self.metadata_cache[egg] = metadata
            return metadata

    @staticmethod
    def _default_metadata(metadata):
        metadata = metadata.copy()
        metadata.setdefault('type', 'egg')
        metadata.setdefault('python', '2.7')
        metadata.setdefault('packages', [])
        return metadata

    @staticmethod
    def egg_name(key):
        return key.split('/')[-1]

    @staticmethod
    def key_name(egg):
        return 'enthought/eggs/{}/{}'.format(plat.custom_plat, egg)
