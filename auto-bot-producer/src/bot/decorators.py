"""
Модуль с декораторами для бота.
"""
import logging
import functools
from typing import Callable, Any
from telegram import Update
from telegram.ext import ContextTypes

from src.bot.moderation_block import check_and_set_moderation_block

logger = logging.getLogger(__name__)

def check_moderation_block(func: Callable) -> Callable:
    """
    Декоратор для проверки блокировки модерации перед выполнением действия.
    
    Args:
        func: Функция-обработчик, которую нужно обернуть
        
    Returns:
        Callable: Обернутая функция с проверкой блокировки
    """
    @functools.wraps(func)
    async def wrapper(self, update: Update, context: ContextTypes.DEFAULT_TYPE, *args: Any, **kwargs: Any) -> None:
        """
        Обертка для функции-обработчика.
        
        Args:
            self: Экземпляр класса бота
            update: Объект обновления
            context: Контекст бота
            *args: Дополнительные позиционные аргументы
            **kwargs: Дополнительные именованные аргументы
        """
        query = update.callback_query
        if not query:
            logger.error("Callback query не найден")
            return await func(self, update, context, *args, **kwargs)
            
        # Получаем post_id из callback_data
        callback_data = query.data
        logger.info(f"Проверка блокировки для callback_data: {callback_data}")
        
        # Извлекаем post_id в зависимости от формата callback_data
        post_id = None
        if callback_data.startswith("moderate_"):
            post_id = callback_data.replace("moderate_", "")
        elif callback_data.startswith("delete_"):
            post_id = callback_data.replace("delete_", "")
        elif callback_data.startswith("publish_post_"):
            post_id = callback_data.replace("publish_post_", "")
        elif callback_data.startswith("edit_"):
            post_id = callback_data.replace("edit_", "")
        elif callback_data.startswith("edittext_"):
            post_id = callback_data.replace("edittext_", "")
        elif callback_data.startswith("editmedia_"):
            post_id = callback_data.replace("editmedia_", "")
        elif callback_data.startswith("addmedia_"):
            post_id = callback_data.replace("addmedia_", "")
        elif callback_data.startswith("removemedia_"):
            post_id = callback_data.replace("removemedia_", "")
            
        if not post_id:
            logger.error(f"Не удалось извлечь post_id из callback_data: {callback_data}")
            return await func(self, update, context, *args, **kwargs)
            
        # Проверяем блокировку
        blocked_user_id = await check_and_set_moderation_block(post_id, query.from_user.id)
        if blocked_user_id is not None and blocked_user_id != query.from_user.id:
            logger.warning(f"Пост {post_id} уже заблокирован пользователем {blocked_user_id}")
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"⚠️ Этот пост уже модерируется другим пользователем (ID: {blocked_user_id})"
            )
            return
            
        # Если блокировки нет или пост заблокирован текущим пользователем,
        # выполняем оригинальную функцию
        return await func(self, update, context, *args, **kwargs)
        
    return wrapper 