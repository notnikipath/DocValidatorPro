# Deployment

## Requirements

- Docker + Docker Compose
- Python 3.11 (for local lint/tests/scripts)

## Start

```bash
cd d:\Шарага\Кинжа5\Task_5_DocValidatorPro
docker compose up --build -d
```

## Stop

```bash
docker compose down
```

## Verify environment

```bash
docker compose config
python -m ruff check .
python -m pytest -q
```

## Ports

- `8500` API Gateway
- `8501-8508` Backend microservices
- `5177` Frontend
- `55435` PostgreSQL
- `18123` ClickHouse HTTP
- `9000/9001` MinIO API/Console
- `6383` Redis
- `5672/15672` RabbitMQ
- `19092` Redpanda Kafka API
