import json

from enstaller.bundled import requests

from enstaller.bundled.encore.storage.dynamic_url_store import DynamicURLStore

from enstaller import plat


class GritsClientStore(DynamicURLStore):
    def __init__(self, url, session=None):
        self.url = self._clean_url(url)
        base_url = self.url + '/store'
        super(GritsClientStore, self).__init__(base_url, base_url)
        self.authenticated = False
        self._session = session or requests.Session()

    def connect(self, creds):
        if creds is not None:
            username, password = creds
            response = self._session.post(self.url + '/authenticate',
                                          data={'email': username,
                                                'password':password})

            response.raise_for_status()
            self.user_data = response.json()
            self.authenticated = True

        self._connected = True

    def add_action(self, user_id, action_type, action_time, **details):
        action_dict = {"user_id": user_id,
                       "action_type": action_type,
                       "action_time": action_time,
                       "details": json.dumps(details)}

        self._session.post(self.url + '/action',
                           data=action_dict) \
                     .raise_for_status()

    def query(self, **kwargs):
        index = {}
        for space in self._user_spaces():
            index.update(self._query_space(space, **kwargs))
        return index.items()

    @staticmethod
    def _clean_url(url):
        url = url.rstrip('/')
        if not url.endswith('/api'):
            url += '/api'
        return url

    def _query_space(self, space, select=None, since=None, **kwargs):
        params = {key: json.dumps(value) for key, value in kwargs.items()}
        params['_with_metadata'] = 'true'
        headers = {'Content-type': 'application/json'}

        if since:
            headers['If-Modified-Since'] = formatdate(since)

        response = self._session.get(self.query_url + '/' + space,
                                     headers=headers,
                                     params=params)
        response.raise_for_status()

        body = response.json()
        if select:
            return [(key, {k: metadata[k] for k in metadata if k in select}) \
                    for key, metadata in body.iteritems()]
        else:
            return body.items()

    def _user_spaces(self):
        return self.user_data['stores'][0]['user_spaces']


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
