"""Модуль для работы с API Sber."""
import logging
import aiohttp
from typing import Tuple, Dict
from src.config.settings import settings
import uuid

logger = logging.getLogger(__name__)

async def get_access_token() -> str:
    """Получение токена доступа к API Sber."""
    try:
        async with aiohttp.ClientSession() as session:
            auth = aiohttp.BasicAuth(settings.SBER_CLIENT_ID, settings.SBER_CLIENT_SECRET)
            headers = {
                'Content-Type': 'application/x-www-form-urlencoded',
                'RqUID': str(uuid.uuid4())
            }
            data = {
                'scope': 'GIGACHAT_API_PERS'
            }
            async with session.post(
                settings.SBER_AUTH_URL,
                auth=auth,
                headers=headers,
                data=data,
                verify_ssl=False
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get('access_token')
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка получения токена: {error_text}")
                    raise Exception(f"Ошибка получения токена: {response.status}")
    except Exception as e:
        logger.error(f"Ошибка при получении токена: {e}", exc_info=True)
        raise

async def format_text_with_sber(text: str) -> Tuple[str, Dict]:
    """Форматирование текста через API Sber."""
    try:
        access_token = await get_access_token()
        
        headers = {
            'Authorization': f'Bearer {access_token}',
            'Content-Type': 'application/json'
        }
        
        system_prompt = """Ты автомобильный эксперт и хорошо знаешь марки и модели машин. 
Возьми из текста необходимую информацию и преобразуй его в вид: (
    1. Марка машины: (сохраняй точное написание, например: Mercedes-Benz, BMW, Audi)
    2. Модель: (указывай полное название модели, включая все буквы и цифры, например: X3 30i, M5 Competition и т.д.)  
    3. VIN-код: (указывай только цифры и буквы, без пробелов)
    4. Пробег:  
    5. Год:  
    6. Цена:  )
Важно:
- Сохраняй точное написание названия марки (например, Mercedes-Benz, а не Mercedes-Benx)
- Сохраняй все буквы и цифры в названии модели (например, X3 30i, а не просто X3)
- Если в тексте есть несколько ссылок, указывай их все
- Если есть несколько контактов, указывай их все
- Если нет нужных данных, то строго ставь прочерк (-)
- Не добавляй от себя никакой информации
- Не меняй формат вывода"""
        
        data = {
            'model': 'GigaChat:latest',
            'messages': [
                {
                    'role': 'system',
                    'content': system_prompt
                },
                {
                    'role': 'user',
                    'content': text
                }
            ],
            'temperature': 0.7,
            'max_tokens': settings.SINGLE_REQUEST_LIMIT
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.post(
                settings.SBER_API_URL,
                headers=headers,
                json=data,
                verify_ssl=False
            ) as response:
                if response.status == 200:
                    result = await response.json()
                    formatted_text = result['choices'][0]['message']['content']
                    token_stats = {
                        'prompt_tokens': result['usage']['prompt_tokens'],
                        'completion_tokens': result['usage']['completion_tokens'],
                        'total_tokens': result['usage']['total_tokens']
                    }
                    return formatted_text, token_stats
                else:
                    error_text = await response.text()
                    logger.error(f"Ошибка форматирования текста: {error_text}")
                    raise Exception(f"Ошибка форматирования текста: {response.status}")
    except Exception as e:
        logger.error(f"Ошибка при форматировании текста: {e}", exc_info=True)
        raise 