package main

import (
	"os"
	"fmt"
	"net/http"
	"encoding/json"
	"strings"
	"strconv"
	"math/rand"
	"time"
	"runtime"
	"github.com/garyburd/redigo/redis"
	"mycache"
)

//----------------------------------
// Request JSON Bindings
//----------------------------------
type RequestLogin struct {
	Username string `json:"username"`
	Password string `json:"password"`
}

type RequestPatchCart struct {
	FoodId int `json:"food_id"`
	Count  int `json:"count"`
}

type RequestMakeOrder struct {
	CartId string `json:"cart_id"`
}

//----------------------------------
// Response JSON Bindings
//----------------------------------
type ResponseLogin struct {
	UserId      int    `json:"user_id"`
	UserName    string `json:"username"`
	AccessToken string `json:"access_token"`
}

type ResponseCreateCart struct {
	CartId string `json:"cart_id"`
}

type OrderItem struct {
	FoodId int `json:"food_id"`
	Count  int `json:"count"`
}

type ResponseOrder struct {
	Id   string 		`json:"id"`
	Items []OrderItem 	`json:"items"`
	Total int 			`json:"total"`
}

type ResponseAdminOrder struct {
	UserId 	int 			`json:"user_id"`
	Id   	string 			`json:"id"`
	Items 	[]OrderItem 	`json:"items"`
	Total 	int 			`json:"total"`
}

var (
	redis_pool  *redis.Pool
)

func main() {
	InitRedis()
	foods := mycache.LoadData()
	rc := redis_pool.Get()
	defer rc.Close()
	for _, f := range foods {
		rc.Do("SET", FoodStockKey(f.Id), f.Stock)
	}
	runtime.GOMAXPROCS(runtime.NumCPU())
	RunServer()
}

func InitRedis() {
	redis_host := os.Getenv("REDIS_HOST")
	redis_port := os.Getenv("REDIS_PORT")
	if redis_host == "" {
		redis_host = "localhost"
	}
	if redis_port == "" {
		redis_port = "6379"
	}
	redis_addr := fmt.Sprintf("%s:%s", redis_host, redis_port)
	// 建立连接池
	redis_pool = &redis.Pool{
		MaxIdle: 1,
		MaxActive: 10,
		IdleTimeout: 180 * time.Second,
		Dial: func() (redis.Conn, error) {
			c, err := redis.Dial("tcp", redis_addr)
			if err != nil {
				return nil, err
			}
			return c, nil
		},
	}
	rc := redis_pool.Get()
	defer rc.Close()
	rc.Do("FLUSHDB")
}

func RunServer() {
	host := os.Getenv("APP_HOST")
	port := os.Getenv("APP_PORT")
	if host == "" {
		host = "localhost"
	}
	if port == "" {
		port = "8080"
	}
	addr := fmt.Sprintf("%s:%s", host, port)
	http.HandleFunc("/login", Login)
	http.HandleFunc("/foods", Foods)
	http.HandleFunc("/carts", NewCart)
	http.HandleFunc("/carts/", PatchCart)
	http.HandleFunc("/orders", Orders)
	http.HandleFunc("/admin/orders", AllOrders)
	fmt.Printf("Listen And Serve On: %s \n", addr)
	http.ListenAndServe(addr, nil)
}

// /login
func Login(w http.ResponseWriter, r * http.Request) {
	data := &RequestLogin{}
	err := DecodeData(r, data)
	if err > 0 {
		ResponseBadReq(&w, err)
		return
	}
	user_id, token := DoLogin(data)
	if user_id > 0 {
		res_data := &ResponseLogin{user_id, data.Username, token}
		ResponseJson(&w, res_data, http.StatusOK)
	} else {
		res_data := &map[string]string {"code": "USER_AUTH_FAIL", "message": "用户名或密码错误"}
		ResponseJson(&w, res_data, http.StatusForbidden)
	}
}

// /foods
func Foods(w http.ResponseWriter, r * http.Request) {
	user_id := Authorize(r)
	if user_id == 0 {
		ResponseUnauthorized(&w)
		return
	}
	food_json := mycache.FoodJson()
	Response(&w, food_json, http.StatusOK)
}

// /carts
func NewCart(w http.ResponseWriter, r * http.Request) {
	user_id := Authorize(r)
	if user_id == 0 {
		ResponseUnauthorized(&w)
		return
	}
	cart_id := CartCreate(user_id)
	res_data := &map[string]string {"cart_id": cart_id}
	ResponseJson(&w, res_data, http.StatusOK)
}

// /carts/<cart_id>
func PatchCart(w http.ResponseWriter, r * http.Request) {
	user_id := Authorize(r)
	if user_id == 0 {
		ResponseUnauthorized(&w)
		return
	}
	data := &RequestPatchCart{}
	err := DecodeData(r, data)
	if err > 0 {
		ResponseBadReq(&w, err)
		return
	}
	l := strings.Split(r.URL.Path, "/")
	cart_id := l[len(l)-1]
	if !CartExists(cart_id) {
		res_data := &map[string]string {"code": "CART_NOT_FOUND", "message": "篮子不存在"}
		ResponseJson(&w, res_data, http.StatusNotFound)
		return
	}
	if !CartBelongs(cart_id, user_id) {
		res_data := &map[string]string {"code": "NOT_AUTHORIZED_TO_ACCESS_CART", "message": "无权限访问指定的篮子"}
		ResponseJson(&w, res_data, http.StatusUnauthorized)
		return	
	}
	if data.FoodId <= 0 {
		res_data := &map[string]string {"code": "FOOD_NOT_FOUND", "message": "食物不存在"}
		ResponseJson(&w, res_data, http.StatusNotFound)
		return
	}
	rc := redis_pool.Get()
	defer rc.Close()
	old_count := CartCount(rc, cart_id)
	total := data.Count + old_count
	if total > 3 {
		res_data := &map[string]string {"code": "FOOD_OUT_OF_LIMIT", "message": "篮子中食物数量超过了三个"}
		ResponseJson(&w, res_data, http.StatusForbidden)
		return
	}
	if UserOrderId(rc, user_id) == "" {
		CartPatch(rc, cart_id, data)
	}
	w.WriteHeader(http.StatusNoContent)
}

func MakeOrder(w http.ResponseWriter, r * http.Request, user_id int) {
	data := &RequestMakeOrder{}
	err := DecodeData(r, data)
	if err > 0 {
		ResponseBadReq(&w, err)
		return
	}
	if !CartExists(data.CartId) {
		res_data := &map[string]string {"code": "CART_NOT_FOUND", "message": "篮子不存在"}
		ResponseJson(&w, res_data, http.StatusNotFound)
		return
	}
	if !CartBelongs(data.CartId, user_id) {
		res_data := &map[string]string {"code": "NOT_AUTHORIZED_TO_ACCESS_CART", "message": "无权限访问指定的篮子"}
		ResponseJson(&w, res_data, http.StatusUnauthorized)
		return	
	}
	rc := redis_pool.Get()
	defer rc.Close()
	if UserOrderId(rc, user_id) != "" {
		res_data := &map[string]string {"code": "ORDER_OUT_OF_LIMIT", "message": "每个用户只能下一单"}
		ResponseJson(&w, res_data, http.StatusForbidden)
		return
	}
	suc := OrderCart(rc, data.CartId)
	if !suc {
		res_data := &map[string]string {"code": "FOOD_OUT_OF_STOCK", "message": "食物库存不足"}
		ResponseJson(&w, res_data, http.StatusForbidden)
		return	
	}
	SetUserOrderId(rc, user_id, data.CartId)
	res_data := &map[string]string {"id": data.CartId}
	ResponseJson(&w, res_data, http.StatusOK)
}

func GetOrders(w http.ResponseWriter, r * http.Request, user_id int) {
	rc := redis_pool.Get()
	defer rc.Close()
	order := UserOrder(rc, user_id)
	orders := make([]ResponseOrder, 0)
	if order != nil {
		orders = append(orders, (*order))
	}
	ResponseJson(&w, &orders, http.StatusOK)
}

// /orders
func Orders(w http.ResponseWriter, r * http.Request) {
	user_id := Authorize(r)
	if user_id == 0 {
		ResponseUnauthorized(&w)
		return
	}
	if r.Method == "POST" {
		MakeOrder(w, r, user_id)
	} else {
		GetOrders(w, r, user_id)
	}
}

// /admin/orders
func AllOrders(w http.ResponseWriter, r * http.Request) {
	user_id := Authorize(r)
	if user_id == 0 {
		ResponseUnauthorized(&w)
		return
	}
	rc := redis_pool.Get()
	defer rc.Close()
	orders := make([]ResponseAdminOrder, 0)
	for _, uid := range mycache.UserIds() {
		o := UserOrder(rc, uid)
		if o != nil {
			order := ResponseAdminOrder{uid, (*o).Id, (*o).Items, (*o).Total}
			orders = append(orders, order)
		}
	}
	ResponseJson(&w, &orders, http.StatusOK)
}


/* responses */

func Response(w * http.ResponseWriter, data []byte, code int) {
	(*w).WriteHeader(code)
	(*w).Write(data)
}

func ResponseJson(w * http.ResponseWriter, data interface{}, code int) {
	d, _ := json.Marshal(data)
	Response(w, d, code)
}

func ResponseBadReq(w * http.ResponseWriter, err_type int) {
	if err_type == 1 {
		data := &map[string]string {"code": "EMPTY_REQUEST", "message": "请求体为空"}	
		ResponseJson(w, data, http.StatusBadRequest)
	} else {
		data := &map[string]string {"code": "MALFORMED_JSON", "message": "格式错误"}
		ResponseJson(w, data, http.StatusBadRequest)
	}	
}

func ResponseUnauthorized(w * http.ResponseWriter) {
	data := &map[string]string {"code": "INVALID_ACCESS_TOKEN", "message": "无效的令牌"}
	ResponseJson(w, data, http.StatusUnauthorized)
}

/* support functions */

func DecodeData(r * http.Request, bind interface{}) int {
	defer r.Body.Close()
	if r.ContentLength == 0 {
		return 1
	}
	err := json.NewDecoder(r.Body).Decode(bind)
	if err != nil {
		return 2
	}
	return 0
}

func Authorize(r * http.Request) int {
	q := r.URL.Query()
	var access_token string
	if v, ok := q["access_token"]; ok && len(v) > 0 {
		access_token = v[0]
	} else {
		h := r.Header
		access_token = h.Get("Access-Token")
	}
	l := strings.Split(access_token, "_")
	if len(l) != 2 {
		return 0
	} else {
		user_id, err1 := strconv.Atoi(l[0])
		check, err2 := strconv.Atoi(l[1])
		if err1 != nil || err2 != nil || check != user_id * 2 + 1 {
			return 0
		} else {
			return user_id
		}
	}
}

func DoLogin(data * RequestLogin) (int, string) {
	user_id := mycache.CheckUser(data.Username, data.Password)
	if user_id == 0 {
		return 0, ""
	}
	access_token := fmt.Sprintf("%d_%d", user_id, user_id * 2 + 1)
	return user_id, access_token
}

// Cart Relative

func CartCreate(user_id int) string {
	cart_id := fmt.Sprintf("%d_%d", user_id, rand.Intn(2147483648))
	return cart_id
}

func CartExists(cart_id string) bool {
	l := strings.Split(cart_id, "_")
	if len(l) != 2 {
		return false
	}
	return true
}

func CartBelongs(cart_id string, user_id int) bool {
	l := strings.Split(cart_id, "_")
	if len(l) != 2 {
		return false
	}
	uid, err := strconv.Atoi(l[0])
	if err != nil || uid != user_id {
		return false
	}
	return true
}

func CartPatch(rc redis.Conn, cart_id string, data * RequestPatchCart) {
	k := fmt.Sprintf("dd.cart%s", cart_id)
	v := fmt.Sprintf("%d_%d", data.FoodId, data.Count)
	k2 := fmt.Sprintf("dd.cart%s.count", cart_id)
	rc.Do("RPUSH", k, v)
	rc.Do("INCRBY", k2, data.Count)
}

func CartCount(rc redis.Conn, cart_id string) int {
	k2 := fmt.Sprintf("dd.cart%s.count", cart_id)
	count, err := redis.Int(rc.Do("GET", k2))
	if err != nil {
		return 0
	}
	return count
}

func CartData(rc redis.Conn, cart_id string) * map[int]int {
	k := fmt.Sprintf("dd.cart%s", cart_id)
	l, _ := redis.Strings(rc.Do("LRANGE", k, 0, -1))
	data := make(map[int]int)
	for _, item := range l {
		temp := strings.Split(item, "_")
		food_id, _ := strconv.Atoi(temp[0])
		count, _ := strconv.Atoi(temp[1])
		o_count := data[food_id]
		n_count := o_count + count
		if n_count < 0 {
			n_count = 0
		}
		data[food_id] = n_count
	}
	return &data
}

// Order Relative

func FoodStockKey(food_id int) string {
	return fmt.Sprintf("dd.food%d.price", food_id)
}

func UserOrderId(rc redis.Conn, user_id int) string {
	k := fmt.Sprintf("dd.order%d", user_id)
	order_id, err := redis.String(rc.Do("GET", k))
	if err != nil {
		return ""
	}
	return order_id
}

func SetUserOrderId(rc redis.Conn, user_id int, order_id string) {
	k := fmt.Sprintf("dd.order%d", user_id)
	rc.Do("SET", k, order_id)
}

func UserOrder(rc redis.Conn, user_id int) * ResponseOrder {
	order_id := UserOrderId(rc, user_id)
	if order_id == "" {
		return nil
	}
	order := ResponseOrder{Id: order_id, Total: 0}
	cart := CartData(rc, order_id)
	for food_id, count := range *cart {
		order.Total = order.Total + mycache.FoodPrice(food_id) * count
		item := OrderItem{food_id, count}
		order.Items = append(order.Items, item)
	}
	return &order
}  

func OrderCart(rc redis.Conn, cart_id string) bool {
	cart := CartData(rc, cart_id)
	suc := true
	for food_id, count := range * cart {
		c, err := redis.Int(rc.Do("DECRBY", FoodStockKey(food_id), count))
		if err != nil {
			panic(err)
		}
		if c < 0 {
			suc = false
		}
	}
	if !suc {
		for food_id, count := range * cart {
			redis.Int(rc.Do("INCRBY", FoodStockKey(food_id), count))
		}
	}	
	return suc
}
 

