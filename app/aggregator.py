"""Модуль агрегации и ранжирования результатов поиска."""

import json
from typing import List, Dict, Any, Optional
from fuzzywuzzy import fuzz


class ResultAggregator:
    """Агрегатор результатов поиска из разных источников."""
    
    def __init__(self, duplicate_threshold: int = 90):
        """
        Args:
            duplicate_threshold: Порог схожести для определения дубликатов (0-100)
        """
        self.duplicate_threshold = duplicate_threshold
    
    def aggregate(
        self,
        internal_results: List[Dict],
        external_results: List[Dict],
        limit: int,
        filters: Optional[Dict] = None,
        sort_by: str = "relevance",
        sort_order: str = "asc"
    ) -> List[Dict]:
        """
        Объединение, фильтрация и ранжирование результатов.
        
        Args:
            internal_results: Результаты из внутренней БД
            external_results: Результаты из внешних источников
            limit: Максимальное количество результатов
            filters: Фильтры (цена, категория, etc.)
            sort_by: Сортировка (relevance, price, rating)
            sort_order: Порядок сортировки (asc, desc)
            
        Returns:
            Отфильтрованный и отсортированный список товаров
        """
        # Объединяем результаты
        all_items = internal_results + external_results
        
        # Применяем фильтры
        if filters:
            all_items = self._apply_filters(all_items, filters)
        
        # Удаляем дубликаты
        unique_items = self._remove_duplicates(all_items)
        
        # Сортируем
        sorted_items = self._sort(unique_items, sort_by, sort_order)
        
        # Ограничиваем количество
        return sorted_items[:limit]
    
    def _apply_filters(self, items: List[Dict], filters: Dict) -> List[Dict]:
        """Применение пользовательских фильтров."""
        filtered = []
        
        for item in items:
            # Фильтр по цене
            if filters.get('price_min') and item.get('price', 0) < filters['price_min']:
                continue
            if filters.get('price_max') and item.get('price', 0) > filters['price_max']:
                continue
            
            # Фильтр по категории
            if filters.get('category'):
                item_category = (item.get('category') or '').lower()
                if filters['category'].lower() not in item_category:
                    continue
            
            # Фильтр по бренду
            if filters.get('brand'):
                item_brand = (item.get('brand') or '').lower()
                if filters['brand'].lower() not in item_brand:
                    continue
            
            # Фильтр по доступности
            if filters.get('availability'):
                item_avail = (item.get('availability') or '').lower()
                if filters['availability'].lower() not in item_avail:
                    continue
            
            filtered.append(item)
        
        return filtered
    
    def _remove_duplicates(self, items: List[Dict]) -> List[Dict]:
        """
        Удаление дубликатов товаров.
        
        Дубликатом считается товар с:
        - Одинаковым артикулом или штрихкодом
        - Или очень похожим названием (fuzzy matching)
        """
        seen = []
        unique = []
        
        for item in items:
            is_dup = False
            
            for seen_item in seen:
                # Проверка по артикулу
                if item.get('article') and seen_item.get('article'):
                    if item['article'] == seen_item['article']:
                        is_dup = True
                        # Оставляем товар с меньшей ценой
                        if item.get('price', 0) < seen_item.get('price', 0):
                            seen.remove(seen_item)
                            seen.append(item)
                        break
                
                # Проверка по штрихкоду
                if item.get('barcode') and seen_item.get('barcode'):
                    if item['barcode'] == seen_item['barcode']:
                        is_dup = True
                        if item.get('price', 0) < seen_item.get('price', 0):
                            seen.remove(seen_item)
                            seen.append(item)
                        break
                
                # Fuzzy comparison по названию
                name_sim = fuzz.token_sort_ratio(
                    item.get('name', ''),
                    seen_item.get('name', '')
                )
                if name_sim > self.duplicate_threshold:
                    is_dup = True
                    if item.get('price', 0) < seen_item.get('price', 0):
                        seen.remove(seen_item)
                        seen.append(item)
                    break
            
            if not is_dup:
                seen.append(item)
                unique.append(item)
        
        return unique
    
    def _sort(self, items: List[Dict], sort_by: str, order: str) -> List[Dict]:
        """Сортировка результатов."""
        reverse = (order == 'desc')
        
        if sort_by == 'price':
            return sorted(items, key=lambda x: x.get('price', 0), reverse=reverse)
        elif sort_by == 'rating':
            return sorted(items, key=lambda x: x.get('rating', 0), reverse=reverse)
        else:  # relevance
            return sorted(
                items,
                key=lambda x: x.get('relevance_score', 0) or 0,
                reverse=True  # релевантность всегда по убыванию
            )
    
    def group_by_shop(self, items: List[Dict]) -> Dict[str, List[Dict]]:
        """Группировка товаров по магазинам."""
        grouped = {}
        for item in items:
            shop = item.get('shop', 'Unknown')
            if shop not in grouped:
                grouped[shop] = []
            grouped[shop].append(item)
        return grouped
    
    def get_best_prices(self, items: List[Dict]) -> List[Dict]:
        """
        Для каждого уникального товара оставляет предложение с минимальной ценой.
        """
        # Группируем по названию+артикулу
        product_map = {}
        
        for item in items:
            key = f"{item.get('name', '')}:{item.get('article', '')}"
            if key not in product_map:
                product_map[key] = item
            else:
                # Оставляем более дешёвое предложение
                if item.get('price', 0) < product_map[key].get('price', 0):
                    product_map[key] = item
        
        return list(product_map.values())


# Глобальный экземпляр
aggregator = ResultAggregator()
