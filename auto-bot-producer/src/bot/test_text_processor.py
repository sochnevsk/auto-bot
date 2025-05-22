"""
Тесты для модуля обработки текста.
"""
import asyncio
import logging
from text_processor import TextProcessor

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

async def test_text_processing():
    """Тест обработки текста."""
    processor = TextProcessor()
    
    # Тест 1: Короткий текст
    text = "Короткий текст"
    processed_text, was_truncated = await processor.process_text(text)
    assert not was_truncated
    assert processed_text == text
    
    # Тест 2: Длинный текст
    long_text = "Тестовый текст " * 100  # ~1500 символов
    processed_text, was_truncated = await processor.process_text(long_text)
    assert was_truncated
    assert len(processed_text) <= processor.MAX_CAPTION_LENGTH
    assert processor.TRUNCATE_MARKER in processed_text
    
    # Тест 3: Текст для канала
    text = "Текст для канала"
    processed_text, was_truncated = await processor.process_text(text, is_channel=True)
    assert not was_truncated
    assert processed_text.endswith(processor.CHANNEL_SIGNATURE)
    
    # Тест 4: Длинный текст для канала
    long_text = "Тестовый текст " * 100  # ~1500 символов
    processed_text, was_truncated = await processor.process_text(long_text, is_channel=True)
    assert was_truncated
    assert len(processed_text) <= processor.MAX_CAPTION_LENGTH
    assert processor.TRUNCATE_MARKER in processed_text
    assert processed_text.endswith(processor.CHANNEL_SIGNATURE)
    
    # Тест 5: Без маркера обрезки
    long_text = "Тестовый текст " * 100  # ~1500 символов
    processed_text, was_truncated = await processor.process_text(long_text, add_truncate_marker=False)
    assert was_truncated
    assert len(processed_text) <= processor.MAX_CAPTION_LENGTH
    assert processor.TRUNCATE_MARKER not in processed_text

async def test_get_original_text():
    """Тест получения оригинального текста."""
    processor = TextProcessor()
    
    # Тест 1: Текст с маркером обрезки
    text = "Текст\n\n!!!ТЕКСТ ОБРЕЗАН!!!"
    original = await processor.get_original_text(text)
    assert original == "Текст"
    
    # Тест 2: Текст с подписью канала
    text = "Текст\n\n@pedalgaza_tg"
    original = await processor.get_original_text(text)
    assert original == "Текст"
    
    # Тест 3: Текст с маркером обрезки и подписью канала
    text = "Текст\n\n!!!ТЕКСТ ОБРЕЗАН!!!\n\n@pedalgaza_tg"
    original = await processor.get_original_text(text)
    assert original == "Текст"
    
    # Тест 4: Обычный текст
    text = "Текст"
    original = await processor.get_original_text(text)
    assert original == text

async def run_tests():
    """Запуск всех тестов."""
    await test_text_processing()
    await test_get_original_text()
    print("Все тесты пройдены успешно!")

if __name__ == "__main__":
    asyncio.run(run_tests()) 