"""
Обработчик редактирования текста.
"""
import os
import logging
import re
from telegram import Update, InputMediaPhoto
from telegram.ext import ContextTypes

from ..states import BotState, PostContext
from ..keyboards import get_moderate_keyboard
from ..text_processor import TextProcessor
from ..decorators import check_moderation_block
from src.utils.telegram_format import entities_to_html

logger = logging.getLogger(__name__)

@check_moderation_block
async def handle_edit_text_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    state_manager,
    post_context: PostContext,
    post_id: str
) -> None:
    """Обработчик сообщения с новым текстом."""
    logger.info(f"=== handle_edit_text_message: старт для поста {post_id} ===")
    
    # Создаем экземпляр TextProcessor
    text_processor = TextProcessor()
    
    # Получаем текст с форматированием
    html_text = entities_to_html(update.message.text, update.message.entities)
    processed_text, was_truncated = await text_processor.process_text(html_text)
    if was_truncated:
        logger.info("Текст был обрезан из-за превышения лимита")
        await update.message.reply_text("⚠️ Текст был обрезан из-за превышения лимита Telegram")
    
    # Получаем путь к папке поста
    post_dir = os.path.join(settings.SAVED_DIR, post_id)
    if not os.path.exists(post_dir):
        logger.error(f"Папка поста не найдена: {post_dir}")
        await update.message.reply_text("❌ Ошибка: папка поста не найдена")
        return
        
    # Сохраняем новый текст в temp.txt
    temp_file = os.path.join(post_dir, "temp.txt")
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(processed_text)
        logger.info(f"Новый текст сохранен в {temp_file}")
    except Exception as e:
        logger.error(f"Ошибка при сохранении temp.txt: {e}")
        await update.message.reply_text("❌ Ошибка при сохранении текста")
        return
        
    # Удаляем старые сообщения
    logger.info("Удаление старых сообщений")
    for message_id in post_context.original_media:
        try:
            await context.bot.delete_message(
                chat_id=post_context.chat_id,
                message_id=message_id
            )
        except Exception as e:
            logger.error(f"Ошибка при удалении сообщения {message_id}: {e}")
            
    # Удаляем служебные сообщения
    for message_id in post_context.service_messages:
        try:
            await context.bot.delete_message(
                chat_id=post_context.chat_id,
                message_id=message_id
            )
        except Exception as e:
            logger.error(f"Ошибка при удалении служебного сообщения {message_id}: {e}")
            
    # Очищаем списки сообщений
    post_context.original_media = []
    post_context.service_messages = []
    
    # Получаем список фотографий
    photos = sorted(
        [f for f in os.listdir(post_dir) if f.startswith("photo_") and f.endswith(".jpg")],
        key=lambda x: int(x.split("_")[1].split(".")[0])
    )
    if not photos:
        logger.error(f"Нет фотографий в папке {post_dir}")
        await update.message.reply_text("❌ Ошибка: фотографии не найдены")
        return
        
    photo_paths = [os.path.join(post_dir, photo) for photo in photos]
    logger.info(f"Найдено {len(photos)} фотографий: {photo_paths}")
    
    # Отправляем новый пост
    media_group = []
    for i, path in enumerate(photo_paths):
        with open(path, 'rb') as photo:
            if i == 0:
                media_group.append(
                    InputMediaPhoto(
                        media=photo,
                        caption=processed_text
                    )
                )
            else:
                media_group.append(
                    InputMediaPhoto(
                        media=photo
                    )
                )
                
    messages = await context.bot.send_media_group(
        chat_id=post_context.chat_id,
        media=media_group
        #parse_mode='HTML'
    )
    logger.info("Новый пост успешно отправлен")
    
    # Обновляем контекст поста
    message_ids = [msg.message_id for msg in messages]
    post_context.original_media = message_ids
    post_context.original_text = processed_text
    post_context.state = BotState.MODERATE_MENU
    logger.info(f"Смена состояния: EDIT_TEXT_WAIT -> MODERATE_MENU для поста {post_id}")
    state_manager.set_post_context(post_id, post_context)
    
    # Отправляем клавиатуру
    keyboard_message = await context.bot.send_message(
        chat_id=post_context.chat_id,
        text="Выберите действие для поста:",
        reply_markup=get_moderate_keyboard(post_id),
        read_timeout=17,
        write_timeout=12,
        connect_timeout=12,
        pool_timeout=12
    )
    post_context.service_messages.append(keyboard_message.message_id)
    state_manager.set_post_context(post_id, post_context)
    
    logger.info(f"=== handle_edit_text_message: завершено для поста {post_id} ===") 