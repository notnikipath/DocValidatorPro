.PHONY: up down lint test compose samples demo

up:
	docker compose up --build -d

down:
	docker compose down

lint:
	python -m ruff check .

test:
	python -m pytest -q

compose:
	docker compose config

samples:
	python scripts/generate_sample_data.py

demo:
	python scripts/demo_pipeline.py
