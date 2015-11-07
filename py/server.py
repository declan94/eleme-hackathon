#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from flask import Flask
from flask import request
from flask import Response
import json

from DB import db
from my_redis import myr

host = os.getenv("APP_HOST", "localhost")
port = int(os.getenv("APP_PORT", "8080"))

app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Hello World! test'

############### special responses ###############

def my_response(data, status_code = 200, status = "ok"):
	r = Response()
	r.status = status
	r.status_code = status_code
	r.data = json.dumps(data)
	return r

def bad_req_1():
	return my_response({"code": "EMPTY_REQUEST", "message": "请求体为空"}, 400, "Bad Request")

def bad_req_2():
	return my_response({"code": "MALFORMED_JSON", "message": "格式错误"}, 400, "Bad Request")

def unauthorized():
	return my_response({"code": "INVALID_ACCESS_TOKEN", "message": "无效的令牌"}, 401, "Unauthorized")
	

############### support functions ###############

def check_data():
	data = request.data
	if not data:
		return bad_req_1()
	else:
		try:
			data = json.loads(data)
		except Exception, e:
			return bad_req_2()
		else:
			return data

def authorize():
	args = request.args
	if args.has_key('access_token'):
		access_token = args['access_token']
	else:
		if args.has_key('Access-Token'):
			access_token = args['Access-Token']
		else:
			if request.headers.has_key('Access-Token'):
				access_token = request.headers['Access-Token']
			else:
				return unauthorized()
	key = "ACCESS_%s" % access_token
	user_id = myr.get(key)
	if user_id == None:
		return unauthorized()
	else:
		return int(user_id)
		


############### view functions ###############

@app.route('/login', methods=["POST"])
def login():
	data = check_data()
	if isinstance(data, Response):
		return data
	username = data['username']
	password = data['password']
	rows = db.select("select `id` from user where name='%s' and password='%s' limit 1" % (username, password))
	r = Response()
	if rows and len(rows) > 0:
		user_id = rows[0][0]
		access_token = "%032d" % user_id
		myr.set("ACCESS_%s" % access_token, user_id)
		res_data = {'user_id': user_id, 'username': data['username'], 'access_token': access_token}
		return my_response(res_data)
	else:
		res_data = {"code": "USER_AUTH_FAIL", "message": "用户名或密码错误"}
		return my_response(res_data, 403, "Forbidden")

@app.route('/foods')
def foods():
	user_id = authorize()
	if isinstance(user_id, Response):
		return user_id
	rows = db.select("select * from food", is_dict = True)
	return my_response(rows)

@app.route('/carts', methods=["POST"])
def carts():
	user_id = authorize()
	if isinstance(user_id, Response):
		return user_id
	cart_id = "%032d" % myr.incr('CART_ID')
	myr.set("USER_CART_%d_%s" % (user_id, cart_id), 1)
	return my_response({'cart_id': cart_id})


if __name__ == '__main__':
    app.run(host=host, port=port, debug=True)

