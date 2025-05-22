"""
Модуль для обработки текста с учетом лимитов Telegram.
"""
import logging
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class TextProcessor:
    """Класс для обработки текста с учетом лимитов Telegram."""
    
    def __init__(self):
        self.MAX_CAPTION_LENGTH = 1024  # Максимальная длина подписи в медиа-группе
        self.TRUNCATE_MARKER = "❗️❗️❗️ТЕКСТ ОБРЕЗАН❗️❗️❗️"
        self.CHANNEL_SIGNATURE = "\n\n@pedalgaza_tg"
    
    async def process_text(
        self, 
        text: str, 
        is_channel: bool = False,
        add_truncate_marker: bool = True
    ) -> Tuple[str, bool]:
        """
        Асинхронно обрабатывает текст с учетом лимитов Telegram.
        
        Args:
            text: Исходный текст
            is_channel: Флаг, указывающий что текст будет отправлен в канал
            add_truncate_marker: Флаг, указывающий нужно ли добавлять маркер обрезки
            
        Returns:
            Tuple[str, bool]: (Обработанный текст, был ли текст обрезан)
        """
        logger.info(f"[process_text] Обработка текста длиной {len(text)} символов")
        
        # Если текст пустой, возвращаем как есть
        if not text:
            return text, False
            
        # Вычисляем доступную длину с учетом подписи канала и маркера обрезки
        available_length = self.MAX_CAPTION_LENGTH
        if is_channel:
            available_length -= len(self.CHANNEL_SIGNATURE)
        if add_truncate_marker:
            available_length -= len(self.TRUNCATE_MARKER) + 2  # +2 для переносов строк
            
        # Если текст короче доступной длины, просто добавляем подпись канала
        if len(text) <= available_length:
            if is_channel:
                return text + self.CHANNEL_SIGNATURE, False
            return text, False
            
        # Текст нужно обрезать
        truncated_text = text[:available_length]
        
        # Добавляем маркер обрезки, если нужно
        if add_truncate_marker:
            truncated_text = truncated_text.rstrip() + f"\n\n{self.TRUNCATE_MARKER}"
            
        # Добавляем подпись канала
        if is_channel:
            truncated_text += self.CHANNEL_SIGNATURE
            
        logger.info(f"[process_text] Текст обрезан до {len(truncated_text)} символов")
        return truncated_text, True

    async def process_private_channel_text(
        self,
        main_text: str,
        source_text: str,
        add_truncate_marker: bool = True
    ) -> Tuple[str, bool]:
        """
        Асинхронно обрабатывает текст для закрытого канала, сохраняя первые две строки из source.txt.
        
        Args:
            main_text: Основной текст из text_close.txt
            source_text: Первые две строки из source.txt
            add_truncate_marker: Флаг, указывающий нужно ли добавлять маркер обрезки
            
        Returns:
            Tuple[str, bool]: (Обработанный текст, был ли текст обрезан)
        """
        logger.info(f"[process_private_channel_text] Обработка текста для закрытого канала")
        logger.info(f"Длина основного текста: {len(main_text)}")
        logger.info(f"Длина текста из source.txt: {len(source_text)}")
        
        # Формируем полный текст
        full_text = f"{main_text}\n\n{source_text}"
        
        # Вычисляем доступную длину с учетом маркера обрезки
        available_length = self.MAX_CAPTION_LENGTH
        if add_truncate_marker:
            available_length -= len(self.TRUNCATE_MARKER) + 2  # +2 для переносов строк
            
        # Если текст короче доступной длины, возвращаем как есть
        if len(full_text) <= available_length:
            return full_text, False
            
        # Вычисляем, сколько символов можно оставить в основном тексте
        # с учетом длины source_text и маркера обрезки
        source_text_length = len(source_text) + 4  # +4 для двух переносов строк
        if add_truncate_marker:
            source_text_length += len(self.TRUNCATE_MARKER) + 2
            
        available_main_length = available_length - source_text_length
        
        # Обрезаем основной текст
        truncated_main = main_text[:available_main_length].rstrip()
        
        # Формируем итоговый текст
        if add_truncate_marker:
            truncated_main += f"\n\n{self.TRUNCATE_MARKER}"
            
        result_text = f"{truncated_main}\n\n{source_text}"
        
        logger.info(f"[process_private_channel_text] Текст обрезан до {len(result_text)} символов")
        return result_text, True
    
    async def get_original_text(self, text: str) -> str:
        """
        Асинхронно возвращает оригинальный текст, убирая маркер обрезки и подпись канала.
        
        Args:
            text: Текст с маркером обрезки и/или подписью канала
            
        Returns:
            str: Оригинальный текст
        """
        # Убираем подпись канала
        if text.endswith(self.CHANNEL_SIGNATURE):
            text = text[:-len(self.CHANNEL_SIGNATURE)]
            
        # Убираем маркер обрезки
        if self.TRUNCATE_MARKER in text:
            text = text.split(self.TRUNCATE_MARKER)[0].rstrip()
            
        return text 