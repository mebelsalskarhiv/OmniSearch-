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
        import random
        
        # Пул прокси (раскомментировать и добавить свои прокси)
        PROXY_POOL = [
            # 'http://proxy1:port',
            # 'http://proxy2:port',
        ]
        
        def get_proxy():
            return random.choice(PROXY_POOL) if PROXY_POOL else None
        
        url = "https://search.wb.ru/exactmatch/ru/common/v4/search"
        params = {
            "query": query,
            "resultset": "catalog",
            "limit": limit
        }
        
        proxy = get_proxy()
        proxies = {"http://": proxy, "https://": proxy} if proxy else None
        
        headers = {
            "User-Agent": UserAgent().random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
        }
        
        with httpx.Client(timeout=10.0, proxies=proxies) as client:
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
                "rating": item.get("reviewRating", 0),
                "reviews_count": item.get("feedbacks", 0)
            })
        
        # Сохраняем результат в Redis для последующего получения
        redis_key = f"ext:{query}:wb"
        from app.utils import get_redis_client
        redis_client = get_redis_client()
        redis_client.setex(redis_key, 300, json.dumps(products))
        
        return products
    
    except Exception as exc:
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=3, default_retry_delay=15)
def fetch_from_ozon(self, query: str, limit: int) -> List[Dict]:
    """
    Celery задача для поиска на Ozon через парсинг HTML.
    Использует ротацию User-Agent и прокси для обхода блокировок.
    
    Args:
        query: Поисковый запрос
        limit: Максимальное количество результатов
        
    Returns:
        Список найденных товаров
    """
    try:
        import httpx
        from fake_useragent import UserAgent
        from bs4 import BeautifulSoup
        import random
        
        # Пул прокси
        PROXY_POOL = [
            # 'http://proxy1:port',
            # 'http://proxy2:port',
        ]
        
        def get_proxy():
            return random.choice(PROXY_POOL) if PROXY_POOL else None
        
        url = f"https://www.ozon.ru/search/?text={query}&from_global=true"
        
        proxy = get_proxy()
        proxies = {"http://": proxy, "https://": proxy} if proxy else None
        
        headers = {
            "User-Agent": UserAgent().random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Accept-Encoding": "gzip, deflate, br",
            "Connection": "keep-alive",
        }
        
        with httpx.Client(timeout=15.0, proxies=proxies, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            
            # Проверка на CAPTCHA или блокировку
            if "captcha" in resp.text.lower() or resp.status_code == 403:
                raise Exception("CAPTCHA detected or access denied")
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            products = []
            
            # Селекторы могут меняться - актуализировать при необходимости
            # Ищем карточки товаров
            product_cards = soup.select('div[data-widget="searchResult"]')[:limit]
            
            for card in product_cards:
                try:
                    # Название
                    name_elem = card.select_one('span[itemprop="name"]')
                    name = name_elem.get_text(strip=True) if name_elem else "Неизвестно"
                    
                    # Цена
                    price_elem = card.select_one('span[data-testid="price-value"]')
                    if not price_elem:
                        price_elem = card.select_one('div[class*="price"] span')
                    price_text = price_elem.get_text(strip=True) if price_elem else "0"
                    # Очистка цены от пробелов и символа ₽
                    price = float(price_text.replace(' ', '').replace('₽', '').replace('\xa0', ''))
                    
                    # Ссылка
                    link_elem = card.select_one('a[itemprop="url"]')
                    if not link_elem:
                        link_elem = card.select_one('a[href^="/product/"]')
                    url = f"https://www.ozon.ru{link_elem['href']}" if link_elem and link_elem.get('href') else ""
                    
                    # Рейтинг
                    rating_elem = card.select_one('span[class*="rating"]')
                    rating = float(rating_elem.get_text(strip=True).replace(',', '.')) if rating_elem else 0
                    
                    # Доступность
                    availability = "В наличии"
                    
                    products.append({
                        "name": name,
                        "price": price,
                        "currency": "RUB",
                        "shop": "Ozon",
                        "url": url,
                        "availability": availability,
                        "source": "ozon",
                        "rating": rating,
                        "reviews_count": 0
                    })
                except Exception:
                    continue  # Пропускаем проблемные карточки
            
            # Сохраняем в Redis
            redis_key = f"ext:{query}:ozon"
            from app.utils import get_redis_client
            redis_client = get_redis_client()
            redis_client.setex(redis_key, 300, json.dumps(products))
            return products
            
    except httpx.HTTPStatusError as e:
        if e.response.status_code in [403, 429, 503]:
            # Блокировка или rate limit - увеличиваем задержку
            raise self.retry(exc=e, countdown=60 * (self.request.retries + 1))
        raise self.retry(exc=e)
    except Exception as exc:
        if "CAPTCHA" in str(exc):
            # При CAPTCHA не retry, возвращаем пустой результат
            return []
        raise self.retry(exc=exc)


@celery_app.task(bind=True, max_retries=2, default_retry_delay=20)
def fetch_from_yandex_market(self, query: str, limit: int) -> List[Dict]:
    """
    Celery задача для поиска на Яндекс.Маркете через парсинг HTML.
    В продакшене рекомендуется использовать официальное API.
    
    Args:
        query: Поисковый запрос
        limit: Максимальное количество результатов
        
    Returns:
        Список найденных товаров
    """
    try:
        import httpx
        from fake_useragent import UserAgent
        from bs4 import BeautifulSoup
        import random
        
        PROXY_POOL = []
        
        def get_proxy():
            return random.choice(PROXY_POOL) if PROXY_POOL else None
        
        url = f"https://market.yandex.ru/search?text={query}"
        
        proxy = get_proxy()
        proxies = {"http://": proxy, "https://": proxy} if proxy else None
        
        headers = {
            "User-Agent": UserAgent().random,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
            "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8,en;q=0.7",
            "Referer": "https://yandex.ru/",
        }
        
        with httpx.Client(timeout=15.0, proxies=proxies, follow_redirects=True) as client:
            resp = client.get(url, headers=headers)
            resp.raise_for_status()
            
            if "captcha" in resp.text.lower():
                raise Exception("CAPTCHA detected")
            
            soup = BeautifulSoup(resp.text, 'html.parser')
            products = []
            
            # Селекторы для Яндекс.Маркета
            product_cards = soup.select('div[data-autotest-id="offer-card"]')[:limit]
            
            for card in product_cards:
                try:
                    name_elem = card.select_one('a[data-autotest-id="offer-title"]')
                    name = name_elem.get_text(strip=True) if name_elem else "Неизвестно"
                    
                    price_elem = card.select_one('div[data-autotest-id="price"]')
                    price_text = price_elem.get_text(strip=True) if price_elem else "0"
                    price = float(price_text.replace(' ', '').replace('₽', '').replace('\xa0', ''))
                    
                    link_elem = card.select_one('a[data-autotest-id="offer-title"]')
                    url = link_elem['href'] if link_elem and link_elem.get('href') else ""
                    if url.startswith('/'):
                        url = f"https://market.yandex.ru{url}"
                    
                    rating_elem = card.select_one('div[data-autotest-id="rating"]')
                    rating = float(rating_elem.get_text(strip=True).replace(',', '.')) if rating_elem else 0
                    
                    products.append({
                        "name": name,
                        "price": price,
                        "currency": "RUB",
                        "shop": "Яндекс.Маркет",
                        "url": url,
                        "availability": "В наличии",
                        "source": "yandex_market",
                        "rating": rating,
                        "reviews_count": 0
                    })
                except Exception:
                    continue
            
            redis_key = f"ext:{query}:ym"
            from app.utils import get_redis_client
            redis_client = get_redis_client()
            redis_client.setex(redis_key, 300, json.dumps(products))
            return products
            
    except Exception as exc:
        if "CAPTCHA" in str(exc):
            return []
        raise self.retry(exc=exc)


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
