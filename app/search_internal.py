"""Модуль поиска по внутренней базе данных (PostgreSQL + Elasticsearch)."""

import os
import json
from typing import List, Dict, Any, Optional
from elasticsearch import AsyncElasticsearch
import asyncpg


class InternalSearchService:
    """Сервис для поиска товаров во внутренних хранилищах."""
    
    def __init__(self):
        self.es_host = os.getenv('ES_HOST', 'http://elasticsearch:9200')
        self.db_url = os.getenv('DATABASE_URL', 'postgresql://user:pass@postgres:5432/searchdb')
        self.es = None
        self.db_pool = None
    
    async def connect(self):
        """Инициализация соединений с ES и PostgreSQL."""
        self.es = AsyncElasticsearch([self.es_host])
        self.db_pool = await asyncpg.create_pool(self.db_url)
    
    async def disconnect(self):
        """Закрытие соединений."""
        if self.es:
            await self.es.close()
        if self.db_pool:
            await self.db_pool.close()
    
    async def search(self, query_info: Dict, limit: int) -> List[Dict]:
        """
        Поиск товаров по внутренней базе.
        
        Args:
            query_info: Нормализованный запрос с типом
            limit: Максимальное количество результатов
            
        Returns:
            Список найденных товаров
        """
        query_type = query_info['type']
        normalized = query_info['normalized']
        
        if query_type == 'barcode':
            return await self._search_by_barcode(normalized)
        elif query_type == 'article':
            products = await self._search_by_article(normalized)
            if not products:
                # Если не нашли по артикулу, ищем по названию
                products = await self._search_by_name(normalized, limit)
            return products
        else:  # name
            return await self._search_by_name(normalized, limit)
    
    async def _search_by_barcode(self, barcode: str) -> List[Dict]:
        """Точный поиск по штрихкоду."""
        async with self.db_pool.acquire() as conn:
            row = await conn.fetchrow("""
                SELECT p.id, p.name, p.article, p.barcode, p.category, p.brand,
                       sp.price, sp.currency, sp.availability, sp.url, s.name as shop_name
                FROM products p
                LEFT JOIN shop_products sp ON p.id = sp.product_id
                LEFT JOIN shops s ON sp.shop_id = s.id
                WHERE p.barcode = $1
                LIMIT 1
            """, barcode)
            
            if row:
                return [self._row_to_product(row, 'internal')]
            return []
    
    async def _search_by_article(self, article: str) -> List[Dict]:
        """Точный поиск по артикулу."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT p.id, p.name, p.article, p.barcode, p.category, p.brand,
                       sp.price, sp.currency, sp.availability, sp.url, s.name as shop_name
                FROM products p
                LEFT JOIN shop_products sp ON p.id = sp.product_id
                LEFT JOIN shops s ON sp.shop_id = s.id
                WHERE p.article = $1
            """, article)
            
            return [self._row_to_product(row, 'internal') for row in rows]
    
    async def _search_by_name(self, query_str: str, limit: int) -> List[Dict]:
        """Полнотекстовый поиск по названию и описанию через Elasticsearch."""
        body = {
            "query": {
                "multi_match": {
                    "query": query_str,
                    "fields": ["name^3", "description", "brand"],
                    "type": "best_fields",
                    "fuzziness": "AUTO"
                }
            },
            "size": limit
        }
        
        try:
            res = await self.es.search(index="products_search", body=body)
            products = []
            for hit in res["hits"]["hits"]:
                source = hit["_source"]
                products.append({
                    "id": source.get("id"),
                    "name": source.get("name"),
                    "article": source.get("article"),
                    "barcode": source.get("barcode"),
                    "category": source.get("category"),
                    "brand": source.get("brand"),
                    "price": 0.0,  # Цену нужно подтянуть из PostgreSQL
                    "currency": "RUB",
                    "availability": None,
                    "url": None,
                    "shop": None,
                    "source": "internal",
                    "relevance_score": hit.get("_score")
                })
            return products
        except Exception as e:
            print(f"Elasticsearch search error: {e}")
            # Fallback на PostgreSQL триграммный поиск
            return await self._search_by_name_pg(query_str, limit)
    
    async def _search_by_name_pg(self, query_str: str, limit: int) -> List[Dict]:
        """Резервный поиск по PostgreSQL с использованием триграмм."""
        async with self.db_pool.acquire() as conn:
            rows = await conn.fetch("""
                SELECT p.id, p.name, p.article, p.barcode, p.category, p.brand,
                       sp.price, sp.currency, sp.availability, sp.url, s.name as shop_name,
                       similarity(p.name, $1) as sim
                FROM products p
                LEFT JOIN shop_products sp ON p.id = sp.product_id
                LEFT JOIN shops s ON sp.shop_id = s.id
                WHERE similarity(p.name, $1) > 0.2
                ORDER BY sim DESC
                LIMIT $2
            """, query_str, limit)
            
            return [self._row_to_product(row, 'internal') for row in rows]
    
    def _row_to_product(self, row: asyncpg.Record, source: str) -> Dict:
        """Преобразование строки БД в словарь продукта."""
        return {
            "id": str(row["id"]) if row["id"] else None,
            "name": row["name"],
            "article": row["article"],
            "barcode": row["barcode"],
            "category": row["category"],
            "brand": row["brand"],
            "price": float(row["price"]) if row["price"] else 0.0,
            "currency": row["currency"] or "RUB",
            "availability": row["availability"],
            "url": row["url"],
            "shop": row["shop_name"],
            "source": source,
            "relevance_score": None
        }


# Глобальный экземпляр сервиса
internal_search_service = InternalSearchService()
