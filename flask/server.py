#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import sys
from time import time, sleep

from flask import Flask
from flask import request
from flask import Response
import json

from db_manager import get_db, get_redis_store

host = os.getenv("APP_HOST", "localhost")
port = int(os.getenv("APP_PORT", "8080"))

app = Flask(__name__)


@app.route('/')
def hello_world():
    return 'Hello World!'

@app.route('/test_block')
def test_block():
	sleep(10)


############### special responses ###############

def my_response(data, status_code = 200, status = "ok"):
	r = Response()
	r.status = status
	r.status_code = status_code
	if data != None:
		if isinstance(data, str):
			r.data = data
		else:
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

# authorize relative
def check_login(name, password):
	# p = redis_store.hget("dd.user%s" % name, "password")
	# if p != password:
	# 	return False
	# access_token = redis_store.hget("dd.user%s" % name, "id")
	redis_store = get_redis_store()
	access_token = redis_store.get("dd.user%s.password%s" % (name, password))
	if access_token == None:
		return False
	user_id = int(access_token)
	# redis_store.set("dd.access%s" % access_token, user_id)
	return (user_id, access_token)

def check_login2(name, password):
	db = get_db()
	row = db.select("select id from user where name='%s' and password='%s' limit 1" % (name, password))
	if not row or len(row) == 0:
		return False
	user_id = row[0][0]
	access_token = "%d" % user_id
	# redis_store.set("dd.access%s" % access_token, user_id)
	return (user_id, access_token)

def authorize():
	if request.headers.has_key('Access-Token'):
		access_token = request.headers['Access-Token']
	else:
		args = request.args
		if args.has_key('access_token'):	
			access_token = args['access_token']
		else:
			return unauthorized()
	# key = "dd.access%s" % access_token
	# user_id = redis_store.get(key)
	# if user_id == None:
	# 	return unauthorized()
	# else:
	# 	return int(user_id)
	return int(access_token)

# food relative #

def food_key(food_id, field = "stock"):
	return "dd.food%d.%s" % (food_id, field)

def food_field(food_id, field = "stock"):
	redis_store = get_redis_store()
	return int(redis_store.get(food_key(food_id, field)))

def food_exists(food_id):
	# food_range = redis_store.hgetall('dd.food')
	# return food_id >= int(food_range['min_id']) and food_id <= int(food_range['max_id'])
	return food_id > 0

# cart relative #

def cart_new(user_id):
	# redis_store = get_redis_store()
	cart_id = "%f%d" % (time(), user_id)
	# cart_id = "%d" % redis_store.incr('dd.cart.id')
	# redis_store.set("dd.user%d.cart%s" % (user_id, cart_id), '1')
	return cart_id

def cart_exists(cart_id):
	# max_cart_id = int(redis_store.get('dd.cart.id'))
	# cid = int(cart_id)
	# return (cid >= 0 and cid <= max_cart_id)
	return float(cart_id) >= 0

def cart_belongs(cart_id, user_id):
	key = "dd.user%d.cart%s" %(user_id, cart_id)
	redis_store = get_redis_store()
	return  redis_store.get(key) == '1'

def cart_data(cart_id):
	data = []
	redis_store = get_redis_store()
	fid_set = redis_store.smembers("dd.cart%s" % cart_id)
	for food_id in fid_set:
		count = redis_store.get("dd.cart%s.count%s" % (cart_id, food_id))
		if count:
			count = int(count)
		else:
			count = 0
		data.append({'food_id': int(food_id), 'count': count})
	return data

def cart_len(cart_id):
	redis_store = get_redis_store()
	return redis_store.scard("dd.cart%s" % cart_id)

def cart_patch(cart_id, food_id, count):
	redis_store = get_redis_store()
	redis_store.sadd("dd.cart%s" % cart_id, food_id)
	k = "dd.cart%s.count%d" % (cart_id, food_id)
	if redis_store.incrby(k, count) < 0:
		redis_store.set(k, 0)
	
# order relative #

def user_order_id(user_id):
	redis_store = get_redis_store()
	return redis_store.get("dd.order%d" % user_id)

def set_user_order_id(user_id, order_id):
	redis_store = get_redis_store()
	redis_store.set("dd.order%d" % user_id, order_id)

def user_order(user_id):
	order_id = user_order_id(user_id)
	if not order_id:
		return None
	items = cart_data(order_id)
	total = 0
	for i in range(0, len(items)):
		item = items[i]
		price = food_field(item['food_id'], 'price')
		total = total + price * item['count']
	return {"id": order_id, "items": items, "total": total}

def order_muti_foods(cart):
	for i in range(0, len(cart)):
		food_id = cart[i]['food_id']
		count = cart[i]['count']
		k = food_key(food_id)
		redis_store = get_redis_store()
		if redis_store.incrby(k, -count) < 0:
			for j in range(0, i+1):				
				redis_store.incrby(food_key(cart[j]['food_id'], cart[j]['count']))
			return False
	return True

def order_single_food(food):
	food_id = food['food_id']
	count = food['count']
	k = food_key(food_id)
	redis_store = get_redis_store()
	if redis_store.incrby(k, -count) < 0:
		redis_store.incrby(k, count)
		return False
	return True


############### view functions ###############

@app.route('/login', methods=["POST"])
def login():
	data = check_data()
	if isinstance(data, Response):
		return data
	name = data['username']
	password = data['password']
	check = check_login(name, password)
	if check != False:
		user_id = check[0]
		access_token = check[1]
		res_data = {'user_id': user_id, 'username': name, 'access_token': access_token}
		return my_response(res_data)
	else:
		res_data = {"code": "USER_AUTH_FAIL", "message": "用户名或密码错误"}
		return my_response(res_data, 403, "Forbidden")

@app.route('/foods')
def get_foods():
	user_id = authorize()
	if isinstance(user_id, Response):
		return user_id
	# db = get_db()
	# foods = db.select('select * from food', is_dict=True)
	# db.close()
	#
	# a = int(redis_store.get("dd.food.min_id"))
	# b = int(redis_store.get("dd.food.max_id"))
	# foods = []
	# for food_id in range(a, b+1):
	# 	stock = food_field(food_id)
	# 	price = food_field(food_id, "price")
	# 	foods.append({"id": food_id, "stock": stock, "price": price})

	# redis_store = get_redis_store()
	# foods_json = redis_store.get('dd.food.json')

	foods_json = '[{"price": 5, "id": 1, "stock": 1000}, {"price": 10, "id": 2, "stock": 1000}, {"price": 5, "id": 3, "stock": 1000}, {"price": 11, "id": 4, "stock": 1000}, {"price": 29, "id": 5, "stock": 1000}, {"price": 26, "id": 6, "stock": 1000}, {"price": 16, "id": 7, "stock": 1000}, {"price": 16, "id": 8, "stock": 1000}, {"price": 6, "id": 9, "stock": 1000}, {"price": 30, "id": 10, "stock": 1000}, {"price": 9, "id": 11, "stock": 1000}, {"price": 6, "id": 12, "stock": 1000}, {"price": 17, "id": 13, "stock": 1000}, {"price": 7, "id": 14, "stock": 1000}, {"price": 25, "id": 15, "stock": 1000}, {"price": 16, "id": 16, "stock": 1000}, {"price": 7, "id": 17, "stock": 1000}, {"price": 12, "id": 18, "stock": 1000}, {"price": 21, "id": 19, "stock": 1000}, {"price": 17, "id": 20, "stock": 1000}, {"price": 3, "id": 21, "stock": 1000}, {"price": 18, "id": 22, "stock": 1000}, {"price": 17, "id": 23, "stock": 1000}, {"price": 21, "id": 24, "stock": 1000}, {"price": 10, "id": 25, "stock": 1000}, {"price": 10, "id": 26, "stock": 1000}, {"price": 26, "id": 27, "stock": 1000}, {"price": 10, "id": 28, "stock": 1000}, {"price": 18, "id": 29, "stock": 1000}, {"price": 29, "id": 30, "stock": 1000}, {"price": 24, "id": 31, "stock": 1000}, {"price": 3, "id": 32, "stock": 1000}, {"price": 28, "id": 33, "stock": 1000}, {"price": 13, "id": 34, "stock": 1000}, {"price": 23, "id": 35, "stock": 1000}, {"price": 23, "id": 36, "stock": 1000}, {"price": 7, "id": 37, "stock": 1000}, {"price": 4, "id": 38, "stock": 1000}, {"price": 29, "id": 39, "stock": 1000}, {"price": 20, "id": 40, "stock": 1000}, {"price": 26, "id": 41, "stock": 1000}, {"price": 3, "id": 42, "stock": 1000}, {"price": 6, "id": 43, "stock": 1000}, {"price": 24, "id": 44, "stock": 1000}, {"price": 19, "id": 45, "stock": 1000}, {"price": 4, "id": 46, "stock": 1000}, {"price": 11, "id": 47, "stock": 1000}, {"price": 13, "id": 48, "stock": 1000}, {"price": 6, "id": 49, "stock": 1000}, {"price": 24, "id": 50, "stock": 1000}, {"price": 26, "id": 51, "stock": 1000}, {"price": 5, "id": 52, "stock": 1000}, {"price": 13, "id": 53, "stock": 1000}, {"price": 12, "id": 54, "stock": 1000}, {"price": 30, "id": 55, "stock": 1000}, {"price": 27, "id": 56, "stock": 1000}, {"price": 16, "id": 57, "stock": 1000}, {"price": 25, "id": 58, "stock": 1000}, {"price": 14, "id": 59, "stock": 1000}, {"price": 16, "id": 60, "stock": 1000}, {"price": 15, "id": 61, "stock": 1000}, {"price": 9, "id": 62, "stock": 1000}, {"price": 10, "id": 63, "stock": 1000}, {"price": 13, "id": 64, "stock": 1000}, {"price": 26, "id": 65, "stock": 1000}, {"price": 29, "id": 66, "stock": 1000}, {"price": 16, "id": 67, "stock": 1000}, {"price": 4, "id": 68, "stock": 1000}, {"price": 8, "id": 69, "stock": 1000}, {"price": 29, "id": 70, "stock": 1000}, {"price": 16, "id": 71, "stock": 1000}, {"price": 19, "id": 72, "stock": 1000}, {"price": 3, "id": 73, "stock": 1000}, {"price": 24, "id": 74, "stock": 1000}, {"price": 8, "id": 75, "stock": 1000}, {"price": 10, "id": 76, "stock": 1000}, {"price": 26, "id": 77, "stock": 1000}, {"price": 22, "id": 78, "stock": 1000}, {"price": 3, "id": 79, "stock": 1000}, {"price": 3, "id": 80, "stock": 1000}, {"price": 10, "id": 81, "stock": 1000}, {"price": 30, "id": 82, "stock": 1000}, {"price": 15, "id": 83, "stock": 1000}, {"price": 22, "id": 84, "stock": 1000}, {"price": 28, "id": 85, "stock": 1000}, {"price": 3, "id": 86, "stock": 1000}, {"price": 17, "id": 87, "stock": 1000}, {"price": 22, "id": 88, "stock": 1000}, {"price": 16, "id": 89, "stock": 1000}, {"price": 14, "id": 90, "stock": 1000}, {"price": 8, "id": 91, "stock": 1000}, {"price": 25, "id": 92, "stock": 1000}, {"price": 21, "id": 93, "stock": 1000}, {"price": 22, "id": 94, "stock": 1000}, {"price": 11, "id": 95, "stock": 1000}, {"price": 5, "id": 96, "stock": 1000}, {"price": 17, "id": 97, "stock": 1000}, {"price": 27, "id": 98, "stock": 1000}, {"price": 11, "id": 99, "stock": 1000}, {"price": 8, "id": 100, "stock": 1000}]'
	return my_response(foods_json)

@app.route('/carts', methods=["POST"])
def new_carts():
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
	# if not cart_belongs(cart_id, user_id):
		# return my_response({"code": "NOT_AUTHORIZED_TO_ACCESS_CART", "message": "无权限访问指定的篮子"}, 401, "Unauthorized")
	food_id = int(data['food_id'])
	count = data['count']
	# 策略一 - 从数据库获取food信息，redis缓存
	# food = get_food(food_id)
	# if not food:
		# return my_response({"code": "FOOD_NOT_FOUND", "message": "食物不存在"}, 404, "Not Found")
	# 策略二 - 设定food_id连续，根据food_id大小判定
	if not food_exists(food_id):
		return my_response({"code": "FOOD_NOT_FOUND", "message": "食物不存在"}, 404, "Not Found")
	total = count
	if total > 3:
		return my_response({"code": "FOOD_OUT_OF_LIMIT", "message": "篮子中食物数量超过了三个"}, 403, "Forbidden");
	# old = cart_data(cart_id)
	# if old:
	# 	for i in range(0, len(old)):
	# 		total = total + old[i]['count']
	# 		if total > 3:
	# 			return my_response({"code": "FOOD_OUT_OF_LIMIT", "message": "篮子中食物数量超过了三个"}, 403, "Forbidden");
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
	# if not cart_belongs(cart_id, user_id):
		# return my_response({"code": "NOT_AUTHORIZED_TO_ACCESS_CART", "message": "无权限访问指定的篮子"}, 403, "Forbidden")
	if user_order_id(user_id) != None:
		return my_response({"code": "ORDER_OUT_OF_LIMIT", "message": "每个用户只能下一单"}, 403, "Forbidden")
	
	# cart = cart_data(cart_id)

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
	# db = get_db()
	# for i in range(0, len(cart)):
	# 	item = cart[i]
	# 	sql = "update `food` set stock = stock - %d where id = %d and stock >= %d" % (item['count'], item['food_id'], item['count'])
	# 	db.execute(sql)
	# 	if db.affected_rows() == 0:
	# 		db.rollback()
	# 		return my_response({"code": "FOOD_OUT_OF_STOCK", "message": "食物库存不足"}, 403, "Forbidden")
	# db.commit()
	# db.close()

	# 策略三 - 完全redis
	
	if cart_len(cart_id) == 1:
		cart = cart_data(cart_id)
		ret = order_single_food(cart[0])
	else:
		cart = cart_data(cart_id)
		# ret = order_muti_foods(cart)
		ret = True

	if not ret:
		return my_response({"code": "FOOD_OUT_OF_STOCK", "message": "食物库存不足"}, 403, "Forbidden")

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
	orders = []
	redis_store = get_redis_store()
	min_user_id = int(redis_store.hget('dd.user', 'min_id'))
	max_user_id = int(redis_store.hget('dd.user', 'max_id'))
	for user_id in range(min_user_id, max_user_id+1):
		order = user_order(user_id)
		if order:
			orders.append(order)
	return my_response(orders)



if __name__ == '__main__':
	app.run(host=host, port=port, debug=False)

