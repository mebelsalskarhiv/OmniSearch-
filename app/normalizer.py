"""Модуль нормализации поисковых запросов."""

import re
from typing import Dict, List, Optional


def normalize_query(raw_query: str) -> Dict:
    """
    Нормализует поисковый запрос и определяет его тип.
    
    Определяет, что ввёл пользователь:
    - Штрихкод (EAN, UPC)
    - Артикул производителя
    - Текстовый запрос (название товара)
    
    Args:
        raw_query: Исходный запрос от пользователя
        
    Returns:
        Словарь с нормализованным запросом и метаданными
    """
    q = raw_query.strip().lower()
    
    # Удаляем лишние символы, но оставляем буквы/цифры/пробелы/дефис/точку
    q = re.sub(r'[^\w\s\-\.]', '', q)
    q = re.sub(r'\s+', ' ', q).strip()
    
    # Определение типа запроса
    query_type = 'name'
    
    # Штрихкод: только цифры, длина 8, 12, 13, 14 (EAN, UPC)
    if re.fullmatch(r'\d{8,14}', q):
        if is_valid_barcode(q):
            query_type = 'barcode'
    
    # Артикул: содержит буквы и цифры, часто без пробелов, длина 5-30 символов
    elif re.fullmatch(r'[a-zA-Z0-9\-_]{5,30}', q):
        query_type = 'article'
    
    # Для текстового запроса извлекаем ключевые слова
    keywords = [w for w in q.split() if len(w) > 1] if query_type == 'name' else []
    
    # Попытка извлечь бренд (первое слово, если оно заглавное в оригинале)
    brand = None
    if query_type == 'name':
        words = raw_query.strip().split()
        if words and words[0][0].isupper():
            brand = words[0]
    
    return {
        'original': raw_query,
        'normalized': q,
        'type': query_type,
        'keywords': keywords,
        'brand': brand
    }


def is_valid_barcode(code: str) -> bool:
    """
    Проверяет валидность штрихкода по контрольной сумме.
    Поддерживает EAN-8, EAN-13, UPC-A, UPC-E.
    
    Args:
        code: Код штрихкода (только цифры)
        
    Returns:
        True если штрихкод валиден
    """
    if not code.isdigit():
        return False
    
    length = len(code)
    
    # EAN-8
    if length == 8:
        return validate_ean8(code)
    # EAN-13 / UPC-A (12 цифр + контрольная)
    elif length == 13:
        return validate_ean13(code)
    elif length == 12:
        # UPC-A можно проверить как EAN-13 с добавлением 0 в начало
        return validate_ean13('0' + code)
    # EAN-14
    elif length == 14:
        return validate_ean14(code)
    
    return False


def validate_ean8(code: str) -> bool:
    """Проверка контрольной суммы EAN-8."""
    if len(code) != 8:
        return False
    
    digits = [int(d) for d in code]
    checksum = sum(digits[i] * (3 if i % 2 == 0 else 1) for i in range(7))
    expected_check = (10 - (checksum % 10)) % 10
    return digits[7] == expected_check


def validate_ean13(code: str) -> bool:
    """Проверка контрольной суммы EAN-13."""
    if len(code) != 13:
        return False
    
    digits = [int(d) for d in code]
    checksum = sum(digits[i] * (1 if i % 2 == 0 else 3) for i in range(12))
    expected_check = (10 - (checksum % 10)) % 10
    return digits[12] == expected_check


def validate_ean14(code: str) -> bool:
    """Проверка контрольной суммы EAN-14 (GTIN-14)."""
    if len(code) != 14:
        return False
    
    digits = [int(d) for d in code]
    checksum = sum(digits[i] * (3 if i % 2 == 0 else 1) for i in range(13))
    expected_check = (10 - (checksum % 10)) % 10
    return digits[13] == expected_check


def extract_brand_from_query(query: str) -> Optional[str]:
    """
    Пытается извлечь название бренда из запроса.
    
    Args:
        query: Исходный запрос
        
    Returns:
        Название бренда или None
    """
    # Популярные бренды электроники
    known_brands = {
        'apple', 'samsung', 'xiaomi', 'huawei', 'honor', 'oneplus',
        'sony', 'lg', 'philips', 'bosch', 'siemens', ' Electrolux',
        'nike', 'adidas', 'puma', 'zara', 'hm', 'uniqlo',
        'ikea', 'lego', 'barbie', 'matel'
    }
    
    words = query.lower().split()
    for word in words:
        if word in known_brands:
            return word.capitalize()
    
    return None
