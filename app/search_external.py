"""Модуль поиска по внешним источникам (Wildberries, Ozon, etc.)."""

import os
import json
import asyncio
import httpx
from typing import List, Dict, Any
from fake_useragent import UserAgent


class ExternalSearchService:
    """Сервис для поиска товаров во внешних источниках."""
    
    def __init__(self):
        self.timeout = httpx.Timeout(10.0)
        self.ua = UserAgent()
    
    async def search_all(self, query: str, limit: int) -> List[Dict]:
        """
        Параллельный поиск по всем внешним источникам.
        
        Args:
            query: Нормализованный поисковый запрос
            limit: Максимальное количество результатов с каждого источника
            
        Returns:
            Объединённый список товаров из всех источников
        """
        tasks = [
            self.search_wildberries(query, limit),
            self.search_ozon(query, limit),
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        all_products = []
        for result in results:
            if isinstance(result, Exception):
                print(f"External search error: {result}")
                continue
            all_products.extend(result)
        
        return all_products
    
    async def search_wildberries(self, query: str, limit: int) -> List[Dict]:
        """Поиск на Wildberries через API."""
        url = f"https://search.wb.ru/exactmatch/ru/common/v4/search"
        params = {
            "query": query,
            "resultset": "catalog",
            "limit": limit
        }
        headers = {"User-Agent": self.ua.random}
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                data = resp.json()
            
            products = []
            for item in data.get("data", {}).get("products", [])[:limit]:
                products.append({
                    "name": item.get("name"),
                    "price": item.get("salePriceU", 0) / 100,  # копейки в рубли
                    "currency": "RUB",
                    "shop": "Wildberries",
                    "url": f"https://www.wildberries.ru/catalog/{item.get('id')}/detail.aspx",
                    "availability": "В наличии" if item.get("saleConditions", {}).get("saleAvailable") else "Под заказ",
                    "source": "wildberries",
                    "image_url": item.get("images", [None])[0] if item.get("images") else None,
                    "rating": item.get("reviewRating", 0)
                })
            return products
        except Exception as e:
            print(f"Wildberries search error: {e}")
            return []
    
    async def search_ozon(self, query: str, limit: int) -> List[Dict]:
        """Поиск на Ozon (через публичное API или парсинг)."""
        # Примечание: Ozon не имеет публичного API для поиска
        # Это пример реализации, требующий доработки
        url = f"https://www.ozon.ru/search/"
        params = {
            "text": query,
            "from_global": "true"
        }
        headers = {"User-Agent": self.ua.random}
        
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url, params=params, headers=headers)
                resp.raise_for_status()
                # Здесь нужен парсинг HTML через BeautifulSoup
                # Для краткости возвращаем пустой список
                return []
        except Exception as e:
            print(f"Ozon search error: {e}")
            return []


# Глобальный экземпляр сервиса
external_search_service = ExternalSearchService()
