"""Celery задачи для асинхронного сбора данных из внешних источников."""

import os
import json
import asyncio
from celery import Celery
from typing import List, Dict

# Инициализация Celery
celery_app = Celery(
    'omnisearch',
    broker=os.getenv('REDIS_URL', 'redis://redis:6379/0'),
    backend=os.getenv('REDIS_URL', 'redis://redis:6379/0')
)

celery_app.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    task_track_started=True,
    task_time_limit=300,
    worker_prefetch_multiplier=1,
)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def fetch_from_wildberries(self, query: str, limit: int) -> List[Dict]:
    """
    Celery задача для поиска на Wildberries.
    
    Args:
        query: Поисковый запрос
        limit: Максимальное количество результатов
        
    Returns:
        Список найденных товаров
    """
    try:
        import httpx
        from fake_useragent import UserAgent
        
        url = "https://search.wb.ru/exactmatch/ru/common/v4/search"
        params = {
            "query": query,
            "resultset": "catalog",
            "limit": limit
        }
        headers = {"User-Agent": UserAgent().random}
        
        with httpx.Client(timeout=10.0) as client:
            resp = client.get(url, params=params, headers=headers)
            resp.raise_for_status()
            data = resp.json()
        
        products = []
        for item in data.get("data", {}).get("products", [])[:limit]:
            products.append({
                "name": item.get("name"),
                "price": item.get("salePriceU", 0) / 100,
                "currency": "RUB",
                "shop": "Wildberries",
                "url": f"https://www.wildberries.ru/catalog/{item.get('id')}/detail.aspx",
                "availability": "В наличии" if item.get("saleConditions", {}).get("saleAvailable") else "Под заказ",
                "source": "wildberries",
                "image_url": item.get("images", [None])[0] if item.get("images") else None,
                "rating": item.get("reviewRating", 0)
            })
        
        # Сохраняем результат в Redis для последующего получения
        redis_key = f"ext:{query}:wb"
        from app.utils import get_redis_client
        redis_client = get_redis_client()
        redis_client.setex(redis_key, 300, json.dumps(products))
        
        return products
    
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=10)
def fetch_from_ozon(self, query: str, limit: int) -> List[Dict]:
    """
    Celery задача для поиска на Ozon.
    Требует доработки (парсинг HTML или использование API).
    """
    # Заглушка - требует реализации парсинга
    return []


@celery_app.task
def aggregate_search_results(internal_json: str, external_keys: list) -> Dict:
    """
    Задача для агрегации результатов поиска.
    
    Args:
        internal_json: JSON с результатами внутреннего поиска
        external_keys: Список ключей Redis с результатами внешнего поиска
        
    Returns:
        Агрегированные результаты
    """
    import json
    from app.aggregator import aggregator
    
    internal_results = json.loads(internal_json)
    external_results = []
    
    from app.utils import get_redis_client
    redis_client = get_redis_client()
    
    for key in external_keys:
        data = redis_client.get(key)
        if data:
            external_results.extend(json.loads(data))
    
    aggregated = aggregator.aggregate(
        internal_results=internal_results,
        external_results=external_results,
        limit=50
    )
    
    return {
        "total_found": len(aggregated),
        "results": aggregated
    }
