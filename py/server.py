#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from time import time

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
	if data:
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
	if request.headers.has_key('Access-Token'):
		access_token = request.headers['Access-Token']
	else:
		args = request.args
		if args.has_key('access_token'):	
			access_token = args['access_token']
		else:
			return unauthorized()
	key = "ACCESS_%s" % access_token
	user_id = myr.get(key)
	if user_id == None:
		return unauthorized()
	else:
		return int(user_id)

# food relative #

def get_food(food_id):
	cached = get_cached_food(food_id)
	if cached:
		return cached
	rows = db.select("select stock, price from `food` where id = %d limit 1" % food_id)
	if not rows or len(rows) == 0:
		return None
	else:
		return rows[0]

def get_cached_food(food_id):
	cache_key = "FOOD_" + food_id
	ct = myr.hget(cache_key, 'cache_time')
	if not ct or time() - ct > 5:
		return None
	stock = myr.hget(cache_key, 'stock')
	price = myr.hget(cache_key, 'price')
	food = {'id': food_id, 'stock': stock, 'price': price}
	cache_food(food)
	return food

def cache_food(food):
	food_id = food['id']
	cache_key = "FOOD_" + food_id
	myr.hset(cache_key, 'stock', food['stock'])
	myr.hset(cache_key, 'price', food['price'])
	myr.hset(cache_key, 'cache_time', time())

# cart relative #

def cart_new(user_id):
	cart_id = "%032d" % myr.incr('CART_ID')
	myr.set("USER_CART_%d_%s" % (user_id, cart_id), 1)
	return cart_id

def cart_exists(cart_id):
	max_cart_id = int(myr.get('CART_ID'))
	cid = int(cart_id)
	return (cid >= 0 and cid <= max_cart_id)

def cart_belongs(cart_id, user_id):
	key = "USER_CART_%d_%s" %(user_id, cart_id)
	return  myr.get(key) == 1

def cart_data(cart_id):
	data = []
	arr = myr.smembers("CART_"+cart_id)
	for i in range(0, len(arr)):
		food_id = int(arr[i])
		count = myr.get("COUNT_%s_%d" % (cart_id, food_id))
		data.append({'food_id': food_id, 'count': count})

def cart_patch(cart_id, food_id, count):
	myr.sadd("CART_" + cart_id, food_id)
	k = "COUNT_%s_%d" % (cart_id, food_id)
	oc = myr.get(k)
	if not oc:
		oc = 0
	else:
		oc = int(oc)
	c = oc + count
	if c < 0:
		c = 0
	myr.set(k, c)


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
	cart_id = cart_new(user_id)
	return my_response({'cart_id': cart_id})

@app.route('/carts/<cart_id>', methods=["PATCH"])
def patch_carts():
	user_id = authorize()
	if isinstance(user_id, Response):
		return user_id
	data = check_data()
	if isinstance(data, Response):
		return data
	if not cart_exists(cart_id):
		return my_response({"code": "CART_NOT_FOUND", "message": "篮子不存在"}, 404, "Not Found")
	if not cart_belongs(cart_id, user_id):
		return my_response({"code": "NOT_AUTHORIZED_TO_ACCESS_CART", "message": "无权限访问指定的篮子"}, 401, "Unauthorized")
	food_id = data['food_id']
	count = data['count']
	food = get_food(food_id)
	if not food:
		return my_response({"code": "FOOD_NOT_FOUND", "message": "食物不存在"}, 404, "Not Found")
	if count > food['stock']:
		return my_response({"code": "FOOD_OUT_OF_STOCK", "message": "食物库存不足"}, 403, "Forbidden")
	old = cart_data(cart_id)
	total = count
	for i in range(0, len(old)):
		total = total + old[i]['count']
		if total > 3:
			return my_response({"code": "FOOD_OUT_OF_LIMIT", "message": "篮子中食物数量超过了三个"}, 403, "Forbidden");
	cart_add(cart_id, food_id, count)
	return my_response(None, 204, "No content")

# @app.route('/orders', methods=["POST"])
# def orders():
# 	user_id = authorize()
# 	if isinstance(user_id, Response):
# 		return user_id
# 	data = check_data()
# 	if isinstance(data, Response):
# 		return data
# 	cart_id = data['cart_id']
	


if __name__ == '__main__':
    app.run(host=host, port=port, debug=True)

