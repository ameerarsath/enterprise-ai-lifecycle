.PHONY: setup up down test lint

setup:
	python -m venv venv
	./venv/Scripts/pip install -e .

up:
	docker-compose up -d

down:
	docker-compose down

run:
	./venv/Scripts/uvicorn api.main:app --reload --port 8000

test:
	./venv/Scripts/pytest tests/

lint:
	./venv/Scripts/black .
	./venv/Scripts/isort .
	./venv/Scripts/mypy .
