#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from time import time

from flask import Flask
from flask import request
from flask import Response
import json

from DB import DB
from my_redis import myr

host = os.getenv("APP_HOST", "localhost")
port = int(os.getenv("APP_PORT", "8080"))
db_host = os.getenv("DB_HOST", "localhost")
db_port = int(os.getenv("DB_PORT", 3306))
db_name = os.getenv("DB_NAME", "eleme")
db_user = os.getenv("DB_USER", "root")
db_pass = os.getenv("DB_PASS", "toor")

def conn_db():
	db = DB(False, host = db_host, user = db_user, passwd = db_pass, db = db_name, port = db_port)
	return db

db = conn_db()
rows = db.select('select min(id) from food')
min_food_id = rows[0][0]
rows = db.select('select max(id) from food')
max_food_id = rows[0][0]
db.close()

app = Flask(__name__)

@app.route('/')
def hello_world():
    return 'Hello World!'


############### special responses ###############

def my_response(data, status_code = 200, status = "ok"):
	r = Response()
	r.status = status
	r.status_code = status_code
	if data != None:
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

def get_food(food_id, use_cache = True):
	db = conn_db()
	cached = None
	if use_cache:
		cached = get_cached_food(food_id)
	if cached:
		return cached
	db = conn_db()
	rows = db.select("select `stock`, `price` from `food` where id = %d limit 1" % food_id)
	db.close()
	if not rows or len(rows) == 0:
		return None
	else:
		food = {'id': food_id, 'stock': rows[0][0], 'price': rows[0][1]}
		cache_food(food)
		return food

def get_cached_food(food_id):
	cache_key = "FOOD_%d" % food_id
	ct = myr.hget(cache_key, 'cache_time')
	if not ct or time() - float(ct) > 500:
		return None
	stock = myr.hget(cache_key, 'stock')
	price = myr.hget(cache_key, 'price')
	food = {'id': food_id, 'stock': int(stock), 'price': int(price)}
	return food

def cache_food(food):
	food_id = food['id']
	cache_key = "FOOD_%d" % food_id
	myr.hset(cache_key, 'stock', food['stock'])
	myr.hset(cache_key, 'price', food['price'])
	myr.hset(cache_key, 'cache_time', time())

def food_exists(food_id):
	return food_id >= min_food_id and food_id <= max_food_id

# cart relative #

def cart_new(user_id):
	cart_id = "%032d" % myr.incr('CART_ID')
	myr.set("USER_CART_%d_%s" % (user_id, cart_id), '1')
	return cart_id

def cart_exists(cart_id):
	max_cart_id = int(myr.get('CART_ID'))
	cid = int(cart_id)
	return (cid >= 0 and cid <= max_cart_id)

def cart_belongs(cart_id, user_id):
	key = "USER_CART_%d_%s" %(user_id, cart_id)
	return  myr.get(key) == '1'

def cart_data(cart_id):
	data = []
	fid_set = myr.smembers("CART_"+cart_id)
	for food_id in fid_set:
		count = myr.get("COUNT_%s_%s" % (cart_id, food_id))
		if count:
			count = int(count)
		else:
			count = 0
		data.append({'food_id': int(food_id), 'count': count})
	return data

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

# order relative #

def user_order_id(user_id):
	return myr.get("ORDER_%d" % user_id)

def set_user_order_id(user_id, order_id):
	myr.set("ORDER_%d" % user_id, order_id)

def user_order(user_id):
	order_id = user_order_id(user_id)
	if not order_id:
		return None
	items = cart_data(order_id)
	total = 0
	for i in range(0, len(items)):
		item = items[i]
		food = get_food(int(item['food_id']))
		total = total + food['price'] * item['count']
	return {"id": order_id, "items": items, "total": total}


############### view functions ###############

@app.route('/login', methods=["POST"])
def login():
	data = check_data()
	if isinstance(data, Response):
		return data
	username = data['username']
	password = data['password']
	db = conn_db()
	rows = db.select("select `id` from user where name='%s' and password='%s' limit 1" % (username, password))
	db.close()
	r = Response()
	if rows and len(rows) > 0:
		user_id = rows[0][0]
		access_token = "%d" % user_id
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
	db = conn_db()
	rows = db.select("select * from food", is_dict = True)
	db.close()
	return my_response(rows)

@app.route('/carts', methods=["POST"])
def carts():
	user_id = authorize()
	if isinstance(user_id, Response):
		return user_id
	cart_id = cart_new(user_id)
	return my_response({'cart_id': cart_id})

@app.route('/carts/<cart_id>', methods=["PATCH"])
def patch_carts(cart_id):
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
	food_id = int(data['food_id'])
	count = data['count']
	# 策略一 - 从数据库获取food信息，redis缓存
	# food = get_food(food_id)
	# if not food:
		# return my_response({"code": "FOOD_NOT_FOUND", "message": "食物不存在"}, 404, "Not Found")
	# 策略二 - 设定food_id连续，根据food_id大小判定
	if not food_exists(food_id):
		return my_response({"code": "FOOD_NOT_FOUND", "message": "食物不存在"}, 404, "Not Found")
	# orders再判断库存
	# if count > food['stock']:
	# 	return my_response({"code": "FOOD_OUT_OF_STOCK", "message": "食物库存不足"}, 403, "Forbidden")
	total = count
	if total > 3:
		return my_response({"code": "FOOD_OUT_OF_LIMIT", "message": "篮子中食物数量超过了三个"}, 403, "Forbidden");
	old = cart_data(cart_id)
	if old:
		for i in range(0, len(old)):
			total = total + old[i]['count']
			if total > 3:
				return my_response({"code": "FOOD_OUT_OF_LIMIT", "message": "篮子中食物数量超过了三个"}, 403, "Forbidden");
	if not user_order_id(user_id):
		cart_patch(cart_id, food_id, count)
	return my_response(None, 204, "No content")

@app.route('/orders', methods=["POST"])
def make_orders():
	user_id = authorize()
	if isinstance(user_id, Response):
		return user_id
	data = check_data()
	if isinstance(data, Response):
		return data
	cart_id = data['cart_id']
	if not cart_exists(cart_id):
		return my_response({"code": "CART_NOT_FOUND", "message": "篮子不存在"}, 404, "Not Found")
	if not cart_belongs(cart_id, user_id):
		return my_response({"code": "NOT_AUTHORIZED_TO_ACCESS_CART", "message": "无权限访问指定的篮子"}, 403, "Forbidden")
	if user_order_id(user_id) != None:
		return my_response({"code": "ORDER_OUT_OF_LIMIT", "message": "每个用户只能下一单"}, 403, "Forbidden")
	cart = cart_data(cart_id)
	# 策略一 - 原始策略 - autocommit开
	# db.execute("LOCK TABLE food WRITE")
	# for i in range(0, len(cart)):
	# 	item = cart[i]
	# 	food = get_food(item['food_id'], False)
	# 	if food['stock'] < item['count']:
	# 		db.execute("UNLOCK TABLE")
	# 		return my_response({"code": "FOOD_OUT_OF_STOCK", "message": "食物库存不足"}, 403, "Forbidden")
	# 	item['stock'] = food['stock']
	# for i in range(0, len(cart)):
	# 	item = cart[i]
	# 	new_stock = item['stock'] - item['count']
	# 	db.update("food", {"stock": new_stock}, {"id": item['food_id']})
	# db.execute("UNLOCK TABLE")

	# 策略二 - autocommit 关
	db = conn_db()
	for i in range(0, len(cart)):
		item = cart[i]
		sql = "update `food` set stock = stock - %d where id = %d and stock >= %d" % (item['count'], item['food_id'], item['count'])
		db.execute(sql)
		if db.affected_rows() == 0:
			db.rollback()
			return my_response({"code": "FOOD_OUT_OF_STOCK", "message": "食物库存不足"}, 403, "Forbidden")
	db.commit()
	db.close()
	order_id = cart_id
	set_user_order_id(user_id, order_id)
	return my_response({"id": order_id})

@app.route('/orders')
def get_orders():
	user_id = authorize()
	if isinstance(user_id, Response):
		return user_id
	order = user_order(user_id)
	if not order:
		return my_response([])
	else:
		return my_response([order])

@app.route('/admin/orders')
def all_orders():
	db = conn_db()
	users = db.select("select id from user")
	db.close()
	orders = []
	for i in range(0, len(users)):
		user_id = users[i][0]
		order = user_order(user_id)
		if order:
			orders.append(order)
	return my_response(orders)



if __name__ == '__main__':
    app.run(host=host, port=port, debug=True)

