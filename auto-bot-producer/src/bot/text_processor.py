"""
Модуль для обработки текста с учетом лимитов Telegram.
"""
import logging
import re
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

class TextProcessor:
    """Класс для обработки текста с учетом лимитов Telegram."""
    
    def __init__(self):
        self.MAX_CAPTION_LENGTH = 1024  # Максимальная длина подписи в медиа-группе
        self.TRUNCATE_MARKER = "❗️❗️❗️ТЕКСТ ОБРЕЗАН❗️❗️❗️"
        self.CHANNEL_SIGNATURE = "\n\nДля более подробной информации: @PedalGaza_tg"
        
        # Специальные символы для MarkdownV2, которые нужно экранировать
        self.MARKDOWN_SPECIAL_CHARS = ['>', '#', '+', '-', '=', '|', '{', '}']
        
        # Регулярные выражения для форматирования
        self.FORMATTING_PATTERNS = {
            'bold': r'\*\*([^*]+(?:\*(?!\*)[^*]*)*)\*\*',  # **жирный текст, с запятыми!**
            'italic': r'\*([^*]+(?:\*(?!\*)[^*]*)*)\*',    # *курсив, с точками.*
            'underline': r'__([^_]+(?:_(?!_)[^_]*)*)__',   # __подчеркнутый, с восклицанием!__
            'strikethrough': r'~~([^~]+(?:~(?!~)[^~]*)*)~~',  # ~~зачеркнутый, с вопросами?~~
            'code': r'`([^`]+)`',        # `код, с запятыми,`
            'link': r'\[([^\]]+)\]\(([^)]+)\)'  # [текст, с запятыми](url)
        }
    
    def _escape_markdown(self, text: str) -> str:
        """
        Экранирует специальные символы для MarkdownV2, сохраняя форматирование.
        
        Args:
            text: Исходный текст
            
        Returns:
            str: Текст с экранированными специальными символами
        """
        # Сначала находим все форматированные блоки
        formatted_blocks = []
        for format_type, pattern in self.FORMATTING_PATTERNS.items():
            for match in re.finditer(pattern, text):
                start, end = match.span()
                formatted_blocks.append((start, end))
        
        # Сортируем блоки по начальной позиции
        formatted_blocks.sort(key=lambda x: x[0])
        
        # Экранируем специальные символы, пропуская форматированные блоки
        result = []
        last_end = 0
        
        for start, end in formatted_blocks:
            # Экранируем текст до форматированного блока
            result.append(self._escape_special_chars(text[last_end:start]))
            # Добавляем форматированный блок как есть
            result.append(text[start:end])
            last_end = end
            
        # Экранируем оставшийся текст
        if last_end < len(text):
            result.append(self._escape_special_chars(text[last_end:]))
            
        return ''.join(result)
    
    def _escape_special_chars(self, text: str) -> str:
        """
        Экранирует специальные символы в тексте.
        
        Args:
            text: Исходный текст
            
        Returns:
            str: Текст с экранированными специальными символами
        """
        for char in self.MARKDOWN_SPECIAL_CHARS:
            text = text.replace(char, f'\\{char}')
        return text
    
    def _preserve_formatting(self, text: str) -> str:
        """
        Сохраняет форматирование текста при обрезке.
        
        Args:
            text: Исходный текст с форматированием
            
        Returns:
            str: Текст с сохраненным форматированием
        """
        # Находим все форматированные блоки
        formatted_blocks = []
        for format_type, pattern in self.FORMATTING_PATTERNS.items():
            for match in re.finditer(pattern, text):
                start, end = match.span()
                formatted_blocks.append((start, end, match.group(0)))
        
        # Сортируем блоки по начальной позиции
        formatted_blocks.sort(key=lambda x: x[0])
        
        # Проверяем, не нарушаем ли мы форматирование при обрезке
        for start, end, block in formatted_blocks:
            if start < self.MAX_CAPTION_LENGTH < end:
                # Если обрезка попадает внутрь форматированного блока,
                # обрезаем до начала блока
                return text[:start]
        
        return text[:self.MAX_CAPTION_LENGTH]
    
    async def process_text(
        self, 
        text: str, 
        is_channel: bool = False,
        add_truncate_marker: bool = True
    ) -> Tuple[str, bool]:
        """
        Асинхронно обрабатывает текст с учетом лимитов Telegram.
        """
        logger.info(f"[process_text] Обработка текста длиной {len(text)} символов")
        if not text:
            return text, False
        # Вычисляем доступную длину для основного текста
        available_length = self.MAX_CAPTION_LENGTH
        if is_channel:
            available_length -= len(self.CHANNEL_SIGNATURE)
        if add_truncate_marker:
            available_length -= len(self.TRUNCATE_MARKER) + 2  # +2 для переносов строк
        # Обрезаем текст с учетом всех добавок
        was_truncated = False
        if len(text) > available_length:
            text = text[:available_length].rstrip()
            was_truncated = True
        # Добавляем маркер обрезки, если нужно
        if was_truncated and add_truncate_marker:
            text += f"\n\n{self.TRUNCATE_MARKER}"
        # Добавляем подпись канала
        if is_channel:
            text += self.CHANNEL_SIGNATURE
        # (Если бы был MarkdownV2 — экранировать здесь)
        logger.info(f"[process_text] Итоговая длина текста: {len(text)} символов")
        return text, was_truncated

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