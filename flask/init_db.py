#!/usr/bin/env python
# -*- coding: utf-8 -*-

from db_manager import get_db, get_redis_store
import json

# cache all data in redis

db = get_db()

rows = db.select('select min(id) from food')
min_food_id = rows[0][0]
rows = db.select('select max(id) from food')
max_food_id = rows[0][0]
rows = db.select('select min(id) from user')
min_user_id = rows[0][0]
rows = db.select('select max(id) from user')
max_user_id = rows[0][0]

all_foods = db.select('select * from food', is_dict=True)
all_users = db.select('select * from user')

db.close()

myr = get_redis_store()
myr.flushdb()
myr.hset('dd.food', 'min_id', min_food_id)
myr.hset('dd.food', 'max_id', max_food_id)
myr.hset('dd.user', 'min_id', min_user_id)
myr.hset('dd.user', 'max_id', max_user_id)
myr.set('dd.food.json', json.dumps(all_foods))

for i in range(0, len(all_foods)):
	f = all_foods[i]
	myr.set("dd.food%d.stock" % f['id'], f['stock'])
	myr.set("dd.food%d.price" % f['id'], f['price'])

for i in range(0, len(all_users)):
	u = all_users[i]
	myr.hset("dd.user%s" % u[1], "password", u[2])
	myr.hset("dd.user%s" % u[1], "id", u[0])


