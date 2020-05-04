# -*- coding: utf-8 -*-

# Copyright (c) 2020 shmilee

'''
Contains loader base class.
'''

import os
import re
import types
import contextlib

from ..glogger import getGLogger
from ..utils import simple_parse_doc

__all__ = ['BaseLoader', 'BaseRawLoader', 'BasePckLoader']
log = getGLogger('L')


class BaseLoader(object):
    '''
    Base class of BaseRawLoader, BasePckLoader.

    Attributes
    ----------
    path: str
    '''
    __slots__ = ['path', 'pathobj']
    loader_type = 'base'

    def __init__(self, path):
        if self._check_path_access(path):
            self.path = path
            if not self._special_check_path():
                raise ValueError("Path '%s' checking failed." % path)
            self.pathobj = None
        else:
            raise IOError("Failed to access path '%s'." % path)

    def update(self, *args, **kwargs):
        '''
        Update path object, keys, etc.
        '''
        raise NotImplementedError()

    @staticmethod
    def _check_path_access(path):
        '''
        Check for access to *path*.
        '''
        if os.path.exists(path) and os.access(path, os.R_OK):
            return True
        else:
            return False

    def _special_check_path(self):
        '''
        Recheck the path. Return bool.
        '''
        raise NotImplementedError()

    def _special_open(self):
        '''
        Return path object to read.
        '''
        raise NotImplementedError()

    def _special_close(self, pathobj):
        '''
        Close path object.
        '''
        raise NotImplementedError()

    def _special_getkeys(self, pathobj):
        '''
        Return all keys in path object.
        '''
        raise NotImplementedError()

    def _special_get(self, pathobj, item):
        '''
        Return value object of key *item* in path object.
        '''
        raise NotImplementedError()

    def close(self):
        if self.pathobj:
            log.debug("Close path %s." % self.path)
            self._special_close(self.pathobj)
            self.pathobj = None

    def keys(self):
        '''Return loader keys.'''
        raise NotImplementedError()

    def find(self, *items):
        '''
        Find the loader keys which contain *items*.
        '''
        result = self.keys()
        for i in items:
            i = str(i)
            result = tuple(
                filter(lambda k: True if i in k else False, result))
        return tuple(result)

    def refind(self, pattern):
        '''
        Find the loader keys which match the regular expression *pattern*.
        '''
        pat = re.compile(pattern)
        return tuple(filter(
            lambda k: True if re.match(pat, k) else False, self.keys()))

    def __contains__(self, item):
        '''
        Return true if item is in loader, false otherwise.
        '''
        return item in self.keys()

    def all_in_loader(self, *items):
        '''
        Check if all the *items* are in this loader.
        '''
        loaderkeys = self.keys()
        result = True
        for i in items:
            if i not in loaderkeys:
                log.warning("Key '%s' not in %s!" % (i, self.path))
                result = False
        return result

    def __repr__(self):
        return '<{0} object at {1} for {2}>'.format(
            type(self).__name__, hex(id(self)), self.path)
        # return '<{0}.{1} object at {2} for {3}>'.format(
        #    self.__module__, type(self).__name__, hex(id(self)), self.path)

    def __getstate__(self):
        # self.pathobj may has '_io.BufferedReader' object,
        # which cannot be pickled, when use multiprocessing.
        return [(name, getattr(self, name))
                for cls in type(self).__mro__
                for name in getattr(cls, '__slots__', [])
                if name != 'pathobj']

    def __setstate__(self, state):
        for name, value in state:
            setattr(self, name, value)
        self.pathobj = self._special_open()


def _raw_copydoc_func(docs):
    name, doc = docs[0]
    assert name == 'BaseRawLoader'
    return (), simple_parse_doc(
        doc, ('Attributes', 'Parameters', 'Notes'), strip=None)


class BaseRawLoader(BaseLoader):
    '''
    Load raw data from a directory or archive file.
    Return a dictionary-like object.

    Attributes
    ----------
    path: str
        path of directory or archive file
    filenames: tuple
        filenames in the directory or archive file

    Parameters
    ----------
    path: str
        path of directory or file
    filenames_filter: function
        a function to filter filenames, example:
        lambda name: True if name.endswith('.out') else False

    Notes
    -----
    1. Method *get()* must be used as with statement context managers.
    2. File-like object which returned by *get()* must has close method,
       and read, readline, or readlines.
    '''
    __slots__ = ['filenames']

    def __init__(self, path, filenames_filter=None):
        super(BaseRawLoader, self).__init__(path)
        self.update(filenames_filter=filenames_filter)

    def update(self, filenames_filter=None):
        self.close()
        self.filenames = None
        try:
            log.debug("Open path %s." % self.path)
            pathobj = self._special_open()
            log.debug("Getting filenames from %s ..." % self.path)
            filenames = tuple(self._special_getkeys(pathobj))
            if isinstance(filenames_filter, types.FunctionType):
                filenames = [k for k in filenames if filenames_filter(k)]
            self.pathobj = pathobj
            self.filenames = tuple(sorted(filenames))
        except (IOError, ValueError):
            log.error("Failed to read path %s." % self.path, exc_info=1)
            raise

    def keys(self):
        return self.filenames

    @contextlib.contextmanager
    def get(self, key):
        '''
        Get file-like object by filename *key*.
        A function for with statement context managers.
        '''
        if key not in self.filenames:
            raise KeyError("%s is not in '%s'" % (key, self.path))
        try:
            log.debug("Getting file '%s' from %s ..." % (key, self.path))
            fileobj = self._special_get(self.pathobj, key)
            yield fileobj
        except (IOError, ValueError):
            log.error("Failed to get '%s' from %s!" %
                      (key, self.path), exc_info=1)
            raise
        finally:
            if 'fileobj' in dir():
                log.debug("Close file %s in path %s." % (key, self.path))
                fileobj.close()

    def beside_path(self, name):
        '''Get a path for *name*, join with :attr:`path`'''
        return os.path.join(self.path, name)


class BasePckLoader(BaseLoader):
    '''
    Load arrays data from a pickled(packaged) data file or cache.
    Return a dictionary-like object.

    Attributes
    ----------
    path: str
        path of the file or cache
    datakeys: tuple
        keys in the loader, contain group name
    datagroups: tuple
        groups of datakeys
    description: str or None
        description of the data, if 'description' is in datakeys
    desc: alias description
    cache: dict
        cached datakeys from file

    Parameters
    ----------
    path: str
        path to open
    datagroups_filter: function
        a function to filter datagroups
        example, lambda group: False if group in ['ex1', 'ex2'] else True
    '''
    __slots__ = ['datakeys', 'datagroups',
                 'desc', 'description', 'cache']

    def _special_getgroups(self, pathobj):
        '''
        Return all keys' groups in path object.
        '''
        return set(os.path.dirname(k) for k in self.datakeys)

    def __init__(self, path, datagroups_filter=None):
        super(BasePckLoader, self).__init__(path)
        self.update(datagroups_filter=datagroups_filter)

    def update(self, datagroups_filter=None):
        self.close()
        self.datakeys, self.datagroups = None, None
        self.description, self.desc = None, None
        try:
            log.debug("Open path %s." % self.path)
            pathobj = self._special_open()
            self.pathobj = pathobj
            log.debug("Getting datakeys from %s ..." % self.path)
            self.datakeys = tuple(self._special_getkeys(pathobj))
            log.debug("Getting datagroups from %s ..." % self.path)
            datagroups = list(self._special_getgroups(pathobj))
            if isinstance(datagroups_filter, types.FunctionType):
                datagroups = list(filter(datagroups_filter, datagroups))
            if '' in datagroups:
                datagroups.remove('')
            self.datagroups = tuple(sorted(datagroups))
            log.debug("Getting description of %s ..." % self.path)
            if 'description' in self.datakeys:
                self.desc = str(self._special_get(pathobj, 'description'))
            else:
                self.desc = None
            self.description = self.desc
        except (IOError, ValueError):
            log.error("Failed to read path %s." % self.path, exc_info=1)
            raise
        self.cache = {}

    def keys(self):
        return self.datakeys

    def groups(self):
        return self.datagroups

    def get(self, key):
        '''
        Get value by ``key`.
        '''
        if key not in self.datakeys:
            raise KeyError("%s is not in '%s'" % (key, self.path))
        if key in self.cache:
            return self.cache[key]
        try:
            log.debug("Getting key '%s' from %s ..." % (key, self.path))
            value = self._special_get(self.pathobj, key)
            self.cache[key] = value
        except (IOError, ValueError):
            log.error("Failed to get '%s' from %s!" %
                      (key, self.path), exc_info=1)
            raise
        return value

    __getitem__ = get

    def get_many(self, *keys):
        '''
        Get values by ``keys``. Return a tuple of values.
        '''
        result = [self.cache[k] if k in self.cache else None for k in keys]
        idxtodo = [i for i, k in enumerate(result) if k is None]
        if len(idxtodo) == 0:
            return tuple(result)
        try:
            for i in idxtodo:
                key = keys[i]
                log.debug("Getting key '%s' from %s ..." % (key, self.path))
                value = self._special_get(self.pathobj, key)
                result[i] = value
                self.cache[key] = value
        except (IOError, ValueError):
            if 'key' in dir():
                log.error("Failed to get '%s' from %s!" %
                          (key, self.path), exc_info=1)
            else:
                log.error("Failed to open '%s'!" % self.path, exc_info=1)
            raise
        return tuple(result)

    def clear_cache(self):
        self.cache = {}
