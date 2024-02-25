
Ensure you have a kubernetes cluster set up in which it is safe to play around.
We recommend [kind](https://kind.sigs.k8s.io/) or
[minikube](https://minikube.sigs.k8s.io/)

<details><summary><b>Create a Cluster with Kind</b></summary>

```sh
kind create cluster
```

</details>

In one terminal, run the example program
```
go run echo.go
```

You should see something like
```
listening on port 8080
```
and if you `curl -d 'x=1' http://localhost:8080` you'll see the echoed
body `x=1`.


Now let's try to make our echo server available in the cluster.
In a separate terminal
```
kgrok echo localhost:8080
```

If we now check k8s, we should see a new service has been created, named
`echo`.

```
kubectl get svc echo
```
we see
```
NAME   TYPE        CLUSTER-IP   EXTERNAL-IP   PORT(S)    AGE
echo   ClusterIP   10.96.0.1    <none>        8080/TCP   54s
```

We can forward a port to the service to test that the service is really
connected
```
kubectl port-forward svc/echo 8081:8080
```
And in yet another terminal we can curl the forwarded port
```
curl -d 'x=1' http://localhost:8081
```
we'll get the same result as before and see the request logged by the echo
server.


