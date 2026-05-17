from pydantic import BaseModel, Field, field_validator
from typing import Optional, List, Dict, Any


class SearchFilters(BaseModel):
    """Фильтры для поиска."""
    category: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    brand: Optional[str] = None
    availability: Optional[str] = None


class SearchRequest(BaseModel):
    """Запрос на поиск товаров."""
    query: str = Field(..., min_length=1, max_length=200)
    limit: int = Field(10, ge=1, le=100)
    filters: Optional[SearchFilters] = None
    sort_by: Optional[str] = Field(None, pattern="^(price|relevance|rating)$")
    sort_order: Optional[str] = Field("asc", pattern="^(asc|desc)$")

    @field_validator('query')
    @classmethod
    def validate_query(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError('Query must not be empty')
        return v


class ProductResult(BaseModel):
    """Результат поиска - товар."""
    id: Optional[str] = None
    name: str
    article: Optional[str] = None
    barcode: Optional[str] = None
    price: float
    currency: str = "RUB"
    shop: Optional[str] = None
    shop_id: Optional[str] = None
    url: Optional[str] = None
    availability: Optional[str] = None
    category: Optional[str] = None
    brand: Optional[str] = None
    image_url: Optional[str] = None
    rating: Optional[float] = None
    source: str = "internal"  # internal, wildberries, ozon, etc.
    relevance_score: Optional[float] = None


class SearchResponse(BaseModel):
    """Ответ на запрос поиска."""
    query: str
    total_found: int
    results: List[ProductResult]
    page: int = 1
    limit: int
    has_more: bool = False
    external_sources_pending: bool = False


class NormalizedQuery(BaseModel):
    """Нормализованный запрос."""
    original: str
    normalized: str
    type: str  # 'name', 'barcode', 'article'
    keywords: List[str] = []
    brand: Optional[str] = None
    category: Optional[str] = None
