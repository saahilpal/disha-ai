# ==============================================================================
# DISHA AI — PRODUCTION MAKEFILE
# Standard one-command engineering workflow targets for developers and CI/CD.
# ==============================================================================

SHELL := /usr/bin/env bash
.DEFAULT_GOAL := help

# Python & Node executables (prefers local .venv if present)
VENV_BIN := $(shell if [ -d ".venv/bin" ]; then echo ".venv/bin"; else echo ""; fi)
PYTHON := $(if $(VENV_BIN),$(VENV_BIN)/python,python3)
PYTEST := $(if $(VENV_BIN),$(VENV_BIN)/pytest,pytest)
RUFF := $(if $(VENV_BIN),$(VENV_BIN)/ruff,ruff)
MYPY := $(if $(VENV_BIN),$(VENV_BIN)/mypy,mypy)
NODE := node
GITLEAKS := $(shell which gitleaks 2>/dev/null || echo "/opt/homebrew/bin/gitleaks")

# ANSI Color codes for clean terminal output
GREEN  := $(shell printf '\033[32m')
RED    := $(shell printf '\033[31m')
YELLOW := $(shell printf '\033[33m')
BLUE   := $(shell printf '\033[34m')
BOLD   := $(shell printf '\033[1m')
RESET  := $(shell printf '\033[0m')

.PHONY: help doctor dev test audit qa tunnel lint typecheck format clean status

help: ## Show this help message
	@echo "$(BOLD)DISHA AI — COMMAND REFERENCE$(RESET)"
	@echo ""
	@echo "Usage: make $(BLUE)<target>$(RESET)"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BLUE)%-15s$(RESET) %s\n", $$1, $$2}'
	@echo ""

doctor: ## Verify prerequisites: python, node, docker, cloudflared, gitleaks, uv
	@echo "$(BOLD)======================================================================$(RESET)"
	@echo "$(BOLD)DISHA AI — SYSTEM HEALTH & DEPENDENCY DOCTOR$(RESET)"
	@echo "$(BOLD)======================================================================$(RESET)"
	@FAIL=0; \
	check_tool() { \
		name="$$1"; cmd="$$2"; ver_cmd="$$3"; \
		if command -v "$$cmd" >/dev/null 2>&1; then \
			ver=$$($$ver_cmd 2>/dev/null | head -n 1); \
			path=$$(which "$$cmd"); \
			printf "  $(GREEN)[✓]$(RESET) %-14s %s ($(YELLOW)%s$(RESET))\n" "$$name" "$$ver" "$$path"; \
		else \
			printf "  $(RED)[✗]$(RESET) %-14s $(RED)NOT FOUND$(RESET)\n" "$$name"; \
			FAIL=1; \
		fi \
	}; \
	check_tool "Python" "$$($(PYTHON) -c 'import sys; print(sys.executable)' 2>/dev/null || echo python3)" "$(PYTHON) --version"; \
	check_tool "Node.js" "node" "node --version"; \
	check_tool "Docker" "docker" "docker --version"; \
	if command -v docker >/dev/null 2>&1; then \
		if docker info >/dev/null 2>&1; then \
			printf "  $(GREEN)[✓]$(RESET) %-14s Engine daemon is running\n" "Docker Daemon"; \
		else \
			printf "  $(RED)[✗]$(RESET) %-14s $(RED)Daemon is not running$(RESET)\n" "Docker Daemon"; \
			FAIL=1; \
		fi \
	fi; \
	check_tool "Cloudflared" "cloudflared" "cloudflared --version"; \
	check_tool "Gitleaks" "$(GITLEAKS)" "$(GITLEAKS) version"; \
	check_tool "UV" "uv" "uv --version"; \
	echo ""; \
	if [ -f ".env" ]; then \
		printf "  $(GREEN)[✓]$(RESET) %-14s Configuration file present (.env)\n" ".env File"; \
	else \
		printf "  $(YELLOW)[!]$(RESET) %-14s $(YELLOW)Missing (Run: cp .env.example .env)$(RESET)\n" ".env File"; \
	fi; \
	if [ -d ".venv" ]; then \
		printf "  $(GREEN)[✓]$(RESET) %-14s Virtual environment activated (.venv)\n" "Virtualenv"; \
	else \
		printf "  $(YELLOW)[!]$(RESET) %-14s $(YELLOW)Missing (Run: uv venv && uv pip install -r disha_core/requirements.txt)$(RESET)\n" "Virtualenv"; \
	fi; \
	echo "$(BOLD)======================================================================$(RESET)"; \
	if [ $$FAIL -eq 0 ]; then \
		echo "$(GREEN)$(BOLD)✓ All prerequisite tools and runtimes are present and operational.$(RESET)"; \
		exit 0; \
	else \
		echo "$(RED)$(BOLD)✗ Some required tools are missing. Please install them before proceeding.$(RESET)"; \
		exit 1; \
	fi

dev: ## Launch local backend and proxy with live healthcheck
	@echo "$(BOLD)[+] Launching Disha AI local stack (PostgreSQL + Backend + NGINX Proxy)...$(RESET)"
	@if [ ! -f ".env" ]; then \
		echo "$(YELLOW)[!] No .env found. Copying .env.example -> .env$(RESET)"; \
		cp .env.example .env; \
	fi
	@docker compose up -d postgres backend proxy
	@echo "[+] Waiting for proxy and backend health check at http://127.0.0.1:8080/health..."
	@ATTEMPTS=0; \
	until curl -s -f http://127.0.0.1:8080/health >/dev/null 2>&1; do \
		ATTEMPTS=$$((ATTEMPTS + 1)); \
		if [ $$ATTEMPTS -gt 30 ]; then \
			echo "$(RED)[-] Timeout waiting for service health.$(RESET)"; \
			docker compose logs --tail=20 backend; \
			exit 1; \
		fi; \
		sleep 1; \
	done
	@echo "$(GREEN)$(BOLD)======================================================================$(RESET)"
	@echo "$(GREEN)$(BOLD)🚀 DISHA AI LOCAL STACK IS ONLINE$(RESET)"
	@echo "   Web Client:       http://127.0.0.1:8080"
	@echo "   Proxy Health:     http://127.0.0.1:8080/health"
	@echo "   Direct Backend:   http://127.0.0.1:8000"
	@echo "   WebSocket Route:  ws://127.0.0.1:8080/ws/conversation"
	@echo "$(GREEN)$(BOLD)======================================================================$(RESET)"

test-ux: ## Run Playwright browser automated UX verification suite
	@echo "$(BOLD)[+] Executing Playwright Browser Automated UX Suite (8 core workflows)...$(RESET)"
	@$(NODE) tests/test_playwright_ux.js

test: ## Run full pytest and node diagnostic suites
	@echo "$(BOLD)[+] Executing Node.js Frontend Diagnostics Suite (32 checks)...$(RESET)"
	@$(NODE) tests/test_frontend_diagnostics.js
	@echo ""
	@echo "$(BOLD)[+] Executing Pytest Core Invariants and Safety Suite (115+ tests)...$(RESET)"
	@$(PYTEST) -v disha_core/tests tests/test_clinical_safety_and_ledger.py tests/test_laya_integration.py tests/test_laya_contract.py tests/test_audit_security_and_edge_cases.py tests/test_vercel_packaging.py
	@echo ""
	@echo "$(GREEN)$(BOLD)✓ All automated test suites PASSED successfully.$(RESET)"

audit: ## Run deterministic multi-dimensional judge evaluation
	@echo "$(BOLD)[+] Running automated audit judge (/audit/judge.py)...$(RESET)"
	@$(PYTHON) -m audit.judge

qa: ## Run Playwright screenshot capture and mechanical adversarial checks
	@echo "$(BOLD)[+] Running Playwright visual regression crawler across viewports and themes...$(RESET)"
	@$(NODE) qa/capture_redesign.js
	@echo ""
	@echo "$(BOLD)[+] Running mechanical clinical safety and edge case verifications...$(RESET)"
	@$(PYTEST) -v tests/test_clinical_safety_and_ledger.py tests/test_audit_security_and_edge_cases.py
	@echo "$(GREEN)$(BOLD)✓ QA visual capture and mechanical checks complete.$(RESET)"

tunnel: ## Start Cloudflare tunnel watchdog
	@echo "$(BOLD)[+] Starting Cloudflare Tunnel Watchdog...$(RESET)"
	@bash scripts/tunnel-watchdog.sh

lint: ## Lint codebase with ruff
	@echo "$(BOLD)[+] Running ruff linter...$(RESET)"
	@$(RUFF) check disha_core audit tests

typecheck: ## Typecheck codebase with mypy
	@echo "$(BOLD)[+] Running mypy type checker...$(RESET)"
	@$(MYPY) disha_core audit

format: ## Format codebase with ruff
	@echo "$(BOLD)[+] Formatting codebase with ruff...$(RESET)"
	@$(RUFF) format disha_core audit tests

clean: ## Clean cache files, pycache, test artifacts
	@echo "$(BOLD)[+] Cleaning caches and temporary artifacts...$(RESET)"
	@find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete 2>/dev/null || true
	@find . -type f -name "*.pyo" -delete 2>/dev/null || true
	@rm -rf .coverage htmlcov .ruff_cache
	@echo "$(GREEN)✓ Clean complete.$(RESET)"

status: ## Show Docker container and service status
	@echo "$(BOLD)[+] Docker Services Status:$(RESET)"
	@docker compose ps
	@echo ""
	@echo "$(BOLD)[+] Edge Endpoint Health:$(RESET)"
	@curl -s -w "\nHTTP Status: %{http_code}\n" http://127.0.0.1:8080/health || echo "$(RED)Unreachable$(RESET)"
