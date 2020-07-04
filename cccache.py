#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Caching controller API allowing (almost) arbitrary caching of e.g. CouchDB
documents.

Allows interactions concerning cached versions of CouchDB documents:

    * Promote a database document to the cache
    * Remove cached version of database document
    * Retrieve database document (preferring the cached version)

.. note::

    Environment variables:

        * ``DB_INSTANCE_URI`` – Full URI for storage backend
        * ``API_USERNAME`` – HTTP Basic Auth granting access: *username*
        * ``API_PASSWORD`` – HTTP Basic Auth granting access: *password*

.. warning::

    * Only datasets serialisable as JSON are supported.
    * Not all document sizes are supported
    * Memory limits may prevent caching of certain documents!

"""
from __future__ import absolute_import

import os
import logging
import re
import json

from flask import Flask, abort, request
import requests
from six.moves.urllib.parse import urlparse, ParseResult
from coshed.vial import JINJA_FILTERS
from coshed.flask_tools import wolfication
from coshed.vial import AppResponse, drop_dev
import coshed
from djali.couchdb import CloudiControl

import cccache_core
from cccache_core.memcached import MemCacheControl

coshed.vial.API_VERSION = cccache_core.__version__

#: regular expression - valid ID
PATTERN_VALID_ID = r'^[a-z][a-z0-9\-\_]+$'
REGEX_VALID_ID = re.compile(PATTERN_VALID_ID)

#: regular expression - valid document ID
PATTERN_VALID_DOCUMENT_ID = r'^[a-zA-Z0-9\-\_]+$'
REGEX_VALID_DOCUMENT_ID = re.compile(PATTERN_VALID_DOCUMENT_ID)

APP_NAME = 'cccache'

DEBUG_FLAG = True

#: logger instance
LOG = logging.getLogger(APP_NAME)

#: flask application instance
app = wolfication(
    Flask(__name__),
    jinja_filters=JINJA_FILTERS, app_name=APP_NAME)

not_to_be_exposed = ('assets', 'navigation', 'python_version')

#: default storage backend URI
DB_INSTANCE_URI = 'http://cc:catch@localhost:5984'
storage_backend = os.environ.get("DB_INSTANCE_URI", DB_INSTANCE_URI)

#: used cache key super prefix
CACHE_PREFIX = 'ccc'

#: default cache expiration
CACHE_EXPIRATION_SECONDS = 3600

#: cloud foundry port
#: Port number is required to fetch from env variable
#: http://docs.cloudfoundry.org/devguide/deploy-apps/environment-variable.html#PORT
cf_port = os.getenv("PORT")


def valid_value_or_bust(item_id, regex=None):
    """
    Check if given item ID matches pattern of regular expression.

    .. note::

        If ``regex`` is not provided :py:data:`PATTERN_VALID_ID` will be used.
        If the value does not match, HTTP request will be aborted using
        HTTP status ``400``.

    Args:
        item_id: ID to check
        regex: regular expression to be matched

    """
    if regex is None:
        regex = REGEX_VALID_ID

    try:
        matcher = re.match(regex, item_id)
        if not matcher:
            raise ValueError(
                "value {!r} does not match {!s}".format(item_id, regex.pattern))
    except Exception as exc:
        app.logger.error(exc)
        abort(400)


def get_couch_controller_or_bust(db_name):
    """
    Get :py:class:`djali.couchdb.CloudiControl` instance for given database.

    Args:
        db_name: Database name

    Returns:
        djali.couchdb.CloudiControl: controller instance

    Raises:
        werkzeug.exceptions.HTTPException: When controller cannot be instanciated
    """
    p_url = urlparse(storage_backend)
    couch_db_pr = ParseResult(
        p_url.scheme, p_url.netloc, '/{db_name}'.format(db_name=db_name), '',
        '', ''
    )
    db_url = couch_db_pr.geturl()

    try:
        return CloudiControl(db_url)
    except requests.exceptions.HTTPError as hexc:
        app.logger.error("Cloudi error while trying to use {!r}".format(db_url))
        app.logger.error(hexc)
        if hexc.response.status_code == 403:
            abort(502)
        abort(503)
    except requests.exceptions.ConnectionError as cexc:
        app.logger.error("Cloudi error while trying to use {!r}".format(db_url))
        app.logger.error(cexc)
        abort(503)


@app.route('/<db_name>/<item_id>', methods=['GET'])
@app.route('/f/<db_name>/<item_id>', methods=['GET'])
def document_get_handler(db_name, item_id):
    """
    Retrieve dataset with given item ID from database.

    :param db_name: Database name
    :param item_id: Document ID

    :statuscode 200: no error
    :statuscode 400: Bad database name or document ID
    :statuscode 404: Document neither in cache nor in storage backend
    :statuscode 500: Server Error
    :statuscode 502: Storage backend authentication error
    :statuscode 503: Generic storage backend error

    """
    valid_value_or_bust(db_name, regex=PATTERN_VALID_ID)
    valid_value_or_bust(item_id, regex=REGEX_VALID_DOCUMENT_ID)
    document = None
    ctl = get_couch_controller_or_bust(db_name)
    mc = MemCacheControl(key_prefix='{:s}_{:s}'.format(CACHE_PREFIX, db_name))
    data = AppResponse(drop_dev=drop_dev())

    # app.logger.debug((db_name, item_id, str(ctl)))

    try:
        try:
            document = json.loads(mc[item_id])
            data['_dev']['source'] = "memcached"
            data['_dev']['cache_key'] = mc.cache_key(item_id)
        except TypeError:
            document = ctl[item_id]
            data['_dev']['source'] = "couchdb"
    except KeyError:
        # document not even found in storage backend
        pass
    except Exception as exc:
        app.logger.error(exc)
        abort(500)

    if document is None:
        abort(404)

    data.update(document)

    return data.flask_obj(not_to_be_exposed=not_to_be_exposed)


@app.route('/<db_name>/<item_id>', methods=['PUT'])
def document_put_handler(db_name, item_id):
    """
    Add dataset with given item ID of database to the memory cache.

    :param db_name: Database name
    :param item_id: Document ID

    :statuscode 200: no error
    :statuscode 400: Bad database name or document ID
    :statuscode 404: Document not in storage backend
    :statuscode 500: Server Error
    :statuscode 502: Storage backend authentication error
    :statuscode 503: Generic storage backend error

    """
    valid_value_or_bust(db_name, regex=PATTERN_VALID_ID)
    valid_value_or_bust(item_id, regex=REGEX_VALID_DOCUMENT_ID)
    ctl = get_couch_controller_or_bust(db_name)
    expiration_seconds = CACHE_EXPIRATION_SECONDS
    mc = MemCacheControl(
        key_prefix='{:s}_{:s}'.format(CACHE_PREFIX, db_name),
        expiration_seconds=expiration_seconds
    )
    document = None
    data = AppResponse(drop_dev=drop_dev())

    try:
        document = ctl[item_id]
    except KeyError:
        abort(404)
    except Exception as exc:
        app.logger.error(exc)
        abort(503)

    try:
        mc[item_id] = json.dumps(dict(document))
        data['_dev']['cache_key'] = mc.cache_key(item_id)
    except Exception as exc:
        app.logger.error(exc)
        abort(500)

    if document is None:
        abort(404)

    data.update(document)

    return data.flask_obj(not_to_be_exposed=not_to_be_exposed)


@app.route('/<db_name>/<item_id>', methods=['DELETE'])
def document_delete_handler(db_name, item_id):
    """
    Remove dataset with given item ID of database from memory cache.

    :param db_name: Database name
    :param item_id: Document ID

    :statuscode 200: no error
    :statuscode 400: Bad database name or document ID
    :statuscode 500: Server Error

    """
    valid_value_or_bust(db_name, regex=PATTERN_VALID_ID)
    valid_value_or_bust(item_id, regex=REGEX_VALID_DOCUMENT_ID)
    ctl = MemCacheControl(key_prefix='{:s}_{:s}'.format(CACHE_PREFIX, db_name))

    data = AppResponse(drop_dev=drop_dev())

    try:
        del ctl[item_id]
        return data.flask_obj(not_to_be_exposed=not_to_be_exposed)
    except Exception as exc:
        app.logger.error(exc)
        abort(500)


@app.route('/<db_name>/<item_id>', methods=['POST'])
def document_post_handler(db_name, item_id):
    """
    Add or replace dataset with given item ID to database and to the memory
    cache.

    .. warning::

        Limited sanitisation only:

            * only JSON encoded payload is accepted
            * payload needs to be :py:func:`dict`
            * CouchDB internal key/value pairs (``_id`` and ``_rev``) will be \
              removed

    .. code-block:: bash

        curl --noproxy localhost -X POST -H "Content-Type: application/json" \
        -d '{"test": 1234}' http://localhost:53723/cccache/haha_post

    :param db_name: Database name
    :param item_id: Document ID

    :statuscode 200: no error
    :statuscode 400: Bad database name or document ID
    :statuscode 404: Document not in storage backend
    :statuscode 500: Server Error
    :statuscode 502: Storage backend authentication error
    :statuscode 503: Generic storage backend error

    """
    valid_value_or_bust(db_name, regex=PATTERN_VALID_ID)
    valid_value_or_bust(item_id, regex=REGEX_VALID_DOCUMENT_ID)
    ctl = get_couch_controller_or_bust(db_name)
    expiration_seconds = CACHE_EXPIRATION_SECONDS
    mc = MemCacheControl(
        key_prefix='{:s}_{:s}'.format(CACHE_PREFIX, db_name),
        expiration_seconds=expiration_seconds
    )
    data = AppResponse(drop_dev=drop_dev())

    if not request.is_json:
        app.logger.error("No JSON POSTed!")
        abort(400)

    if request.json is None:
        app.logger.error("Empty content POSTed!")
        abort(400)

    document = request.json
    if not isinstance(document, dict):
        app.logger.error("No dict POSTed!")
        abort(400)

    for del_key in ('_id', '_rev'):
        try:
            del document[del_key]
        except KeyError:
            pass

    try:
        ctl[item_id] = document
    except Exception as exc:
        app.logger.error(exc)
        abort(503)

    try:
        mc[item_id] = json.dumps(document)
        data['_dev']['cache_key'] = mc.cache_key(item_id)
    except Exception as exc:
        app.logger.error(exc)
        abort(500)

    data.update(document)

    return data.flask_obj(not_to_be_exposed=not_to_be_exposed)


if __name__ == '__main__':
    port = int('53722') + 1
    bind_address = '0.0.0.0'

    if cf_port:
        DEBUG_FLAG = False
        port = int(cf_port)

    app.run(host=bind_address, port=port, debug=DEBUG_FLAG)
