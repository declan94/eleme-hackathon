#!/usr/bin/env python
# -*- coding: utf-8 -*-

from DB import db
from my_redis import myr

# db.execute('CREATE  TABLE  test (name VARCHAR(20),password VARCHAR(20));')
myr.flushdb()
