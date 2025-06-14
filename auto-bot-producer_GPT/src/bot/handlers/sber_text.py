"""
Обработчик форматирования текста через Sber GPT.
"""
import os
import logging
from telegram import Update, InputMediaPhoto
from telegram.ext import ContextTypes

from ..states import BotState, PostContext
from ..keyboards import get_moderate_keyboard
from ..decorators import check_moderation_block
from src.utils.api import format_text_with_sber
from src.config.settings import settings

logger = logging.getLogger(__name__)

@check_moderation_block
async def handle_edit_sber_text_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    state_manager,
    post_context: PostContext,
    post_id: str
) -> None:
    """Обработчик кнопки 'Текст Sber'."""
    query = update.callback_query
    await query.answer()
    
    logger.info(f"=== handle_edit_sber_text_callback: старт для поста {post_id} ===")
    
    # Получаем текущий текст поста
    current_text = post_context.original_text
    
    # Отправляем текст в Sber API
    formatted_text, token_stats = await format_text_with_sber(current_text, settings.FORMAT_PROMPT)
    
    if not formatted_text:
        logger.error(f"Ошибка при форматировании текста для поста {post_id}")
        await query.message.edit_text("❌ Ошибка при форматировании текста")
        return
    
    logger.info(f"Текст успешно отформатирован через Sber GPT для поста {post_id}")
    
    # Получаем путь к папке поста
    post_dir = os.path.join(settings.SAVE_DIR, post_id)
    if not os.path.exists(post_dir):
        logger.error(f"Папка поста не найдена: {post_dir}")
        await query.message.edit_text("❌ Ошибка: папка поста не найдена")
        return
    
    # Сохраняем новый текст в temp.txt
    temp_file = os.path.join(post_dir, "temp.txt")
    with open(temp_file, 'w', encoding='utf-8') as f:
        f.write(formatted_text)
    
    # Получаем список фото
    photos = [f for f in os.listdir(post_dir) if f.startswith("photo_") and f.endswith(".jpg")]
    photos.sort(key=lambda x: int(x.split('_')[1].split('.')[0]))
    
    if not photos:
        logger.error(f"Фотографии не найдены в папке {post_dir}")
        await query.message.edit_text("❌ Ошибка: фотографии не найдены")
        return
    
    # Формируем пути к фото
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
                        caption=formatted_text
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
    )
    logger.info("Новый пост успешно отправлен")
    
    # Обновляем контекст поста
    message_ids = [msg.message_id for msg in messages]
    post_context.original_media = message_ids
    post_context.original_text = formatted_text
    post_context.state = BotState.MODERATE_MENU
    logger.info(f"Смена состояния: EDIT_SBER_TEXT_WAIT -> MODERATE_MENU для поста {post_id}")
    state_manager.set_post_context(post_id, post_context)
    
    # Отправляем клавиатуру
    keyboard_message = await context.bot.send_message(
        chat_id=post_context.chat_id,
        text="Выберите действие для поста:",
        reply_markup=get_moderate_keyboard(post_id),
        read_timeout=20,
        write_timeout=15,
        connect_timeout=15,
        pool_timeout=15
    )
    post_context.service_messages.append(keyboard_message.message_id)
    state_manager.set_post_context(post_id, post_context)
    
    logger.info(f"=== handle_edit_sber_text_callback: завершено для поста {post_id} ===") 