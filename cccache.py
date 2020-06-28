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

from flask import Flask, abort
import requests
from six.moves.urllib.parse import urlparse, ParseResult
from coshed.vial import JINJA_FILTERS
from coshed.flask_tools import wolfication
from coshed.vial import AppResponse, drop_dev
import coshed
from djali.couchdb import CloudiControl
from flask_httpauth import HTTPBasicAuth
from werkzeug.security import generate_password_hash, check_password_hash

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
auth = HTTPBasicAuth()

not_to_be_exposed = ('assets', 'navigation', 'python_version')

#: default storage backend URI
DB_INSTANCE_URI = 'http://cc:catch@localhost:5984'
storage_backend = os.environ.get("DB_INSTANCE_URI", DB_INSTANCE_URI)
api_username = os.environ.get("API_USERNAME")
api_password = os.environ.get("API_PASSWORD")

#: used cache key super prefix
CACHE_PREFIX = 'ccc'

#: default cache expiration
CACHE_EXPIRATION_SECONDS = 3600

#: cloud foundry port
#: Port number is required to fetch from env variable
#: http://docs.cloudfoundry.org/devguide/deploy-apps/environment-variable.html#PORT
cf_port = os.getenv("PORT")

if not (api_password and api_password):
    import random

    u, p = (list("abcDEFkl843"), 
            list("hiK841g288745947383839297328239jfdshfsd74nerh43r483bdsjsd"))
    random.shuffle(u)
    random.shuffle(p)
    api_password = ''.join(p)
    api_username = ''.join(u)
    app.logger.warning("API credentials: {!r}:{!r}".format(
        api_username, api_password))
    app.logger.warning(
        "Please consider using the environment variables {!r} ...".format(
            ('API_USERNAME', 'API_PASSWORD')))

users = {
    api_username: generate_password_hash(api_password)
}

@auth.verify_password
def verify_password(username, password):
    if username in users:
        return check_password_hash(users.get(username), password)

    return False


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
@auth.login_required
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
        except KeyError:
            document = ctl[item_id]
            data['_dev']['source'] = "couchdb"
    except Exception as exc:
        app.logger.error(exc)
        abort(500)

    if document is None:
        abort(404)

    data.update(document)

    return data.flask_obj(not_to_be_exposed=not_to_be_exposed)


@app.route('/<db_name>/<item_id>', methods=['PUT'])
@auth.login_required
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
        abort(500)

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
@auth.login_required
def document_delete_handler(db_name, item_id):
    """
    Remove dataset with given item ID of database from memory cache.

    :param db_name: Database name
    :param item_id: Document ID

    :statuscode 200: no error
    :statuscode 500: Server Error
    :statuscode 502: Storage backend authentication error
    :statuscode 503: Generic storage backend error

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


@app.route("/auth")
@auth.login_required
def nginx_auth():
    data = AppResponse()
    return data.flask_obj(not_to_be_exposed=not_to_be_exposed)


if __name__ == '__main__':
    port = int('53722')
    bind_address = '0.0.0.0'

    if cf_port:
        DEBUG_FLAG = False
        port = int(cf_port)

    app.run(host=bind_address, port=port, debug=DEBUG_FLAG)
