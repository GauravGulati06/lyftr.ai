up:
	docker compose up -d --build

down:
	docker compose down -v

logs:
	docker compose logs -f api

test:
	docker compose run --rm api pytest -q
