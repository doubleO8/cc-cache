#!/usr/bin/env python
# -*- coding: utf-8 -*-
from __future__ import absolute_import

try:
    from setuptools import setup
except ImportError:
    from distutils.core import setup

import versioneer

setup(
    name='cc-cache',
    author="doubleO8",
    author_email="wb008@hdm-stuttgart.de",
    version=versioneer.get_version(),
    cmdclass=versioneer.get_cmdclass(),
    description="no description",
    long_description="no long description either",
    url="http://127.0.0.1:27450/",
    packages=['cccache_core'],
    install_requires=[
        'pendulum==2.0.5',
        'requests>=2.13.0',
        'future==0.18.2',
        'coshed>=0.7.0',
        'six==1.13.0',
        'Jinja2==2.11.3',
        'Flask==1.1.1',
        'Flask-Compress==1.4.0',
        'Flask-Cors==3.0.7',
        'djali>=0.1.3',
        'pylibmc>=1.6.1',
    ],
    scripts=[
        'cccache.py'
    ]
)
