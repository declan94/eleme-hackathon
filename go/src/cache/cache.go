package cache
// package main

import (
	"os"
	"fmt"
	"database/sql"
	"encoding/json"
	_ "github.com/go-sql-driver/mysql"
)

//----------------------------------
// Entity Abstracts
//----------------------------------
type User struct {
	Id          int
	Username    string
	Password    string
}

type Food struct {
	Id    int `json:"id"`
	Price int `json:"price"`
	Stock int `json:"stock"`
}

//----------------------------------
// Global Variables
//----------------------------------
var (
	user_cache      = make(map[string]int)   	// map[{user.Username}.{user.Password}]user.Id
	food_cache      = make(map[int]int) 		// map[{food.Id}]price
	food_json		= make([]byte, 0)	
	uids			= make([]int, 0)
)

//----------------------------------
// Data Initialization
//----------------------------------
// Load all data.
func LoadData() []Food {
	dbHost := os.Getenv("DB_HOST")
	dbPort := os.Getenv("DB_PORT")
	dbName := os.Getenv("DB_NAME")
	dbUser := os.Getenv("DB_USER")
	dbPass := os.Getenv("DB_PASS")

	if dbHost == "" {
		dbHost = "localhost"
	}
	if dbPort == "" {
		dbPort = "3306"
	}
	if dbName == "" {
		dbName = "eleme"
	}
	if dbUser == "" {
		dbUser = "root"
	}
	if dbPass == "" {
		dbPass = "toor"
	}

	fmt.Printf("Connect to mysql..")
	dbDsn := fmt.Sprintf("%s:%s@tcp(%s:%s)/%s", dbUser, dbPass, dbHost, dbPort, dbName)
	db, err := sql.Open("mysql", dbDsn)
	if err != nil {
		panic(err)
	}
	defer db.Close()
	fmt.Printf("OK\n")
	fmt.Printf("Ping to mysql..")
	err = db.Ping()
	if err != nil {
		panic(err)
	}
	fmt.Printf("OK\n")
	fmt.Printf("Load users from mysql..")
	LoadUsers(db)
	fmt.Printf("OK\n")
	fmt.Printf("Load foods from mysql..")
	foods := LoadFoods(db)
	fmt.Printf("OK\n")
	return foods
}

// Load users from mysql
func LoadUsers(db *sql.DB) {
	var user User
	rows, err := db.Query("SELECT `id`, `name`, `password` from user")
	if err != nil {
		panic(err)
	}
	defer rows.Close()
	for rows.Next() {
		err = rows.Scan(&user.Id, &user.Username, &user.Password)
		if err != nil {
			panic(err)
		}
		k := fmt.Sprintf("%s.%s", user.Username, user.Password)
		user_cache[k] = user.Id
		uids = append(uids, user.Id)
	}
}

// Load foods from mysql
func LoadFoods(db *sql.DB) []Food {
	var food Food
	foods := make([]Food, 0)
	rows, err := db.Query("SELECT `id`, `stock`, `price` from food")
	if err != nil {
		panic(err)
	}
	defer rows.Close()
	for rows.Next() {
		err = rows.Scan(&food.Id, &food.Stock, &food.Price)
		if err != nil {
			panic(err)
		}
		food_cache[food.Id] = food.Price
		foods = append(foods, food)
	}
	food_json, _ = json.Marshal(foods)
	return foods
}

func CheckUser(username string, password string) int {
	k := fmt.Sprintf("%s.%s", username, password)
	if v, ok := user_cache[k]; ok {
		return v
	} else {
		return 0
	}
}

func UserIds() []int {
	return uids
}

func FoodJson() []byte {
	return food_json
}

func FoodPrice(food_id int) int {
	if v, ok := food_cache[food_id]; ok {
		return v
	} else {
		return 0
	}
}

// func main() {
// 	LoadData()	
// 	fmt.Printf("Food 1 Price: %d \n", FoodPrice(1))
// 	os.Stdout.Write(FoodJson())
// }
