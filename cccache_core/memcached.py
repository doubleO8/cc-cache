#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Minimalistic wrapper for accessing memcache server.

.. seealso::

    * http://sendapatch.se/projects/pylibmc/
    * https://memcached.org/
    * https://github.com/douban/libmc

"""
from __future__ import print_function
from __future__ import absolute_import
from builtins import object
import logging

LOG = logging.getLogger(__name__)

import pylibmc

#: default cached key expiration time in seconds
DEFAULT_EXPIRATION_SECONDS = 3600 * 24 * 9

#: cached key expiration time in seconds when keys are touched
TOUCH_GRACE_SECONDS = 3600 * 24 * 3

#: default memcached servers
DEFAULT_SERVERS = ['localhost:11211']


class MemCacheControl(object):
    """
    Memcached Client

    Attributes:
        log: logger instance
        expiration_seconds: key expiration time
        servers: memcached servers
        key_prefix: cache key prefix

    >>> mc = MemCacheControl(key_prefix="doctest_deluxe")
    >>> mc['17'] = "abc"
    >>> mc['17']
    'abc'
    >>> mc.meets_expectation('17', 'abc')
    True
    >>> mc.meets_expectation('17', 'abc1')
    False
    >>> mc.cache_key("haha")
    'doctest_deluxe.haha'

    """
    def __init__(self, *args, **kwargs):
        """
        Args:
            loglevel: loglevel
            expiration_seconds: key expiration time
            servers: memcached servers
            key_prefix: cache key prefix
        """
        self.log = logging.getLogger(__name__)
        self.expiration_seconds = kwargs.get("expiration_seconds")
        self.servers = kwargs.get("servers", DEFAULT_SERVERS)
        self.key_prefix = kwargs.get("key_prefix", "mc")
        loglevel = kwargs.get("loglevel", logging.CRITICAL)
        self.log.setLevel(loglevel)

        if self.expiration_seconds:
            try:
                self.expiration_seconds = int(self.expiration_seconds)
            except (TypeError, ValueError):
                self.expiration_seconds = DEFAULT_EXPIRATION_SECONDS
        else:
            self.expiration_seconds = DEFAULT_EXPIRATION_SECONDS

        self._mc = pylibmc.Client(self.servers)

    def __getitem__(self, key):
        try:
            return self._mc.get(self.cache_key(key))
        except AttributeError:
            pass

        return None

    def __setitem__(self, key, value):
        try:
            return self._mc.set(self.cache_key(key), value,
                                time=self.expiration_seconds)
        except AttributeError:
            pass

    def __delitem__(self, key):
        try:
            return self._mc.delete(self.cache_key(key))
        except AttributeError:
            pass

    def cache_key(self, key):
        """
        Generate the cache key for *key*

        Args:
            key: item key

        Returns:
            str: cache key
        """
        return '.'.join((self.key_prefix, key))


if __name__ == '__main__':
    import doctest

    logging.basicConfig(loglevel=logging.DEBUG)
    (FAILED, SUCCEEDED) = doctest.testmod()
    print("[doctest] SUCCEEDED/FAILED: {:d}/{:d}".format(SUCCEEDED, FAILED))
