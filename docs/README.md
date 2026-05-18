# OmniSearch Documentation

Полная документация по архитектуре, API и развертыванию поисковой системы OmniSearch.

## Содержание

1. [Архитектура](#архитектура)
2. [Алгоритм поиска](#алгоритм-поиска)
3. [API Reference](#api-reference)
4. [Установка и запуск](#установка-и-запуск)
5. [Конфигурация](#конфигурация)
6. [Разработка](#разработка)

---

## Архитектура

OmniSearch построен по микросервисной архитектуре с разделением ответственности:

```
┌─────────────┐     ┌──────────────────┐     ┌───────────────────┐
│   Client    │────▶│   API Gateway    │────▶│ Search Orchestrator│
│  (Browser/  │     │    (FastAPI)     │     │                   │
│   Mobile)   │     └──────────────────┘     └─────────┬─────────┘
└─────────────┘                                        │
                                                       ▼
                    ┌──────────────────────────────────────────────┐
                    │                                              │
          ┌─────────▼─────────┐                      ┌────────────▼───────────┐
          │  Internal DB      │                      │  External Fetcher      │
          │  - PostgreSQL     │                      │  (Celery Workers)      │
          │  - Elasticsearch  │                      │  - Wildberries         │
          └─────────┬─────────┘                      │  - Ozon                │
                    │                                │  - Yandex.Market       │
                    │                                └────────────┬───────────┘
                    │                                             │
                    └──────────────────┬──────────────────────────┘
                                       ▼
                              ┌─────────────────┐
                              │ Result Aggregator│
                              │ - Deduplication │
                              │ - Ranking       │
                              │ - Filtering     │
                              └────────┬────────┘
                                       ▼
                              ┌─────────────────┐
                              │  Cache Layer    │
                              │    (Redis)      │
                              └─────────────────┘
```

### Компоненты

| Компонент | Технология | Описание |
|-----------|------------|----------|
| API Gateway | FastAPI | Прием запросов, валидация, rate limiting |
| Search Orchestrator | Python asyncio | Координация поиска по внутренним и внешним источникам |
| Internal DB Service | PostgreSQL + Elasticsearch | Хранение и поиск по товарам |
| External Fetcher | Celery + httpx | Асинхронный парсинг внешних источников |
| Result Aggregator | Python | Объединение, дедупликация, ранжирование |
| Cache Layer | Redis | Кэширование запросов, состояние задач |

---

## Алгоритм поиска

### Пошаговый процесс

#### Шаг 1: Прием и валидация запроса
```
POST /api/v1/search
{
  "query": "iPhone 15 128GB",
  "limit": 10,
  "filters": {
    "category": "electronics",
    "price_min": 80000,
    "price_max": 120000
  }
}
```

- Проверка rate limiting (Redis ключ `rate_limit:{ip}`)
- Валидация через Pydantic модели
- Логирование запроса

#### Шаг 2: Нормализация запроса
Функция `normalize_query()`:
1. Очистка от спецсимволов
2. Приведение к нижнему регистру
3. Определение типа запроса:
   - **barcode**: 8-14 цифр, проверка контрольной суммы EAN/UPC
   - **article**: 5-30 символов (буквы+цифры), без пробелов
   - **name**: текстовый запрос, извлечение ключевых слов

Пример результата:
```python
{
  'original': 'iPhone 15 128GB',
  'normalized': 'iphone 15 128gb',
  'type': 'name',
  'keywords': ['iphone', '15', '128gb']
}
```

#### Шаг 3: Поиск во внутренней базе (синхронно)

**Для barcode:**
```sql
SELECT * FROM products WHERE barcode = '{value}' LIMIT 1;
```

**Для article:**
```sql
SELECT * FROM products WHERE article = '{value}' LIMIT 1;
```

**Для name:**
1. Поиск в Elasticsearch:
```json
{
  "query": {
    "multi_match": {
      "query": "iphone 15 128gb",
      "fields": ["name^3", "description", "brand"],
      "type": "best_fields",
      "fuzziness": "AUTO"
    }
  },
  "size": 10
}
```

2. Fallback на PostgreSQL (если ES недоступен):
```sql
SELECT * FROM products 
WHERE name ILIKE '%iphone%' OR name ILIKE '%15%'
ORDER BY similarity(name, 'iphone 15 128gb') DESC
LIMIT 10;
```

#### Шаг 4: Поиск во внешних источниках (асинхронно)

Запуск Celery задач параллельно:
```python
task_wb = fetch_from_wildberries.delay(query, limit)
task_ozon = fetch_from_ozon.delay(query, limit)
```

**Wildberries API:**
```
GET https://search.wb.ru/exactmatch/ru/common/v4/search?query={query}&limit={limit}
```

**Ozon (парсинг):**
- HTML parsing через BeautifulSoup
- Обход через пул прокси

Результаты сохраняются в Redis с TTL 300 сек:
```
SETEX ext:{query}:wb 300 {json_data}
```

#### Шаг 5: Агрегация результатов

1. **Объединение** всех источников
2. **Фильтрация** по параметрам (цена, категория, бренд)
3. **Дедупликация**:
   - Точное совпадение артикула
   - Fuzzy-сравнение названий (threshold 90%)
```python
from fuzzywuzzy import fuzz
name_sim = fuzz.token_sort_ratio(item1['name'], item2['name'])
if name_sim > 90: mark_as_duplicate()
```

4. **Ранжирование**:
   - По умолчанию: relevance (score из ES) → price
   - Опции: price_asc, price_desc, rating_desc

5. **Лимитирование** результатов

#### Шаг 6: Формирование ответа

```json
{
  "query": "iPhone 15",
  "total_found": 34,
  "results": [
    {
      "id": "uuid",
      "name": "Apple iPhone 15 128GB",
      "price": 89990,
      "currency": "RUB",
      "shop": "М.Видео",
      "url": "...",
      "availability": "В наличии",
      "relevance_score": 0.95
    }
  ],
  "external_sources_pending": true
}
```

---

## API Reference

### POST /api/v1/search

Поиск товаров.

**Request:**
```json
{
  "query": "string (1-200 chars)",
  "limit": "integer (1-100, default: 10)",
  "filters": {
    "category": "string (optional)",
    "price_min": "number (optional)",
    "price_max": "number (optional)",
    "brand": "string (optional)"
  },
  "sort": "string (optional): relevance|price_asc|price_desc|rating_desc"
}
```

**Response:**
```json
{
  "query": "string",
  "total_found": "integer",
  "results": "array[Product]",
  "external_sources_pending": "boolean"
}
```

**Error Codes:**
- `400` - Invalid request format
- `429` - Too many requests (rate limit)
- `500` - Internal server error

### GET /api/v1/search/status/{task_id}

Проверка статуса асинхронной задачи.

**Response:**
```json
{
  "status": "pending|processing|completed|failed",
  "progress": "integer (0-100)",
  "results": "array[Product] (if completed)"
}
```

---

## Установка и запуск

### Требования
- Docker 20+
- Docker Compose 2+
- 4GB RAM minimum
- 10GB disk space

### Быстрый старт

```bash
# Клонирование репозитория
git clone https://github.com/mebelsalskarhiv/OmniSearch-.git
cd OmniSearch-

# Запуск всех сервисов
docker-compose up -d

# Проверка логов
docker-compose logs -f api
docker-compose logs -f worker

# Доступ к API
open http://localhost:8000/docs
```

### Миграции БД

```bash
# Инициализация PostgreSQL
docker-compose exec postgres psql -U user -d searchdb -f /docker-entrypoint-initdb.d/init.sql

# Создание индекса Elasticsearch
curl -X PUT "http://localhost:9200/products_search" \
  -H "Content-Type: application/json" \
  -d @es_mapping.json
```

### Тестирование

```bash
# Запуск тестов
docker-compose exec api pytest

# Пример запроса
curl -X POST "http://localhost:8000/api/v1/search" \
  -H "Content-Type: application/json" \
  -d '{"query": "iPhone 15", "limit": 5}'
```

---

## Конфигурация

### Переменные окружения

| Variable | Default | Description |
|----------|---------|-------------|
| `DATABASE_URL` | `postgresql://user:pass@postgres:5432/searchdb` | PostgreSQL connection |
| `ES_HOST` | `http://elasticsearch:9200` | Elasticsearch host |
| `REDIS_URL` | `redis://redis:6379` | Redis connection |
| `CELERY_BROKER` | `redis://redis:6379/0` | Celery broker URL |
| `RATE_LIMIT_PER_MIN` | `60` | Requests per minute per IP |
| `PROXY_POOL` | `` | Comma-separated proxy list |

### Файл `.env`

```bash
DATABASE_URL=postgresql://user:pass@postgres:5432/searchdb
ES_HOST=http://elasticsearch:9200
REDIS_URL=redis://redis:6379
CELERY_BROKER=redis://redis:6379/0
RATE_LIMIT_PER_MIN=60
```

---

## Разработка

### Структура проекта

```
OmniSearch/
├── app/
│   ├── main.py              # FastAPI приложение
│   ├── models.py            # Pydantic модели
│   ├── normalizer.py        # Нормализация запросов
│   ├── search_internal.py   # Поиск по внутренней БД
│   ├── search_external.py   # Поиск по внешним источникам
│   ├── aggregator.py        # Агрегация результатов
│   ├── tasks.py             # Celery задачи
│   └── utils.py             # Утилиты (rate limiting)
├── docs/                    # Документация
├── docker-compose.yml       # Docker конфигурация
├── Dockerfile               # Образ приложения
├── db_init.sql              # Схема БД
├── es_mapping.json          # Mapping Elasticsearch
├── requirements.txt         # Python зависимости
└── README.md                # Основная документация
```

### Добавление нового источника

1. Создать задачу в `tasks.py`:
```python
@celery_app.task
def fetch_from_new_source(query: str, limit: int):
    # Реализация парсинга/API вызова
    pass
```

2. Добавить вызов в `search_external.py`:
```python
task_new = fetch_from_new_source.delay(q, limit)
```

3. Обновить агрегатор для обработки новых полей

### Тестирование

```bash
# Unit тесты
pytest tests/unit/

# Integration тесты
pytest tests/integration/

# Load тесты
locust -f tests/load/locustfile.py
```

---

## Roadmap

### v1.0 (Current)
- ✅ Basic search functionality
- ✅ Internal DB integration
- ✅ Wildberries API
- ⏳ Ozon parsing
- ⏳ Full test coverage

### v1.1
- [ ] Yandex.Market integration
- [ ] WebSocket for real-time updates
- [ ] Advanced filtering
- [ ] Pagination support

### v2.0
- [ ] ML-based similar products
- [ ] Telegram bot
- [ ] Price drop notifications
- [ ] User favorites

### v3.0
- [ ] Kubernetes deployment
- [ ] Multi-region support
- [ ] Advanced analytics
- [ ] GraphQL API

---

## Лицензия

MIT License - см. LICENSE файл.

## Контакты

GitHub: https://github.com/mebelsalskarhiv/OmniSearch-
