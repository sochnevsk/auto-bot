import base64
import uuid
import logging
import aiohttp
from typing import Optional, Dict, Tuple

from config.settings import (
    SBER_API_URL,
    SBER_AUTH_URL,
    CLIENT_ID,
    CLIENT_SECRET,
    SINGLE_REQUEST_LIMIT
)

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
                    token_stats = {
                        'prompt_tokens': usage.get('prompt_tokens', 0),
                        'completion_tokens': usage.get('completion_tokens', 0),
                        'total_tokens': usage.get('total_tokens', 0)
                    }
                    
                    return formatted_text, token_stats
                else:
                    error_text = await response.text()
                    logging.error(f"Ошибка API Sber: {response.status} - {error_text}")
                    return None, {}
                    
    except Exception as e:
        logging.error(f"Ошибка при форматировании текста: {e}")
        return None, {} 