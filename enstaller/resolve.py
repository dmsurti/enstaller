import re
from collections import defaultdict

from utils import PY_VER, comparable_version



def comparable_info(spec):
    """
    Returns a tuple(version, build) for a distribution, version is a
    RationalVersion object.  The result may be used for as a sort key.
    """
    return comparable_version(spec['version']), spec['build']


class Req(object):
    """
    A requirement object is initialized by a requirement string. Attributes:
    name: the lowercase project name
    version: the list of possible versions required
    strictness: the level of strictness
        0   nothing matters, anything matches
        1   only the name must match
        2   name and version must match
        3   name, version and build must match
    """
    pat = re.compile(r'(?:([\w.]+)(?:\s+([\w.]+)(?:-(\d+))?)?)?$')

    def __init__(self, req_string):
        m = self.pat.match(str(req_string.strip()))
        if m is None:
            raise Exception("Not a valid requirement: %r" % req_string)
        self.name, self.version, self.build = m.groups()
        self.strictness = 0
        if self.name is not None:
            self.name = self.name.lower()
            self.strictness = 1
        if self.version is not None:
            self.strictness = 2
        if self.build is not None:
            self.build = int(self.build)
            self.strictness = 3

    def as_dict(self):
        res = {}
        for var_name in 'name', 'version', 'build':
            if getattr(self, var_name):
                res[var_name] = getattr(self, var_name)
        return res

    def matches(self, spec):
        """
        Returns True if the spec of a distribution matches the requirement
        (self).  That is, the name must match, and the version must be in
        the list of required versions.
        """
        if spec['python'] not in (None, PY_VER):
            return False
        if self.strictness == 0:
            return True
        if spec['name'] != self.name:
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
            res += '-%d' % self.build
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



class Resolve(object):
    """
    The main purpose of this class is to support the install_sequence method
    below.  In most cases, the user will only create an instance of this
    class (which is inexpensive), to call the install_sequence method, e.g.:

    eggs = Resolve(store).install_sequence(req)
    """
    def __init__(self, repo, verbose=False):
        self.repo = repo
        self.verbose = verbose

    def get_egg(self, req):
        """
        return the egg with the largest version and build number
        """
        assert req.strictness >= 1

        eggs = dict(self.repo.query(type='egg', name=req.name))
        matches = [egg for egg, metadata in eggs.iteritems()
                   if req.matches(metadata) and metadata.get('available', True)]
        if matches:
            return max(matches, key=lambda egg: comparable_info(eggs[egg]))
        else:
            return None

    def egg_reqs(self, egg):
        """
        return the set of requirement objects listed by the given egg
        """
        return {Req(pkg) for pkg in self.repo.get_metadata(egg)['packages']}

    def egg_name(self, egg):
        """
        return the project name for a given egg (from it's meta data)
        """
        return self.repo.get_metadata(egg)['name']

    def are_complete(self, eggs):
        """
        return True if the 'eggs' are complete, i.e. the for each egg all
        dependencies (by name only) are also included in 'eggs'
        """
        names = {self.egg_name(egg) for egg in eggs}
        for egg in eggs:
            for req in self.egg_reqs(egg):
                if req.name not in names:
                    return False
        return True

    def determine_install_order(self, eggs):
        """
        given the 'eggs' (which are already complete, i.e. the for each
        egg all dependencies are also included in 'eggs'), return a list
        of the same eggs in the correct install order
        """
        eggs = list(eggs)
        assert self.are_complete(eggs)

        # make sure each project name is listed only once
        assert len(eggs) == len(set(self.egg_name(d) for d in eggs))

        # the eggs corresponding to the requirements must be sorted
        # because the output of this function is otherwise not deterministic
        eggs.sort(key=self.egg_name)

        # maps egg -> set of required (project) names
        rns = {}
        for egg in eggs:
            rns[egg] = set(r.name for r in self.egg_reqs(egg))

        # as long as we have things missing, simply look for things which
        # can be added, i.e. all the requirements have been added already
        result = []
        names_inst = set()
        while len(result) < len(eggs):
            n = len(result)
            for egg in eggs:
                if egg in result:
                    continue
                # see if all required packages were added already
                if all(bool(name in names_inst) for name in rns[egg]):
                    result.append(egg)
                    names_inst.add(self.egg_name(egg))
                    assert len(names_inst) == len(result)

            if len(result) == n:
                # nothing was added
                raise Exception("Loop in dependency graph\n%r" % eggs)
        return result

    def _sequence_flat(self, root):
        eggs = [root]
        for r in self.egg_reqs(root):
            d = self.get_egg(r)
            if d is None:
                from enstaller.enpkg import EnpkgError
                err = EnpkgError('Error: could not resolve %s' % str(r))
                err.req = r
                raise err
            eggs.append(d)

        can_order = self.are_complete(eggs)
        if self.verbose:
            print "Can determine install order:", can_order
        if can_order:
            eggs = self.determine_install_order(eggs)
        return eggs

    def _sequence_recur(self, root):
        reqs_shallow = {r.name: r for r in self.egg_reqs(root)}
        reqs_deep = defaultdict(set)

        def add_dependents(egg, visited=None):
            if visited is None:
                visited = set()
            visited.add(egg)

            for req in self.egg_reqs(egg):
                reqs_deep[req.name].add(req)
                if (req.name in reqs_shallow  and
                    req.strictness < reqs_shallow[req.name].strictness):
                    continue

                dep = self.get_egg(req)
                if dep is None:
                    from enstaller.enpkg import EnpkgError
                    err = EnpkgError(('Error: could not resolve "%s" ' +
                                      'required by "%s"') % (str(req), egg))
                    err.req = req
                    raise err
                eggs.add(dep)
                if not dep in visited:
                    add_dependents(dep, visited)

        eggs = {root}
        add_dependents(root)

        names = {self.egg_name(egg) for egg in eggs}
        if len(eggs) != len(names):
            for name in names:
                ds = [d for d in eggs if self.egg_name(d) == name]
                assert len(ds) != 0
                if len(ds) == 1:
                    continue
                if self.verbose:
                    print 'multiple: %s' % name
                    for d in ds:
                        print '    %s' % d
                r = max(reqs_deep[name], key=lambda r: r.strictness)
                assert r.name == name
                # remove the eggs with name
                eggs = [d for d in eggs if self.egg_name(d) != name]
                # add the one
                eggs.append(self.get_egg(r))

        return self.determine_install_order(eggs)

    def install_sequence(self, req, mode='recur'):
        """
        Return the list of eggs which need to be installed (and None if
        the requirement can not be resolved).
        The returned list is given in dependency order.
        The 'mode' may be:

        'root':  only the egg for the requirement itself is
                 contained in the result (but not any dependencies)

        'flat':  dependencies are handled only one level deep

        'recur': dependencies are handled recursively (default)
        """
        if self.verbose:
            print "Determining install sequence for %r" % req
        root = self.get_egg(req)
        if root is None:
            return None
        if mode == 'root':
            return [root]
        if mode == 'flat':
            return self._sequence_flat(root)
        if mode == 'recur':
            return self._sequence_recur(root)
        raise Exception('did not expect: mode = %r' % mode)
