# coding=utf-8

from db_manager import get_db
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

def check_user(name, password):
	user_id = get("dd.user%s.password%s" % (name, password))
	return user_id


