# https://hub.docker.com/_/python
FROM python:3.12-slim


WORKDIR /app
COPY requirements.txt pyproject.toml ./

RUN pip install uv && uv venv .venv
RUN . .venv/bin/activate \
    && uv pip sync requirements.txt

COPY src src
RUN . .venv/bin/activate \
    && uv pip install -e .

ENV PYTHONUNBUFFERED True
ENV APP_HOME /app
WORKDIR $APP_HOME


ENTRYPOINT [".venv/bin/kgrok-remote"]
