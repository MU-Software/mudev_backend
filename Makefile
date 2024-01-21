include .env
export $(shell sed 's/=.*//' .env)

MIGRATION_MESSAGE ?= `date +"%Y%m%d_%H%M%S"`
UPGRADE_VERSION ?= head
DOWNGRADE_VERSION ?= -1

MKFILE_PATH := $(abspath $(lastword $(MAKEFILE_LIST)))
PROJECT_DIR := $(dir $(MKFILE_PATH))

GIT_MAIN_BRANCH_HEAD_HASH := $(shell git rev-parse origin/main)
ifeq (prod-update,$(firstword $(MAKECMDGOALS)))
  UPDATE_TARGET_GIT_HASH := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  $(eval $(UPDATE_TARGET_GIT_HASH):;@:)
endif
UPDATE_TARGET_GIT_HASH := $(if $(UPDATE_TARGET_GIT_HASH),$(UPDATE_TARGET_GIT_HASH),$(GIT_MAIN_BRANCH_HEAD_HASH))

ifeq (makemigration,$(firstword $(MAKECMDGOALS)))
  MIGRATION_MESSAGE := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  $(eval $(MIGRATION_MESSAGE):;@:)
endif
MIGRATION_MESSAGE := $(if $(MIGRATION_MESSAGE),$(MIGRATION_MESSAGE),migration)

ifeq (docker-build,$(firstword $(MAKECMDGOALS)))
  IMAGE_NAME := $(wordlist 2,$(words $(MAKECMDGOALS)),$(MAKECMDGOALS))
  $(eval $(IMAGE_NAME):;@:)
endif
IMAGE_NAME := $(if $(IMAGE_NAME),$(IMAGE_NAME),mudev-backend)

ifeq ($(DOCKER_DEBUG),true)
	DOCKER_MID_BUILD_OPTIONS = --progress=plain --no-cache
	DOCKER_END_BUILD_OPTIONS = 2>&1 | tee docker-build.log
else
	DOCKER_MID_BUILD_OPTIONS =
	DOCKER_END_BUILD_OPTIONS =
endif


guard-%:
	@if [ "${${*}}" = "" ]; then \
		echo "Environment variable $* not set"; \
		exit 1; \
	fi

# DB migrations
db-makemigration:
	@poetry run alembic revision --autogenerate -m $(MIGRATION_MESSAGE)

db-upgrade:
	@poetry run alembic upgrade $(UPGRADE_VERSION)

db-downgrade:
	@poetry run alembic downgrade $(DOWNGRADE_VERSION)

# Docker compose setup
# This is for local development, use mudev-infra repo for production
docker-compose-up:
	docker-compose -f ./infra/docker-compose-dev.yaml up -d

docker-compose-down:
	docker-compose -f ./infra/docker-compose-dev.yaml down

docker-compose-rm: docker-compose-down
	docker-compose -f ./infra/docker-compose-dev.yaml rm

# Docker image build for production
# Usage: make docker-build <image-name:=snowfall_image>
# if you want to build with debug mode, set DOCKER_DEBUG=true
# ex) make docker-build snowfall_image DOCKER_DEBUG=true
docker-build:
	docker build \
		-f ./infra/Dockerfile --target runtime -t $(IMAGE_NAME) \
		--build-arg GIT_HASH=$(shell git rev-parse HEAD) \
		--build-arg INVALIDATE_CACHE_DATE=$(shell date +%Y-%m-%d_%H:%M:%S) \
		$(DOCKER_MID_BUILD_OPTIONS) $(PROJECT_DIR) $(DOCKER_END_BUILD_OPTIONS)

# For local environments
local-api: docker-compose-up
	@poetry run python -m app

local-celery: docker-compose-up
	@poetry run python -m app.celery_task worker

local-beat: docker-compose-up
	@poetry run python -m app.celery_task beat

local-flower: docker-compose-up
	@poetry run python -m app.celery_task flower

local-celery-healthcheck: docker-compose-up
	@poetry run python -m app.celery_task healthcheck

prod-run:
	@poetry run gunicorn --bind $(HOST):$(PORT) 'app:create_app()' --worker-class uvicorn.workers.UvicornWorker

# For production environments
prod-upgrade: guard-PROD_SERVER_SSH_NAME  # Usage: make prod-upgrade <?git-hash>
	@fab --hosts=$(PROD_SERVER_SSH_NAME) update $(UPDATE_TARGET_GIT_HASH)

prod-cutover: guard-PROD_SERVER_SSH_NAME
	@fab --hosts=$(PROD_SERVER_SSH_NAME) cutover

prod-migrate: guard-PROD_SERVER_SSH_NAME
	@fab --hosts=$(PROD_SERVER_SSH_NAME) migrate

prod-deploy: guard-PROD_SERVER_SSH_NAME
	@fab --hosts=$(PROD_SERVER_SSH_NAME) update migrate cutover

# Devtools
hooks-install:
	poetry run pre-commit install

hooks-upgrade:
	poetry run pre-commit autoupdate

hooks-lint:
	poetry run pre-commit run --all-files

lint: hooks-lint  # alias

hooks-mypy:
	poetry run pre-commit run mypy --all-files

mypy: hooks-mypy  # alias

# CLI tools
cli-%:
	@if [[ -z "$*" || "$*" == '.o' ]]; then echo "Usage: make cli-<command>"; exit 1; fi
	poetry run python -m app.cli $*
