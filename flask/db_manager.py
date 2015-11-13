# -*- coding: utf-8 -*-

import os
from DB import DB
import redis

db_host = os.getenv("DB_HOST", "localhost")
db_port = int(os.getenv("DB_PORT", 3306))
db_name = os.getenv("DB_NAME", "eleme")
db_user = os.getenv("DB_USER", "root")
db_pass = os.getenv("DB_PASS", "toor")
redis_host = os.getenv('REDIS_HOST', "localhost")
redis_port = int(os.getenv('REDIS_PORT', 6379))

cached_myr = False

def get_db():
	db = DB(False, host = db_host, user = db_user, passwd = db_pass, db = db_name, port = db_port)
	return db

def get_redis_store():
	global cached_myr
	if cached_myr:
		return cached_myr
	myr = redis.Redis(host=redis_host, port=redis_port)
	cached_myr = myr
	return myr
	