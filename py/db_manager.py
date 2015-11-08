# -*- coding: utf-8 -*-

import os
from DB import DB

db_host = os.getenv("DB_HOST", "localhost")
db_port = int(os.getenv("DB_PORT", 3306))
db_name = os.getenv("DB_NAME", "eleme")
db_user = os.getenv("DB_USER", "root")
db_pass = os.getenv("DB_PASS", "toor")

max_conn_cache = 100

idle_conn = []

def conn_db():
	db = DB(False, host = db_host, user = db_user, passwd = db_pass, db = db_name, port = db_port)
	return db

def get_db():
	if len(idle_conn) > 0:
		db = idle_conn.pop()
	else:
		db = conn_db()
	return db

def reuse_db(db):
	if len(idle_conn) < max_conn_cache:
		idle_conn.append(db)
	else:
		db.close()