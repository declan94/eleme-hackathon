#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
from time import time, sleep

from flask import Flask
from flask import request
from flask import Response
import json

from db_manager import get_db, get_redis_store

host = os.getenv("APP_HOST", "localhost")
port = int(os.getenv("APP_PORT", "8080"))

app = Flask(__name__)
redis_store = get_redis_store()

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
	p = redis_store.get("dd.user%s.password" % name)
	if p != password:
		return False
	user_id = int(redis_store.get("dd.user%s.id" % name))
	access_token = "%d" % user_id
	redis_store.set("dd.access%s" % access_token, user_id)
	return (user_id, access_token)

def check_login2(name, password):
	db = get_db()
	row = db.select("select id from user where name='%s' and password='%s' limit 1" % (name, password))
	if not row or len(row) == 0:
		return False
	user_id = row[0][0]
	access_token = "%d" % user_id
	redis_store.set("dd.access%s" % access_token, user_id)
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
	key = "dd.access%s" % access_token
	user_id = redis_store.get(key)
	if user_id == None:
		return unauthorized()
	else:
		return int(user_id)

# food relative #

def food_key(food_id, field = "stock"):
	return "dd.food%d.%s" % (food_id, field)

def food_field(food_id, field = "stock"):
	return int(redis_store.get(food_key(food_id, field)))

def food_exists(food_id):
	return redis_store.get(food_key(food_id)) != None

# cart relative #

def cart_new(user_id):
	cart_id = "%d" % redis_store.incr('dd.cart.id')
	redis_store.set("dd.user%d.cart%s" % (user_id, cart_id), '1')
	return cart_id

def cart_exists(cart_id):
	max_cart_id = int(redis_store.get('dd.cart.id'))
	cid = int(cart_id)
	return (cid >= 0 and cid <= max_cart_id)

def cart_belongs(cart_id, user_id):
	key = "dd.user%d.cart%s" %(user_id, cart_id)
	return  redis_store.get(key) == '1'

def cart_data(cart_id):
	data = []
	fid_set = redis_store.smembers("CART_"+cart_id)
	for food_id in fid_set:
		count = redis_store.get("COUNT_%s_%s" % (cart_id, food_id))
		if count:
			count = int(count)
		else:
			count = 0
		data.append({'food_id': int(food_id), 'count': count})
	return data

def cart_patch(cart_id, food_id, count):
	redis_store.sadd("CART_" + cart_id, food_id)
	k = "COUNT_%s_%d" % (cart_id, food_id)
	oc = redis_store.get(k)
	if not oc:
		oc = 0
	else:
		oc = int(oc)
	c = oc + count
	if c < 0:
		c = 0
	redis_store.set(k, c)

# order relative #

def user_order_id(user_id):
	return redis_store.get("ORDER_%d" % user_id)

def set_user_order_id(user_id, order_id):
	redis_store.set("ORDER_%d" % user_id, order_id)

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
	pipe = redis_store.pipeline()
	while True:
		for i in range(0, len(cart)):
			food_id = cart[i]['food_id']
			pipe.watch(food_key(food_id))
			stock = food_field(food_id)
			if stock < cart[i]['count']:
				pipe.unwatch()
				return False
			cart[i]['stock'] = stock
		pipe.multi()
		for i in range(0, len(cart)):
			item = cart[i]
			food_id = item['food_id']
			new_stock = item['stock'] - item['count']
			pipe.set(food_key(food_id), new_stock)
		try:
			pipe.execute()
			break
		except WatchError:
			continue
	return True

def order_single_food(food):
	food_id = food['food_id']
	count = food['count']
	k = food_key(food_id)
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
	# a = int(redis_store.get("dd.food.min_id"))
	# b = int(redis_store.get("dd.food.max_id"))
	# foods = []
	# for food_id in range(a, b+1):
	# 	stock = food_field(food_id)
	# 	price = food_field(food_id, "price")
	# 	foods.append({"id": food_id, "stock": stock, "price": price})
	# 
	# db = get_db()
	# foods = db.select('select * from food', is_dict=True)
	# db.close()
	# 
	temp = redis_store.get('dd.food.json')
	foods = json.loads(temp)
	return my_response(foods)

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
	if len(cart) == 1:
		ret = order_single_food(cart[0])
	else:
		ret = order_muti_foods(cart)
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
	min_user_id = int(redis_store.get('dd.user.min_id'))
	max_user_id = int(redis_store.get('dd.user.max_id'))
	for i in range(min_user_id, max_user_id+1):
		user_id = users[i][0]
		order = user_order(user_id)
		if order:
			orders.append(order)
	return my_response(orders)



if __name__ == '__main__':
    app.run(host=host, port=port, debug=True)

