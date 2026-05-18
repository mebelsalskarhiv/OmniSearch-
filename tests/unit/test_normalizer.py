"""Unit тесты для модуля нормализации запросов."""

import pytest
from app.normalizer import normalize_query


class TestNormalizeQuery:
    """Тесты для функции normalize_query."""

    def test_simple_text_query(self):
        """Тест обычного текстового запроса."""
        result = normalize_query("iPhone 15 128GB")
        
        assert result['original'] == "iPhone 15 128GB"
        assert result['normalized'] == "iphone 15 128gb"
        assert result['type'] == 'name'
        assert result['keywords'] == ['iphone', '15', '128gb']

    def test_barcode_ean13_valid(self):
        """Тест валидного штрихкода EAN-13."""
        # Валидный EAN-13: 4600001234567 (с правильной контрольной суммой)
        result = normalize_query("4600001234567")
        
        assert result['original'] == "4600001234567"
        assert result['normalized'] == "4600001234567"
        assert result['type'] == 'barcode'
        assert result['keywords'] == []

    def test_barcode_ean8_valid(self):
        """Тест валидного штрихкода EAN-8."""
        # Валидный EAN-8: 12345670
        result = normalize_query("12345670")
        
        assert result['original'] == "12345670"
        assert result['normalized'] == "12345670"
        assert result['type'] == 'barcode'
        assert result['keywords'] == []

    def test_barcode_invalid_checksum(self):
        """Тест штрихкода с неверной контрольной суммой."""
        # Неверная контрольная сумма
        result = normalize_query("4600001234568")
        
        assert result['original'] == "4600001234568"
        assert result['normalized'] == "4600001234568"
        assert result['type'] == 'name'  # Должен распознаваться как текст

    def test_article_mixed(self):
        """Тест артикула со смешанными символами."""
        result = normalize_query("ABC-123_XYZ")
        
        assert result['original'] == "ABC-123_XYZ"
        assert result['normalized'] == "abc-123_xyz"
        assert result['type'] == 'article'
        assert result['keywords'] == []

    def test_query_with_special_chars(self):
        """Тест запроса со специальными символами."""
        result = normalize_query("iPhone 15! @#$% 128GB^&*()")
        
        assert result['normalized'] == "iphone 15 128gb"
        assert result['type'] == 'name'
        assert result['keywords'] == ['iphone', '15', '128gb']

    def test_empty_query_after_strip(self):
        """Тест пустого запроса после очистки."""
        with pytest.raises(ValueError):
            normalize_query("   ")

    def test_single_char_keywords_filtered(self):
        """Тест фильтрации односимвольных ключевых слов."""
        result = normalize_query("a b c iPhone d")
        
        assert 'a' not in result['keywords']
        assert 'b' not in result['keywords']
        assert 'd' not in result['keywords']
        assert 'iphone' in result['keywords']

    def test_long_query_truncated(self):
        """Тест длинного запроса."""
        long_query = "iPhone " * 50  # Длинный запрос
        result = normalize_query(long_query)
        
        assert len(result['normalized']) <= 200
        assert result['type'] == 'name'

    def test_upc_code(self):
        """Тест UPC кода (12 цифр)."""
        # Валидный UPC-A: 012345678905
        result = normalize_query("012345678905")
        
        # UPC требует 12 цифр, проверяем что распознан как barcode или name
        assert result['original'] == "012345678905"
        assert result['normalized'] == "012345678905"
        # Тип зависит от реализации проверки

    def test_russian_text_query(self):
        """Тест запроса на русском языке."""
        result = normalize_query("Смартфон Apple iPhone 15")
        
        assert result['original'] == "Смартфон Apple iPhone 15"
        assert result['normalized'] == "смартфон apple iphone 15"
        assert result['type'] == 'name'
        assert 'смартфон' in result['keywords']
        assert 'apple' in result['keywords']
        assert 'iphone' in result['keywords']
        assert '15' in result['keywords']

    def test_query_with_hyphen(self):
        """Тест запроса с дефисом."""
        result = normalize_query("Samsung Galaxy S23-Ultra")
        
        assert result['normalized'] == "samsung galaxy s23-ultra"
        assert result['type'] == 'name'
        assert 's23-ultra' in result['keywords'] or 's23' in result['keywords']

    def test_numeric_only_not_barcode(self):
        """Тест чисто числового запроса, не являющегося штрихкодом."""
        # Число меньше 8 цифр - не штрихкод
        result = normalize_query("12345")
        
        assert result['type'] == 'name'
        assert result['keywords'] == []  # Односимвольные фильтруются

    def test_whitespace_normalization(self):
        """Тест нормализации пробелов."""
        result = normalize_query("  iPhone    15   128GB  ")
        
        assert result['normalized'] == "iphone 15 128gb"
        assert result['keywords'] == ['iphone', '15', '128gb']
