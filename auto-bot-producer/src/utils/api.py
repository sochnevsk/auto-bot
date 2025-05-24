"""
Модуль для работы с API Sber.
"""
import os
import logging
import aiohttp
from typing import Optional, Dict, Tuple

from src.config.settings import settings

logger = logging.getLogger(__name__)

async def get_access_token() -> Optional[str]:
    """Получает токен доступа к API Sber."""
    try:
        async with aiohttp.ClientSession() as session:
            data = {
                'scope': 'GIGACHAT_API_PERS',
                'grant_type': 'client_credentials'
            }
            auth = aiohttp.BasicAuth(settings.SBER_CLIENT_ID, settings.SBER_CLIENT_SECRET)
            
            async with session.post(settings.SBER_AUTH_URL, data=data, auth=auth, ssl=False) as response:
                if response.status == 200:
                    result = await response.json()
                    return result.get('access_token')
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка получения токена: {response.status} - {error_text}")
                    return None
                    
    except Exception as e:
        logger.error(f"Ошибка при получении токена: {e}")
        return None

async def format_text_with_sber(text: str, prompt: str) -> Tuple[Optional[str], Dict]:
    """
    Отправляет текст на форматирование через Sber API.
    
    Args:
        text (str): Исходный текст для форматирования
        prompt (str): Промпт для форматирования
        
    Returns:
        Tuple[Optional[str], Dict]: (Отформатированный текст или None в случае ошибки, статистика токенов)
    """
    try:
        # Получаем токен доступа
        access_token = await get_access_token()
        if not access_token:
            logger.error("Не удалось получить токен доступа")
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
                'max_tokens': settings.SINGLE_REQUEST_LIMIT
            }
            
            async with session.post(settings.SBER_API_URL, headers=headers, json=data, ssl=False) as response:
                if response.status == 200:
                    result = await response.json()
                    formatted_text = result['choices'][0]['message']['content']
                    
                    # Получаем статистику токенов
                    usage = result.get('usage', {})
                    token_stats = {
                        'prompt_tokens': usage.get('prompt_tokens', 0),
                        'completion_tokens': usage.get('completion_tokens', 0),
                        'total_tokens': usage.get('total_tokens', 0)
                    }
                    
                    return formatted_text, token_stats
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка API Sber: {response.status} - {error_text}")
                    return None, {}
                    
    except Exception as e:
        logger.error(f"Ошибка при форматировании текста: {e}")
        return None, {} 