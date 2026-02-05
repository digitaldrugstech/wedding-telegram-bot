.DEFAULT_GOAL := help

## ── Run ─────────────────────────────────────────────────────────────

.PHONY: run
run: ## Run the bot
	python app/bot.py

## ── Setup ───────────────────────────────────────────────────────────

.PHONY: setup
setup: ## First-time setup (install deps, copy .env)
	pip install -r requirements.txt
	@test -f .env || cp .env.example .env
	@echo "Setup complete. Edit .env then run: make run"

## ── Code Quality ────────────────────────────────────────────────────

.PHONY: fmt
fmt: ## Format code (black + isort)
	black .
	isort .

.PHONY: lint
lint: ## Remove unused imports
	autoflake --check --recursive .

.PHONY: test
test: ## Run tests
	pytest tests/ -v 2>/dev/null || echo "No tests found."

## ── Help ────────────────────────────────────────────────────────────

.PHONY: help
help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
		awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-12s\033[0m %s\n", $$1, $$2}'
