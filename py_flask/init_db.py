#!/usr/bin/env python
# -*- coding: utf-8 -*-

from db_manager import get_db, get_redis_store

myr = get_redis_store()
myr.flushdb()

db = get_db()
rows = db.select('select min(id) from food')
min_food_id = rows[0][0]
rows = db.select('select max(id) from food')
max_food_id = rows[0][0]
db.close()

myr.set('MIN_FOOD_ID', min_food_id)
myr.set('MAX_FOOD_ID', max_food_id)
