.PHONY: setup run test lint infra-up infra-down

# ── Setup ───────────────────────────────────────────────────────────────────────
setup:
	python -m venv .venv
	.venv/Scripts/activate && pip install -r requirements.txt
	cp -n .env.example .env || true
	@echo ""
	@echo "Done. Next:"
	@echo "  1. Edit .env — set SECRET_KEY (run: python -c \"import secrets; print(secrets.token_hex(32))\")"
	@echo "  2. Start infra: make infra-up"
	@echo "  3. Run API:     make run"

# ── Infrastructure ──────────────────────────────────────────────────────────────
infra-up:
	cd .. && docker compose up -d
	@echo "Waiting for DB..."
	@timeout /t 5 /nobreak >nul 2>&1 || sleep 5
	@echo "DB + Redis ready."

infra-down:
	cd .. && docker compose down

# ── Run ─────────────────────────────────────────────────────────────────────────
run:
	.venv/Scripts/python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# ── Test ────────────────────────────────────────────────────────────────────────
test:
	.venv/Scripts/python -m pytest tests/ -v --cov=app --cov-report=term-missing

# ── Lint ────────────────────────────────────────────────────────────────────────
lint:
	.venv/Scripts/python -m ruff check app/ tests/
