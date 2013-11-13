import requests
import json

from encore.storage.dynamic_url_store import DynamicURLStore

from enstaller import plat

class GritsClientStore(DynamicURLStore):
    ''' Copied from grits_client.storage.client_store '''
    def __init__(self, url):
        self.url = clean_url(url)
        base_url = self.url + '/store'
        super(GritsClientStore, self).__init__(base_url, base_url)
        self.authenticated = False

    def connect(self, creds):
        self._session = requests.Session()

        if creds is not None:
            username, password = creds
            response = self._session.post(self.url + '/authenticate',
                                          data={'email': username,
                                                'password':password})

            response.raise_for_status()
            self.user_data = response.json()
            self._user_tag = self.user_data['user_tag']
            self.authenticated = True

        self._connected = True

    def is_connected(self):
        return self._connected

    def add_action(self, user_id, action_type, action_time, **details):
        action_dict = {"user_id": user_id,
                       "action_type": action_type,
                       "action_time": action_time,
                       "details": json.dumps(details)}

        self._session.post(self.url + '/action',
                           data=action_dict) \
                     .raise_for_status()

    def query(self, select=None, since=None, **kwargs):
        params = {key: json.dumps(value) for key, value in kwargs.items()}
        params['_with_metadata'] = 'true'
        headers = {'Content-type': 'application/json'}
        if since:
            headers['If-Modified-Since'] = formatdate(since)

        response = self._session.get(self.query_url, headers=headers, params=params)
        response.raise_for_status()

        body = response.json()
        if select:
            ret = {}
            for key, metadata in body.iteritems():
                ret[key] = {}
                for k, v in metadata.iteritems():
                    if k in select:
                        ret[key][k] = v
            return ret
        else:
            return body.items()

    @property
    def user_store(self):
        return self.user_data['stores'][0]

    @property
    def user_spaces(self):
        return self.user_store['user_spaces']


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
