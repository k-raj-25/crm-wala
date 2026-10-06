.PHONY: help install db migrate seed api web admin test typecheck build up down
help: ## list targets
	@grep -E '^[a-z-]+:.*##' $(MAKEFILE_LIST) | awk -F':.*## ' '{printf "  %-12s %s\n", $$1, $$2}'
install: ## install JS + Python deps
	npm install && cd backend && python -m venv .venv && . .venv/bin/activate && pip install -r requirements.txt
migrate: ## apply DB migrations and platform defaults (plans, flags, email templates)
	cd backend && . .venv/bin/activate && FLASK_APP=wsgi.py flask db upgrade && FLASK_APP=wsgi.py flask seed-platform
seed: ## demo workspace + synthetic customers for the admin dashboards (dev only)
	cd backend && . .venv/bin/activate && FLASK_APP=wsgi.py flask seed-demo --reset && FLASK_APP=wsgi.py flask seed-sample
api: ## dev API on :5000
	scripts/api.sh restart
web: ## customer app on :3000
	npm run dev:web
admin: ## Super Admin app on :3001
	npm run dev:admin
test: ## backend tests (needs Postgres + Redis, see README)
	cd backend && . .venv/bin/activate && python -m pytest -q
typecheck: ## TypeScript across all packages
	npm run typecheck
build: ## production builds of both apps
	npm run build
up: ## full stack in Docker
	docker compose up --build
down:
	docker compose down
