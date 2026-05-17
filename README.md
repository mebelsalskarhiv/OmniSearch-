# OmniSearch

Универсальная поисковая система для агрегации товаров из внутренних и внешних источников.

## Архитектура

Сервис разделён на независимые компоненты, взаимодействующие через REST API и очереди задач:

- **API Gateway** — FastAPI-приложение, принимает запросы, валидирует, запускает поиск
- **Search Orchestrator** — синхронно ищет во внутренних хранилищах, асинхронно запускает сбор с внешних источников
- **Internal DB Service** — слой доступа к PostgreSQL (реляционные данные) и Elasticsearch (полнотекстовый поиск)
- **External Fetcher Workers** — Celery-воркеры для парсинга сайтов и обращения к API маркетплейсов
- **Result Aggregator** — объединяет, очищает дубликаты и ранжирует результаты
- **Cache Layer** — Redis для кэширования популярных запросов и состояния задач

## Структура проекта

```
OmniSearch/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI приложение
│   ├── models.py            # Pydantic модели
│   ├── normalizer.py        # Модуль нормализации запросов
│   ├── search_internal.py   # Поиск по внутренней БД
│   ├── search_external.py   # Поиск по внешним источникам
│   ├── aggregator.py        # Агрегация и ранжирование
│   ├── tasks.py             # Celery задачи
│   └── utils.py             # Утилиты (rate limiting, etc.)
├── tests/
├── docker-compose.yml
├── Dockerfile
├── requirements.txt
└── README.md
```

## Быстрый старт

```bash
# Запуск через Docker Compose
docker-compose up -d

# API доступен на http://localhost:8000
# Документация Swagger: http://localhost:8000/docs
```

## Пример запроса

```bash
curl -X POST "http://localhost:8000/api/v1/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "iPhone 15 128GB",
    "limit": 10,
    "filters": {
      "category": "electronics",
      "price_min": 80000,
      "price_max": 120000
    }
  }'
```

## Технологии

- **Backend**: FastAPI, Python 3.11+
- **Базы данных**: PostgreSQL 15, Elasticsearch 8.6
- **Кэш и брокер**: Redis 7
- **Очереди задач**: Celery
- **Контейнеризация**: Docker, Kubernetes (для продакшена)

## Лицензия

MIT
