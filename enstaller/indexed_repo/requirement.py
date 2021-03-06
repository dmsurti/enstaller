from dist_naming import split_eggname, filename_dist

from enstaller.utils import PY_VER, canonical


class Req(object):
    """
    A requirement object is initalized by a requirement string. Attributes:
    name: the canonical project name
    version: the list of possible versions required
    strictness: the level of strictness
        0   nothing matters, anything matches
        1   only the name must match
        2   name and version must match
        3   name, version and build must match
    """
    def __init__(self, req_string):
        for c in '<>=,':
            assert c not in req_string, req_string
        lst = req_string.split()
        assert len(lst) <= 2, req_string
        self.strictness = 0
        self.name = self.version = self.build = None
        if lst:
            self.name = canonical(lst[0])
            self.strictness = 1
        if len(lst) == 2:
            tmp = lst[1]
            self.version = tmp.split('-')[0]
            self.strictness = 2 + bool('-' in tmp)
            if self.strictness ==  3:
                self.build = int(tmp.split('-')[1])

    def matches(self, spec):
        """
        Returns True if the spec of a distribution matches the requirement
        (self).  That is, the canonical name must match, and the version
        must be in the list of required versions.
        """
        #assert spec['metadata_version'] >= '1.1', spec
        if spec['python'] not in (None, PY_VER):
            return False
        if self.strictness == 0:
            return True
        if spec['cname'] != self.name:
            return False
        if self.strictness == 1:
            return True
        if spec['version'] != self.version:
            return False
        if self.strictness == 2:
            return True
        assert self.strictness == 3
        return spec['build'] == self.build

    def __str__(self):
        if self.strictness == 0:
            return ''
        res = self.name
        if self.version:
            res += ' %s' % self.version
        if self.build:
            res += '-%i' % self.build
        return res

    def __repr__(self):
        """
        return a canonical representation of the object
        """
        return 'Req(%r)' % str(self)

    def __eq__(self, other):
        return (self.name == other.name  and
                self.version == other.version  and
                self.build == other.build  and
                self.strictness == other.strictness)

    def __hash__(self):
        return (hash(self.strictness) ^ hash(self.name) ^
                hash(self.version) ^ hash(self.build))


def add_Reqs_to_spec(spec):
    """
    add the 'Reqs' key (which maps to the set of requirement objects),
    as well as the 'cname' key, to a spec dictionary
    """
    spec['Reqs'] = set(Req(s) for s in spec['packages'])
    spec['cname'] = canonical(spec['name'])


def spec_as_req(spec, strictness=3):
    """
    return a requirement object from a spec
    """
    assert 1 <= strictness <= 3
    req_string = spec['name']
    if strictness >= 2:
        req_string += ' %s' % spec['version']
    if strictness >= 3:
        req_string += '-%i' % spec['build']
    return Req(req_string)


def filename_as_req(filename, strictness=3):
    """
    return the filename of a distribution in terms of the a requirement object
    """
    name, version, build = split_eggname(filename)
    return spec_as_req(locals(), strictness)


def dist_as_req(dist, strictness=3):
    """
    Return the distribution in terms of the a requirement object.
    That is: What requirement gives me the distribution?
    """
    return filename_as_req(filename_dist(dist), strictness)
