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

# For local environments
local-run:
	@poetry run python -m app

local-celery:
	@poetry run python -m app.celery_task

local-flower:
	@poetry run python -m app.celery_task flower

local-celery-healthcheck:
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
