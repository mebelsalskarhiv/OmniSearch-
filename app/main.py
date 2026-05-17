"""OmniSearch API Gateway - FastAPI приложение."""

import os
import asyncio
import json
from contextlib import asynccontextmanager
from typing import Optional, List

from fastapi import FastAPI, HTTPException, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi import SlowAPI, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from pydantic import BaseModel

from app.models import SearchRequest, SearchResponse, ProductResult, SearchFilters
from app.normalizer import normalize_query
from app.search_internal import internal_search_service
from app.search_external import external_search_service
from app.aggregator import aggregator
from app.utils import rate_limit_check, get_redis_client
from app.tasks import fetch_from_wildberries, fetch_from_ozon


# Инициализация rate limiter
slowapi = SlowAPI()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Жизненный цикл приложения - инициализация и закрытие соединений."""
    # Startup
    await internal_search_service.connect()
    yield
    # Shutdown
    await internal_search_service.disconnect()


app = FastAPI(
    title="OmniSearch",
    description="Универсальная поисковая система для агрегации товаров",
    version="1.0.0",
    lifespan=lifespan
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Rate limiting
app.state.limiter = slowapi
app.add_exception_handler(429, _rate_limit_exceeded_handler)


@app.post("/api/v1/search", response_model=SearchResponse)
@slowapi.limit("100/minute")
async def search(request: SearchRequest, req: Request):
    """
    Поиск товаров по запросу.
    
    Выполняет поиск во внутренней базе данных и запускает асинхронный
    сбор данных из внешних источников (Wildberries, Ozon).
    """
    # Rate limiting
    client_ip = req.client.host
    if not await rate_limit_check(client_ip):
        raise HTTPException(status_code=429, detail="Too many requests")
    
    # Нормализация запроса
    query_info = normalize_query(request.query)
    
    # Поиск во внутренней базе
    internal_results = await internal_search_service.search(query_info, request.limit)
    
    # Запуск асинхронного поиска во внешних источниках
    external_task_wb = fetch_from_wildberries.delay(query_info['normalized'], request.limit)
    external_task_ozon = fetch_from_ozon.delay(query_info['normalized'], request.limit)
    
    # Агрегация результатов (пока только внутренние)
    filters_dict = request.filters.model_dump() if request.filters else None
    
    final_results = aggregator.aggregate(
        internal_results=internal_results,
        external_results=[],  # Внешние результаты будут позже
        limit=request.limit,
        filters=filters_dict,
        sort_by=request.sort_by or "relevance",
        sort_order=request.sort_order or "asc"
    )
    
    # Конвертация в модель ProductResult
    product_results = [ProductResult(**item) for item in final_results]
    
    return SearchResponse(
        query=request.query,
        total_found=len(product_results),
        results=product_results,
        limit=request.limit,
        has_more=len(internal_results) > request.limit,
        external_sources_pending=True  # Внешние источники ещё обрабатываются
    )


@app.get("/api/v1/search/{task_id}")
async def get_search_results(task_id: str):
    """
    Получение результатов поиска по ID задачи.
    
    Используется для получения результатов от внешних источников,
    которые обрабатываются асинхронно.
    """
    redis_client = get_redis_client()
    
    # Проверяем наличие результатов в Redis
    result = redis_client.get(f"search:{task_id}")
    if result:
        return json.loads(result)
    
    raise HTTPException(status_code=404, detail="Search results not found")


@app.get("/health")
async def health_check():
    """Проверка здоровья сервиса."""
    return {"status": "healthy", "version": "1.0.0"}


@app.get("/")
async def root():
    """Корневой эндпоинт."""
    return {
        "service": "OmniSearch",
        "version": "1.0.0",
        "docs": "/docs",
        "health": "/health"
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
