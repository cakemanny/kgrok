# syntax=docker/dockerfile:1
# https://hub.docker.com/_/python

# builder:
    FROM python:3.12-slim AS builder

    WORKDIR /app
    RUN pip install uv && uv venv .venv

    ENV VIRTUAL_ENV=/app/.venv
    ENV PATH=$VIRTUAL_ENV/bin:$PATH

    COPY requirements.txt pyproject.toml ./

    RUN uv pip sync requirements.txt

    COPY src src
    RUN uv pip install .

# runtime:
    FROM python:3.12-slim
    COPY --from=builder /app/.venv /app/.venv

    ENV PYTHONUNBUFFERED=True \
        APP_HOME=/app \
        VIRTUAL_ENV=/app/.venv
    ENV PATH=$VIRTUAL_ENV/bin:$PATH
    WORKDIR $APP_HOME

    ENTRYPOINT ["kgrok-remote"]
