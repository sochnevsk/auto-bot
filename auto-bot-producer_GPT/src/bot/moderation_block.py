"""
Модуль для управления блокировками модерации.
"""
import json
import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

MODERATION_BLOCK_FILE = "moderation_block.json"

async def check_and_set_moderation_block(post_id: str, user_id: int) -> Optional[int]:
    """
    Проверяет и устанавливает блокировку модерации для поста.
    
    Args:
        post_id: ID поста
        user_id: ID пользователя, пытающегося получить блокировку
        
    Returns:
        Optional[int]: ID пользователя, у которого есть блокировка, или None если блокировки нет
    """
    try:
        # Проверяем существование файла
        if not os.path.exists(MODERATION_BLOCK_FILE):
            logger.info(f"Файл {MODERATION_BLOCK_FILE} не существует, создаем новый")
            # Создаем новый файл с первой записью
            data = {post_id: user_id}
            with open(MODERATION_BLOCK_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Создан файл {MODERATION_BLOCK_FILE} с первой записью: {data}")
            return None

        # Читаем существующий файл
        with open(MODERATION_BLOCK_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"Прочитаны данные из {MODERATION_BLOCK_FILE}: {data}")

        # Проверяем наличие блокировки
        if post_id in data:
            blocked_user_id = data[post_id]
            logger.info(f"Пост {post_id} заблокирован пользователем {blocked_user_id}")
            return blocked_user_id

        # Если блокировки нет, устанавливаем новую
        data[post_id] = user_id
        with open(MODERATION_BLOCK_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info(f"Установлена новая блокировка для поста {post_id} пользователем {user_id}")
        return None

    except Exception as e:
        logger.error(f"Ошибка при работе с блокировками модерации: {e}", exc_info=True)
        return None

async def remove_moderation_block(post_id: str) -> None:
    """
    Удаляет блокировку модерации для поста.
    
    Args:
        post_id: ID поста
    """
    try:
        if not os.path.exists(MODERATION_BLOCK_FILE):
            logger.info(f"Файл {MODERATION_BLOCK_FILE} не существует, нечего удалять")
            return

        # Читаем существующий файл
        with open(MODERATION_BLOCK_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
            logger.info(f"Прочитаны данные из {MODERATION_BLOCK_FILE}: {data}")

        # Удаляем блокировку если она есть
        if post_id in data:
            del data[post_id]
            with open(MODERATION_BLOCK_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"Удалена блокировка для поста {post_id}")
        else:
            logger.info(f"Блокировка для поста {post_id} не найдена")

    except Exception as e:
        logger.error(f"Ошибка при удалении блокировки модерации: {e}", exc_info=True) 