"""
Обработчик удаления фото из поста.
"""
import os
import logging
from telegram import Update, InputMediaPhoto
from telegram.ext import ContextTypes
from telegram.error import TimedOut, NetworkError

from src.bot.states import BotState
from src.bot.keyboards import get_moderate_keyboard
from src.utils.logger import setup_logger

logger = setup_logger("remove_media_handler")

async def handle_remove_media_message(update: Update, context: ContextTypes.DEFAULT_TYPE, state_manager, post_context, post_id: str) -> None:
    """
    Обработчик сообщения с номерами фото для удаления.
    
    Args:
        update: Объект обновления
        context: Контекст бота
        state_manager: Менеджер состояний
        post_context: Контекст поста
        post_id: ID поста
    """
    logger.info(f"=== Начало обработки удаления фото для поста {post_id} ===")
    
    # Получаем номера фото для удаления
    text = update.message.text.strip()
    try:
        numbers = list(map(int, text.split()))
    except Exception:
        await update.message.reply_text("❌ Ошибка: введите номера фото через пробел, например: 1 3 4")
        return

    post_dir = os.path.join("saved", post_id)
    photos = [f for f in os.listdir(post_dir) if f.startswith("photo_") and f.endswith(".jpg")]
    photos.sort(key=lambda x: int(x.split('_')[1].split('.')[0]))
    
    if not photos:
        await update.message.reply_text("В этом посте нет фото для удаления.")
        return

    # Проверяем валидность номеров
    to_delete = set()
    for n in numbers:
        if 1 <= n <= len(photos):
            to_delete.add(n-1)
    
    if not to_delete:
        await update.message.reply_text("❌ Ошибка: нет корректных номеров для удаления.")
        return

    # Удаляем выбранные фото
    deleted = []
    for idx in sorted(to_delete, reverse=True):
        try:
            os.remove(os.path.join(post_dir, photos[idx]))
            deleted.append(photos[idx])
        except Exception as e:
            logger.error(f"Ошибка при удалении файла {photos[idx]}: {e}")

    # Обновляем список фото
    remaining_photos = [f for f in os.listdir(post_dir) if f.startswith("photo_") and f.endswith(".jpg")]
    remaining_photos.sort(key=lambda x: int(x.split('_')[1].split('.')[0]))

    # Переименовываем оставшиеся фото для последовательности
    for i, fname in enumerate(remaining_photos):
        correct_name = f"photo_{i+1}.jpg"
        if fname != correct_name:
            os.rename(os.path.join(post_dir, fname), os.path.join(post_dir, correct_name))

    # Удаляем старые сообщения с фото
    for message_id in post_context.original_media:
        try:
            await context.bot.delete_message(chat_id=post_context.chat_id, message_id=message_id)
        except Exception as e:
            logger.error(f"Ошибка при удалении старого сообщения {message_id}: {e}")

    for message_id in post_context.service_messages:
        try:
            await context.bot.delete_message(chat_id=post_context.chat_id, message_id=message_id)
        except Exception as e:
            logger.error(f"Ошибка при удалении служебного сообщения {message_id}: {e}")

    post_context.original_media = []
    post_context.service_messages = []

    # Если остались фото — отправляем их заново
    remaining_photos = [f for f in os.listdir(post_dir) if f.startswith("photo_") and f.endswith(".jpg")]
    remaining_photos.sort(key=lambda x: int(x.split('_')[1].split('.')[0]))

    if remaining_photos:
        media_group = []
        for i, fname in enumerate(remaining_photos):
            path = os.path.join(post_dir, fname)
            with open(path, 'rb') as photo:
                if i == 0:
                    media_group.append(InputMediaPhoto(media=photo, caption=post_context.original_text))
                else:
                    media_group.append(InputMediaPhoto(media=photo))
        messages = await context.bot.send_media_group(chat_id=post_context.chat_id, media=media_group)
        message_ids = [msg.message_id for msg in messages]
        post_context.original_media = message_ids

    # Клавиатура
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
    post_context.state = BotState.MODERATE_MENU
    state_manager.set_post_context(post_id, post_context)

    await update.message.reply_text(f"✅ Фото удалены: {' '.join(deleted) if deleted else 'ничего не удалено'}")
    logger.info(f"Фото удалены из поста {post_id}: {deleted}")
    logger.info(f"=== Завершена обработка удаления фото для поста {post_id} ===") 