"""Unit тесты для модуля агрегации результатов."""

import pytest
from app.aggregator import aggregator


class TestAggregator:
    """Тесты для агрегатора результатов."""

    def test_merge_internal_and_external(self):
        """Тест объединения внутренних и внешних результатов."""
        internal = [
            {"id": "1", "name": "iPhone 15", "price": 90000, "shop": "М.Видео", "source": "internal"},
            {"id": "2", "name": "iPhone 15 Pro", "price": 110000, "shop": "DNS", "source": "internal"}
        ]
        
        external = [
            {"name": "Apple iPhone 15 128GB", "price": 89990, "shop": "Wildberries", "source": "wildberries"},
            {"name": "iPhone 15", "price": 92000, "shop": "Ozon", "source": "ozon"}
        ]
        
        result = aggregator.aggregate(internal_results=internal, external_results=external, limit=10)
        
        assert len(result) > 0
        # Проверяем что есть результаты из обоих источников
        sources = set(item.get('source') for item in result)
        assert 'internal' in sources or 'wildberries' in sources or 'ozon' in sources

    def test_deduplication_by_article(self):
        """Тест дедупликации по артикулу."""
        items = [
            {"name": "iPhone 15", "article": "A12345", "price": 90000, "shop": "Shop1"},
            {"name": "Apple iPhone 15", "article": "A12345", "price": 89990, "shop": "Shop2"}
        ]
        
        result = aggregator.remove_duplicates(items)
        
        # Должен остаться один товар с одинаковым артикулом
        assert len(result) == 1
        assert result[0]['article'] == "A12345"

    def test_deduplication_fuzzy_name(self):
        """Тест fuzzy-дедупликации по названию."""
        items = [
            {"name": "Samsung Galaxy S23 Ultra 256GB", "price": 95000, "shop": "Shop1"},
            {"name": "Samsung Galaxy S23 Ultra 256 GB", "price": 94000, "shop": "Shop2"}
        ]
        
        result = aggregator.remove_duplicates(items)
        
        # Названия очень похожи - должен остаться один
        assert len(result) == 1

    def test_filter_by_price_range(self):
        """Тест фильтрации по диапазону цен."""
        items = [
            {"name": "Product 1", "price": 50000},
            {"name": "Product 2", "price": 80000},
            {"name": "Product 3", "price": 120000},
            {"name": "Product 4", "price": 150000}
        ]
        
        filters = {"price_min": 70000, "price_max": 130000}
        result = aggregator.apply_filters(items, filters)
        
        assert len(result) == 2
        prices = [item['price'] for item in result]
        assert all(70000 <= p <= 130000 for p in prices)

    def test_filter_by_category(self):
        """Тест фильтрации по категории."""
        items = [
            {"name": "iPhone 15", "category": "electronics"},
            {"name": "T-Shirt", "category": "clothing"},
            {"name": "MacBook", "category": "electronics"}
        ]
        
        filters = {"category": "electronics"}
        result = aggregator.apply_filters(items, filters)
        
        assert len(result) == 2
        assert all(item['category'] == 'electronics' for item in result)

    def test_sort_by_price_asc(self):
        """Тест сортировки по цене (возрастание)."""
        items = [
            {"name": "Product 1", "price": 100000},
            {"name": "Product 2", "price": 50000},
            {"name": "Product 3", "price": 75000}
        ]
        
        result = aggregator.sort_results(items, sort_by='price_asc')
        
        assert result[0]['price'] == 50000
        assert result[1]['price'] == 75000
        assert result[2]['price'] == 100000

    def test_sort_by_price_desc(self):
        """Тест сортировки по цене (убывание)."""
        items = [
            {"name": "Product 1", "price": 100000},
            {"name": "Product 2", "price": 50000},
            {"name": "Product 3", "price": 75000}
        ]
        
        result = aggregator.sort_results(items, sort_by='price_desc')
        
        assert result[0]['price'] == 100000
        assert result[1]['price'] == 75000
        assert result[2]['price'] == 50000

    def test_limit_results(self):
        """Тест лимитирования результатов."""
        items = [{"name": f"Product {i}", "price": i * 1000} for i in range(20)]
        
        result = aggregator.limit_results(items, limit=5)
        
        assert len(result) == 5

    def test_full_aggregation_pipeline(self):
        """Тест полного пайплайна агрегации."""
        internal = [
            {"id": "1", "name": "iPhone 15", "price": 90000, "category": "electronics", "source": "internal"},
            {"id": "2", "name": "Samsung S23", "price": 85000, "category": "electronics", "source": "internal"}
        ]
        
        external = [
            {"name": "Apple iPhone 15 128GB", "price": 89990, "category": "electronics", "source": "wildberries"},
            {"name": "iPhone 15", "price": 92000, "category": "electronics", "source": "ozon"},
            {"name": "Cheap Phone", "price": 10000, "category": "electronics", "source": "wb"}
        ]
        
        filters = {"price_min": 50000, "price_max": 100000, "category": "electronics"}
        
        result = aggregator.aggregate(
            internal_results=internal,
            external_results=external,
            limit=5,
            filters=filters,
            sort_by='price_asc'
        )
        
        # Все цены должны быть в диапазоне
        assert all(50000 <= item['price'] <= 100000 for item in result)
        # Лимит соблюден
        assert len(result) <= 5
        # Отсортировано по возрастанию цены
        for i in range(len(result) - 1):
            assert result[i]['price'] <= result[i+1]['price']

    def test_empty_inputs(self):
        """Тест с пустыми входными данными."""
        result = aggregator.aggregate(internal_results=[], external_results=[], limit=10)
        assert len(result) == 0

    def test_no_duplicates_different_shops(self):
        """Тест что товары из разных магазинов с разными названиями не дублируются."""
        items = [
            {"name": "iPhone 15", "price": 90000, "shop": "М.Видео"},
            {"name": "Samsung S23", "price": 85000, "shop": "DNS"},
            {"name": "Pixel 8", "price": 75000, "shop": "Wildberries"}
        ]
        
        result = aggregator.remove_duplicates(items)
        
        assert len(result) == 3
