# -*- coding: utf-8 -*-

import os
import redis 

# 连接，可选不同数据库 
redis_host = os.getenv('REDIS_HOST', "localhost")
redis_port = int(os.getenv('REDIS_PORT', 6379))
r = redis.Redis(host=redis_host, port=redis_port)


r.set('a', 'A')
print r.get('a')
print r.get('c')

