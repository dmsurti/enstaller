from __future__ import print_function

import re
import sys
import time
import string
from os.path import isfile, join

import egginst


TIME_FMT = '%Y-%m-%d %H:%M:%S %z %Z'

def now():
    """
    return the current local time as an ISO formated
    string with time zone data, e.g. '2012-05-21 16:45:59 -0500 CDT'
    """
    return time.strftime(TIME_FMT)

def is_diff(content):
    return any(s.startswith(('-', '+')) for s in content)

def pretty_diff(diff):
    added = {}
    removed = {}
    for s in diff:
        fn = s[1:]
        name, version = egginst.name_version_fn(fn)
        if s.startswith('-'):
            removed[name.lower()] = version
        elif s.startswith('+'):
            added[name.lower()] = version
    changed = set(added) & set(removed)
    for name in sorted(changed):
        yield ' %s  (%s -> %s)' % (name, removed[name], added[name])
    for name in sorted(set(removed) - changed):
        yield '-%s-%s' % (name, removed[name])
    for name in sorted(set(added) - changed):
        yield '+%s-%s' % (name, added[name])

def pretty_content(content):
    if is_diff(content):
        return pretty_diff(content)
    else:
        return iter(sorted(content, key=string.lower))


class History(object):

    def __init__(self, prefix):
        self.prefix = prefix
        if prefix is None:
            return
        self._log_path = join(prefix, 'enpkg.hist')

    def __enter__(self):
        if self.prefix is None:
            return
        self.update()

    def __exit__(self, exc_type, exc_value, traceback):
        if self.prefix is None:
            return
        self.update()

    def _init_log_file(self, force=False):
        """
        initialize the log file
        """
        if not force and isfile(self._log_path):
            return
        self._write_egg_names(egginst.get_installed(self.prefix))

    def update(self):
        """
        update the history file (creating a new one if necessary)
        """
        self._init_log_file()
        last = self.get_state()
        curr = set(egginst.get_installed(self.prefix))
        if last == curr:
            return
        self._write_changes(last, curr)

    def parse(self):
        """
        parse the history file and return a list of
        tuples(datetime strings, set of eggs/diffs)
        """
        res = []
        if not isfile(self._log_path):
            return res
        sep_pat = re.compile(r'==>\s*(.+?)\s*<==')
        for line in open(self._log_path):
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            m = sep_pat.match(line)
            if m:
                dt = m.group(1)
                res.append((dt, set()))
            else:
                res[-1][1].add(line)
        return res

    def construct_states(self):
        """
        return a list of tuples(datetime strings, set of eggs)
        """
        res = []
        for dt, cont in self.parse():
            if not is_diff(cont):
                cur = cont
            else:
                for s in cont:
                    if s.startswith('-'):
                        cur.discard(s[1:])
                    elif s.startswith('+'):
                        cur.add(s[1:])
                    else:
                        raise Exception('Did not expect: %s' % s)
            res.append((dt, cur.copy()))
        return res

    def get_state(self, rev=-1):
        """
        return the state, i.e. the set of eggs, for a given revision,
        defaults to latest (which is the same as the current state when
        the log file is up-to-date)
        """
        times, pkgs = zip(*self.construct_states())
        return pkgs[rev]

    def print_log(self):
        for i, (date, content) in enumerate(self.parse()):
            print('%s  (rev %d)' % (date, i))
            for line in pretty_content(content):
                print('    %s' % line)
            print()

    def _write_egg_names(self, names):
        """ update the log file with the given list of egg names.

        Should be used only when init-ing the log_file
        """
        fo = open(self._log_path, 'w')
        fo.write("==> %s <==\n" % now())
        for eggname in names:
            fo.write('%s\n' % eggname)
        fo.close()

    def _write_changes(self, last_state, current_state):
        """ write the changes between last_state and current_state to log_file.

        """
        fo = open(self._log_path, 'a')
        fo.write("==> %s <==\n" % now())
        for fn in last_state - current_state:
            fo.write('-%s\n' % fn)
        for fn in current_state - last_state:
            fo.write('+%s\n' % fn)
        fo.close()


if __name__ == '__main__':
    h = History(sys.prefix)
    with h:
        h.update()
        h.print_log()
