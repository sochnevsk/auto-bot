"""
Обработчик публикации поста.
"""
import os
import logging
from telegram import Update, InputMediaPhoto
from telegram.ext import ContextTypes

from ..states import BotState, PostContext
from ..text_processor import TextProcessor

logger = logging.getLogger(__name__)

async def handle_publish_callback(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    state_manager,
    post_context: PostContext,
    post_id: str
) -> None:
    """Обработчик публикации поста."""
    logger.info(f"=== handle_publish_callback: старт для поста {post_id} ===")
    
    # Создаем экземпляр TextProcessor
    text_processor = TextProcessor()
    
    # Получаем путь к папке поста
    post_dir = os.path.join(settings.SAVED_DIR, post_id)
    if not os.path.exists(post_dir):
        logger.error(f"Папка поста не найдена: {post_dir}")
        await update.message.reply_text("❌ Ошибка: папка поста не найдена")
        return
        
    # Читаем текст поста
    text_file = os.path.join(post_dir, "text.txt")
    if not os.path.exists(text_file):
        logger.error(f"Файл text.txt не найден в {post_dir}")
        await update.message.reply_text("❌ Ошибка: файл text.txt не найден")
        return
        
    with open(text_file, 'r', encoding='utf-8') as f:
        post_text = f.read().strip()
        logger.info(f"Текст поста для публикации: {post_text[:100]}...")
        
    # Читаем текст закрытого поста
    close_text = post_text
    text_close_file = os.path.join(post_dir, "text_close.txt")
    if os.path.exists(text_close_file):
        with open(text_close_file, 'r', encoding='utf-8') as f:
            close_text = f.read()
    else:
        logger.error(f"No close_text.txt file found in {post_dir}")
        
    # Читаем информацию об источнике
    source_file = os.path.join(post_dir, "source.txt")
    if os.path.exists(source_file):
        with open(source_file, 'r', encoding='utf-8') as f:
            close_text += "\n\n" + f.read()
    else:
        logger.error(f"No source.txt file found in {post_dir}")
        
    # Обрабатываем текст для публикации
    processed_text, was_truncated = await text_processor.process_text(post_text, is_channel=True)
    if was_truncated:
        logger.info("Текст был обрезан из-за превышения лимита")
        
    # Обрабатываем текст для закрытого канала
    processed_close_text, was_truncated = await text_processor.process_text(close_text, is_channel=True)
    if was_truncated:
        logger.info("Текст для закрытого канала был обрезан из-за превышения лимита")
        
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
    
    # Формируем медиа-группу
    media_group = []
    private_first_media_photo = None
    for i, path in enumerate(photo_paths):
        try:
            # Добавляем caption только к первой фотографии
            if i == 0:
                private_first_media_photo = InputMediaPhoto(
                    media=open(path, 'rb'),
                    caption=processed_close_text
                )
                media_group.append(
                    InputMediaPhoto(
                        media=open(path, 'rb'),
                        caption=processed_text
                    )
                )
            else:
                media_group.append(
                    InputMediaPhoto(
                        media=open(path, 'rb')
                    )
                )
        except Exception as e:
            logger.error(f"Ошибка при добавлении фото {path}: {e}", exc_info=True)
            await update.message.reply_text("❌ Ошибка при формировании медиа-группы")
            return
            
    # Публикуем в открытый канал
    logger.info("Публикация в открытый канал")
    try:
        await context.bot.send_media_group(
            chat_id=settings.PUBLIC_CHANNEL_ID,
            media=media_group,
            read_timeout=30,
            write_timeout=30,
            connect_timeout=30,
            pool_timeout=30
        )
        logger.info("Пост успешно опубликован в открытый канал")
    except Exception as e:
        logger.error(f"Ошибка при публикации в открытый канал: {e}", exc_info=True)
        await update.message.reply_text("❌ Ошибка при публикации в открытый канал")
        return
        
    # Публикуем в закрытый канал
    logger.info("Публикация в закрытый канал")
    try:
        # Формируем медиа-группу для закрытого канала
        private_media_group = []
        for i, path in enumerate(photo_paths):
            if i == 0:
                private_media_group.append(private_first_media_photo)
            else:
                private_media_group.append(
                    InputMediaPhoto(
                        media=open(path, 'rb')
                    )
                )
                
        await context.bot.send_media_group(
            chat_id=settings.PRIVATE_CHANNEL_ID,
            media=private_media_group,
            read_timeout=30,
            write_timeout=30,
            connect_timeout=30,
            pool_timeout=30
        )
        logger.info("Пост успешно опубликован в закрытый канал")
    except Exception as e:
        logger.error(f"Ошибка при публикации в закрытый канал: {e}", exc_info=True)
        await update.message.reply_text("❌ Ошибка при публикации в закрытый канал")
        return
        
    # Удаляем пост из модерации
    logger.info("Удаление поста из модерации")
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
            
    # Очищаем контекст поста
    state_manager.remove_post_context(post_id)
    logger.info(f"Контекст поста {post_id} удален")
    
    # Отправляем сообщение об успешной публикации
    await update.message.reply_text("✅ Пост успешно опубликован в оба канала")
    
    logger.info(f"=== handle_publish_callback: завершено для поста {post_id} ===") 