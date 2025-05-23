import os
import asyncio
import logging
import time
from telegram import Update, InputMediaPhoto
from telegram.ext import ContextTypes
from typing import List, Dict, Optional, Set
from src.bot.decorators import check_moderation_block
from src.bot.keyboards import get_media_confirm_keyboard

# Глобальные переменные для хранения временных данных
media_group_temp: Dict[int, Dict[str, List]] = {}  # {user_id: {media_group_id: [photo, ...]}}
media_group_tasks: Dict[int, Dict[str, asyncio.Task]] = {}  # {user_id: {media_group_id: asyncio.Task}}
media_group_file_ids: Dict[int, Dict[str, Set[str]]] = {}  # {user_id: {media_group_id: {file_id, ...}}}
MEDIA_GROUP_TIMEOUT = 9.0  # Таймаут для сбора альбома

@check_moderation_block
async def handle_photo(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE,
    post_id: Optional[str] = None,
    operation_context: str = "create"  # "create" или "edit"
) -> None:
    """
    Обработчик получения фотографий.
    Поддерживает как одиночные фото, так и альбомы.
    
    Args:
        update: Объект обновления
        context: Контекст бота
        post_id: ID поста (опционально, для контекста редактирования)
        operation_context: Контекст операции ("create" или "edit")
    """
    user_id = update.message.from_user.id
    photos = update.message.photo
    
    if not photos:
        await update.message.reply_text("Ошибка: отправьте фото.")
        return
        
    media_group_id = update.message.media_group_id
    
    if media_group_id:
        # Инициализация структур для альбома
        if user_id not in media_group_temp:
            media_group_temp[user_id] = {}
            media_group_file_ids[user_id] = {}
        if user_id not in media_group_tasks:
            media_group_tasks[user_id] = {}
        if media_group_id not in media_group_temp[user_id]:
            media_group_temp[user_id][media_group_id] = []
            media_group_file_ids[user_id][media_group_id] = set()
            
        # Получаем file_id самой большой версии фото
        largest_photo = photos[-1]
        file_id = largest_photo.file_id
        
        # Проверяем, не было ли уже добавлено это фото
        if file_id not in media_group_file_ids[user_id][media_group_id]:
            media_group_temp[user_id][media_group_id].append(largest_photo)
            media_group_file_ids[user_id][media_group_id].add(file_id)
            
            # Создаем или обновляем таймер для сбора альбома
            if media_group_id in media_group_tasks[user_id]:
                try:
                    media_group_tasks[user_id][media_group_id].cancel()
                except Exception as e:
                    logging.error(f"Ошибка при отмене таймера: {e}")
                    
            async def finish_media_group():
                try:
                    await asyncio.sleep(MEDIA_GROUP_TIMEOUT)
                    await process_media_group(user_id, media_group_id, context, post_id, operation_context)
                except asyncio.CancelledError:
                    pass
                    
            media_group_tasks[user_id][media_group_id] = asyncio.create_task(finish_media_group())
    else:
        # Обработка одиночного фото
        await process_single_photo(update, context, post_id, operation_context)

@check_moderation_block
async def process_single_photo(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE,
    post_id: Optional[str] = None,
    operation_context: str = "create"
) -> None:
    """
    Обработка одиночного фото.
    
    Args:
        update: Объект обновления
        context: Контекст бота
        post_id: ID поста (опционально, для контекста редактирования)
        operation_context: Контекст операции ("create" или "edit")
    """
    user_id = update.message.from_user.id
    photo = update.message.photo[-1]  # Берем фото максимального размера
    
    try:
        # Определяем директорию для сохранения в зависимости от контекста
        if operation_context == "edit" and post_id:
            save_dir = os.path.join("saved", post_id)
        else:
            save_dir = f"media/{user_id}"
        os.makedirs(save_dir, exist_ok=True)
        
        # Сохраняем фото
        file = await photo.get_file()
        file_path = f"{save_dir}/photo_{int(time.time())}.jpg"
        await file.download_to_drive(file_path)
        
        # Отправляем подтверждение
        await update.message.reply_text(
            "Фото успешно сохранено",
            reply_markup=get_media_confirm_keyboard(file_path)
        )
        
    except Exception as e:
        logging.error(f"Ошибка при сохранении фото: {e}")
        await update.message.reply_text("Произошла ошибка при сохранении фото")

@check_moderation_block
async def process_media_group(
    user_id: int, 
    media_group_id: str, 
    context: ContextTypes.DEFAULT_TYPE,
    post_id: Optional[str] = None,
    operation_context: str = "create"
) -> None:
    """
    Обработка собранного альбома.
    
    Args:
        user_id: ID пользователя
        media_group_id: ID группы медиа
        context: Контекст бота
        post_id: ID поста (опционально, для контекста редактирования)
        operation_context: Контекст операции ("create" или "edit")
    """
    if user_id not in media_group_temp or media_group_id not in media_group_temp[user_id]:
        return
        
    album_photos = media_group_temp[user_id][media_group_id]
    saved_paths = []
    
    try:
        # Определяем директорию для сохранения в зависимости от контекста
        if operation_context == "edit" and post_id:
            save_dir = os.path.join("saved", post_id)
        else:
            save_dir = f"media/{user_id}"
        os.makedirs(save_dir, exist_ok=True)
        
        # Сохраняем все фото из альбома
        for i, photo in enumerate(album_photos):
            file = await photo.get_file()
            file_path = f"{save_dir}/photo_{int(time.time())}_{i}.jpg"
            await file.download_to_drive(file_path)
            saved_paths.append(file_path)
            
        # Отправляем подтверждение
        await context.bot.send_message(
            chat_id=user_id,
            text=f"Сохранено {len(saved_paths)} фотографий",
            reply_markup=get_media_confirm_keyboard(saved_paths)
        )
        
    except Exception as e:
        logging.error(f"Ошибка при обработке альбома: {e}")
        await context.bot.send_message(
            chat_id=user_id,
            text="Произошла ошибка при сохранении альбома"
        )
    finally:
        # Очищаем временные данные
        if user_id in media_group_temp:
            media_group_temp[user_id].pop(media_group_id, None)
            media_group_file_ids[user_id].pop(media_group_id, None)
            media_group_tasks[user_id].pop(media_group_id, None) 