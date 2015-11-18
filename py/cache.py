# coding=utf-8

from db_manager import get_db, get_redis_store
import sys

cache_data = {}

def cache(key, val):
	global cache_data
	cache_data[key] = val

def get(key, default=None):
	global cache_data
	return cache_data.get(key, default)

def cache_users_data():
	db = get_db()
	all_users = db.select('select * from user')
	db.close()
	for u in all_users:
		cache("dd.user%s.password%s" % (u[1], u[2]), u[0])
	r = get_redis_store()
	cache('dd.user.min_id', int(r.hget('dd.user', 'min_id')))
	cache('dd.user.max_id', int(r.hget('dd.user', 'max_id')))

def cache_foods_data():
	r = get_redis_store()
	cache('dd.food.min_id', int(r.hget('dd.food', 'min_id')))
	cache('dd.food.max_id', int(r.hget('dd.food', 'max_id')))
	cache('dd.food.json', r.get('dd.food.json'))

def check_user(name, password):
	user_id = get("dd.user%s.password%s" % (name, password))
	return user_id

def user_min_id():
	return get('dd.user.min_id')

def user_max_id():
	return get('dd.user.max_id')

def food_json():
	return get('dd.food.json')

def food_min_id():
	return get('dd.food.min_id')

def food_max_id():
	return get('dd.food.max_id')



