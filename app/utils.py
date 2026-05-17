"""Утилиты и вспомогательные функции."""

import os
import redis
from typing import Optional
from functools import lru_cache


@lru_cache()
def get_redis_client() -> redis.Redis:
    """
    Получение клиента Redis (singleton).
    
    Returns:
        Подключенный клиент Redis
    """
    redis_url = os.getenv('REDIS_URL', 'redis://redis:6379/0')
    return redis.from_url(redis_url, decode_responses=True)


async def rate_limit_check(client_ip: str, max_requests: int = 100, window_seconds: int = 60) -> bool:
    """
    Проверка rate limiting для клиента.
    
    Args:
        client_ip: IP адрес клиента
        max_requests: Максимальное количество запросов в окно
        window_seconds: Размер окна в секундах
        
    Returns:
        True если запрос разрешён, False если превышен лимит
    """
    redis_client = get_redis_client()
    key = f"rate_limit:{client_ip}"
    
    current = redis_client.get(key)
    
    if current is None:
        redis_client.setex(key, window_seconds, 1)
        return True
    
    if int(current) >= max_requests:
        return False
    
    redis_client.incr(key)
    return True


def generate_task_id() -> str:
    """Генерация уникального ID для задачи."""
    import uuid
    return str(uuid.uuid4())
