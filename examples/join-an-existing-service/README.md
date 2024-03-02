
Create a service

```
k apply -f - <<EOF
apiVersion: v1
kind: Service
metadata:
  labels:
    app: echo
  name: echo
spec:
  ports:
  - name: http
    port: 8080
  selector:
    app: echo
EOF
```

start our own local echo service
```
(cd ../simple-echo-server ; go run echo.go)
```

now run
```
kgrok echo 8080
```
