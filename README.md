# Kgrok

## Quick Start

```
kgrok my-svc localhost:8080
```

We assume you have a service already listening locally on port 8080
and you have your `kubectl` context configured for the cluster you want to
listen receive traffic from.


## Installation

Using [pipx] might be the most reliable.

```
pipx install kgrok
```

[pipx]: https://pipx.pypa.io/stable/

If you are however already in a Python 3.12 virtual environment, or inside
a container with pip, you can probably get away with it.

```
python3 -m pip install kgrok
```
