package main

import (
	"io"
	"log"
	"net/http"
	"os"
)


func main() {
	port := os.Getenv("PORT")
	if port == "" {
		port = "8080"
	}
	log.Printf("listening on port %s\n", port)
	err := http.ListenAndServe(":" + port, http.HandlerFunc(func (w http.ResponseWriter, r *http.Request) {
		log.Printf("%s %s\n", r.Method, r.URL)
		if r.Method == "GET" {
			w.WriteHeader(200)
		} else if r.Method == "POST" {
			w.Header().Add("Content-Type", r.Header.Get("Content-Type"))
			io.Copy(w, r.Body)
		} else {
			w.WriteHeader(http.StatusMethodNotAllowed);
		}
	}))
	log.Println(err)
}
