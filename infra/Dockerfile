FROM --platform=linux/arm64 python:3.11-slim-bookworm as base

# ==============================================================================
FROM base as builder
SHELL [ "/bin/bash", "-euxvc"]

RUN apt-get update; \
    apt-get install  -y --no-install-recommends curl openssh-client gcc git libpq-dev; \
    curl -sSL https://install.python-poetry.org | python3.11 -;

ENV PATH="${PATH}:/root/.local/bin:"

COPY ../poetry.lock ../pyproject.toml ./

RUN poetry config experimental.system-git-client true; \
    poetry config virtualenvs.create false; \
    poetry install --only main --no-interaction --no-ansi --no-root;

# ==============================================================================
FROM base as runtime
SHELL [ "/bin/bash", "-euxvc"]

ARG GIT_HASH
ENV TZ=Asia/Seoul \
    LANG=C.UTF-8 \
    LC_ALL=C.UTF-8 \
    PYTHONIOENCODING=UTF-8 \
    DEPLOYMENT_GIT_HASH=$GIT_HASH

RUN ln -snf /usr/share/zoneinfo/$TZ /etc/localtime && echo $TZ > /etc/timezone; \
    apt-get update; \
    apt-get install -y --no-install-recommends curl wget ca-certificates gnupg lsb-release;

COPY --from=builder /usr/local/bin/ /usr/local/bin/
COPY --from=builder /usr/local/lib/python3.11/lib-dynload /usr/local/lib/python3.11/lib-dynload/
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages/

RUN curl -sL https://sentry.io/get-cli/ | bash; \
    apt-get autoremove -y; \
    apt-get autoclean -y; \
    apt-get clean -y; \
    rm -rf /var/cache/apt/archives /var/lib/apt/lists/*;

# Make docker to always copy app directory so that source code can be refreshed.
ARG IMAGE_BUILD_DATETIME=unknown
ENV DEPLOYMENT_IMAGE_BUILD_DATETIME=$IMAGE_BUILD_DATETIME

# Copy main app
COPY ../alembic.ini ./alembic.ini
COPY ../pyproject.toml ./pyproject.toml
COPY ../app/ /app
RUN mkdir -p user_content
