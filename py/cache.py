# coding=utf-8

from db_manager import get_db, get_redis_store
import sys
import json

cache_data = {}
user_cache = {}
food_cache = {}

def cache(key, val):
	cache_data[key] = val

def get(key, default=None):
	return cache_data.get(key, default)

def cache_users_data():
	db = get_db()
	all_users = db.select('select * from user')
	db.close()
	for u in all_users:
		user_cache["dd.user%s.password%s" % (u[1], u[2])] =  u[0]
	r = get_redis_store()
	user_cache['dd.user.min_id'] = int(r.hget('dd.user', 'min_id'))
	user_cache['dd.user.max_id'] = int(r.hget('dd.user', 'max_id'))

def cache_foods_data():
	r = get_redis_store()
	food_cache['dd.food.min_id'] = int(r.hget('dd.food', 'min_id'))
	food_cache['dd.food.max_id'] = int(r.hget('dd.food', 'max_id'))
	food_cache['dd.food.json'] = r.get('dd.food.json')
	db = get_db()
	all_foods = db.select('select * from food')
	db.close()
	for f in all_foods:
		food_cache["dd.food%d.price" % f[0]] = f[2]

def check_user(name, password):
	return user_cache.get("dd.user%s.password%s" % (name, password), None)

def user_min_id():
	return user_cache.get('dd.user.min_id', 1)

def user_max_id():
	return user_cache.get('dd.user.max_id', 1000)

def food_json():
	return food_cache.get('dd.food.json', '')

def food_min_id():
	return food_cache.get('dd.food.min_id', 1)

def food_max_id():
	return food_cache.get('dd.food.max_id', 100)

def food_price(food_id):
	return food_cache.get("dd.food%d.price" % food_id, 0)



