import os
import logging
import aiohttp
import base64
import uuid
import asyncio
import json
from typing import Optional, Tuple, Dict
from datetime import datetime, date, timedelta
from dotenv import load_dotenv
from pathlib import Path

# Добавляем корневую директорию проекта в PYTHONPATH
import sys
sys.path.append(str(Path(__file__).resolve().parent.parent.parent))

from src.utils.token_tracker import TokenUsageTracker
from src.utils.api import format_text_with_sber
from config.settings import (
    SAVE_DIR,
    LOG_FILE,
    LOG_FORMAT,
    LOG_LEVEL,
    FORMAT_PROMPT
)

# Настройка логирования
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# Загрузка переменных окружения
load_dotenv()

# Конфигурация API
SBER_API_URL = os.getenv('SBER_API_URL', 'https://gigachat.devices.sberbank.ru/api/v1/chat/completions')
SBER_AUTH_URL = os.getenv('SBER_AUTH_URL', 'https://ngw.devices.sberbank.ru:9443/api/v2/oauth')
CLIENT_ID = os.getenv('SBER_CLIENT_ID', 'f6d9a0c5-d03f-40fc-8ce7-3df3f0880a2d')
CLIENT_SECRET = os.getenv('SBER_CLIENT_SECRET', '37c8508b-d0f1-4fff-8af6-1e645180dc5a')

# Лимиты токенов
MONTHLY_TOKEN_LIMIT = 100_000
DAILY_TOKEN_LIMIT = 10_000
SINGLE_REQUEST_LIMIT = 2_000

# Пороги предупреждений (в процентах)
WARNING_THRESHOLD = 80  # Предупреждение при достижении 80% лимита
CRITICAL_THRESHOLD = 90  # Критическое предупреждение при достижении 90% лимита

# Файл для хранения статистики
TOKEN_STATS_FILE = 'token_stats.json'

# Создаем глобальный трекер использования токенов
token_tracker = TokenUsageTracker()

async def get_access_token() -> Optional[str]:
    """
    Получает токен доступа от Sber API.
    
    Returns:
        Optional[str]: Токен доступа или None в случае ошибки
    """
    try:
        # Формируем Basic Auth заголовок
        auth_string = f"{CLIENT_ID}:{CLIENT_SECRET}"
        auth_bytes = auth_string.encode('ascii')
        base64_auth = base64.b64encode(auth_bytes).decode('ascii')
        
        headers = {
            'Authorization': f'Basic {base64_auth}',
            'Content-Type': 'application/x-www-form-urlencoded',
            'RqUID': str(uuid.uuid4())
        }
        
        data = {
            'scope': 'GIGACHAT_API_PERS'
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(SBER_AUTH_URL, headers=headers, data=data, ssl=False) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get('access_token')
                else:
                    error_text = await response.text()
                    logging.error(f"Ошибка получения токена: {response.status} - {error_text}")
                    return None
                    
    except Exception as e:
        logging.error(f"Ошибка при получении токена: {e}")
        return None

async def format_text_with_sber(text: str, prompt: str) -> Tuple[Optional[str], dict]:
    """
    Отправляет текст на форматирование через Sber API.
    
    Args:
        text (str): Исходный текст для форматирования
        prompt (str): Промпт для форматирования
        
    Returns:
        Tuple[Optional[str], dict]: (Отформатированный текст или None в случае ошибки, статистика токенов)
    """
    try:
        # Получаем токен доступа
        access_token = await get_access_token()
        if not access_token:
            logging.error("Не удалось получить токен доступа")
            return None, {}
            
        async with aiohttp.ClientSession() as session:
            headers = {
                'Authorization': f'Bearer {access_token}',
                'Content-Type': 'application/json'
            }
            
            data = {
                'model': 'GigaChat:latest',
                'messages': [
                    {'role': 'system', 'content': prompt},
                    {'role': 'user', 'content': text}
                ],
                'temperature': 0.7,
                'max_tokens': SINGLE_REQUEST_LIMIT
            }
            
            async with session.post(SBER_API_URL, headers=headers, json=data, ssl=False) as response:
                if response.status == 200:
                    result = await response.json()
                    formatted_text = result['choices'][0]['message']['content']
                    
                    # Получаем статистику токенов
                    usage = result.get('usage', {})
                    prompt_tokens = usage.get('prompt_tokens', 0)
                    completion_tokens = usage.get('completion_tokens', 0)
                    total = usage.get('total_tokens', 0)
                    
                    # Обновляем статистику использования токенов
                    token_tracker.add_usage(total, 'text_formatting')
                    
                    token_stats = {
                        'prompt_tokens': prompt_tokens,
                        'completion_tokens': completion_tokens,
                        'total_tokens': total
                    }
                    
                    return formatted_text, token_stats
                else:
                    error_text = await response.text()
                    logging.error(f"Ошибка API Sber: {response.status} - {error_text}")
                    return None, {}
                    
    except Exception as e:
        logging.error(f"Ошибка при форматировании текста: {e}")
        return None, {}

async def process_post_folder(post_folder: str) -> None:
    """
    Обрабатывает папку с постом, форматируя текст из text_close.txt
    
    Args:
        post_folder (str): Путь к папке поста
    """
    text_close_path = Path(post_folder) / 'text_close.txt'
    text_gpt_path = Path(post_folder) / 'text_gpt.txt'
    
    # Проверяем, существует ли файл text_close.txt
    if not text_close_path.exists():
        logging.info(f"Пропуск {post_folder}: нет файла text_close.txt")
        return
        
    # Проверяем, не был ли уже отформатирован текст
    if text_gpt_path.exists():
        logging.info(f"Пропуск {post_folder}: текст уже отформатирован")
        return
    
    try:
        # Читаем исходный текст
        with open(text_close_path, 'r', encoding='utf-8') as f:
            text = f.read().strip()
            
        if not text:
            logging.info(f"Пропуск {post_folder}: пустой текст")
            return
            
        # Форматируем текст
        logging.info(f"Форматирование текста в {post_folder}")
        formatted_text, token_stats = await format_text_with_sber(text, FORMAT_PROMPT)
        
        if formatted_text:
            # Обновляем статистику использования токенов
            token_tracker.add_usage(token_stats['total_tokens'], 'text_formatting')
            
            # Сохраняем отформатированный текст
            with open(text_gpt_path, 'w', encoding='utf-8') as f:
                f.write(formatted_text)
            logging.info(f"✅ Текст отформатирован и сохранен в {text_gpt_path}")
            logging.info(f"📊 Токены: prompt={token_stats['prompt_tokens']}, completion={token_stats['completion_tokens']}, total={token_stats['total_tokens']}")
        else:
            logging.error(f"❌ Не удалось отформатировать текст в {post_folder}")
                
    except Exception as e:
        logging.error(f"❌ Ошибка при обработке {post_folder}: {e}")

async def main():
    """
    Основная функция скрипта.
    Находит все папки с постами и обрабатывает их.
    """
    save_dir = Path(SAVE_DIR)
    if not save_dir.exists():
        logging.error(f"Директория {SAVE_DIR} не существует")
        return
        
    # Получаем список всех папок с постами
    post_folders = [
        folder for folder in save_dir.iterdir()
        if folder.is_dir() and folder.name.startswith('post_')
    ]
    
    if not post_folders:
        logging.info("Нет папок с постами для обработки")
        return
        
    logging.info(f"Найдено {len(post_folders)} папок с постами в {SAVE_DIR}")
    
    # Показываем текущую статистику
    stats = token_tracker.get_usage_stats()
    logging.info(f"📊 Текущая статистика токенов:")
    logging.info(f"Месяц: {stats['monthly']['used']}/{stats['monthly']['limit']} ({stats['monthly']['percent']:.1f}%)")
    logging.info(f"День: {stats['daily']['used']}/{stats['daily']['limit']} ({stats['daily']['percent']:.1f}%)")
    
    # Обрабатываем каждую папку
    for post_folder in post_folders:
        await process_post_folder(str(post_folder))
    
    # Показываем обновленную статистику
    stats = token_tracker.get_usage_stats()
    logging.info(f"\n📊 Обновленная статистика токенов:")
    logging.info(f"Месяц: {stats['monthly']['used']}/{stats['monthly']['limit']} ({stats['monthly']['percent']:.1f}%)")
    logging.info(f"День: {stats['daily']['used']}/{stats['daily']['limit']} ({stats['daily']['percent']:.1f}%)")
    
    # Показываем историю использования за последние 7 дней
    history = token_tracker.get_usage_history(7)
    if history:
        total_tokens = sum(entry['tokens'] for entry in history)
        logging.info(f"\n📊 Статистика за последние 7 дней:")
        logging.info(f"Всего использовано токенов: {total_tokens}")
        logging.info(f"Среднее использование в день: {total_tokens / 7:.1f}")

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logging.info("Скрипт остановлен пользователем")
    except Exception as e:
        logging.error(f"Критическая ошибка: {e}")
