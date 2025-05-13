"""
Основной модуль бота.
"""
import logging
import asyncio
import os
from telegram import Update, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes
)

from src.config.settings import settings
from src.utils.logger import setup_logger

# Настройка логгера
logger = setup_logger(__name__)

class Bot:
    """Основной класс бота."""
    
    def __init__(self):
        """Инициализация бота."""
        logger.info("Initializing bot...")
        self.application = Application.builder().token(settings.BOT_TOKEN).build()
        self._setup_handlers()
        logger.info("Bot initialized successfully")
    
    def _setup_handlers(self) -> None:
        """Настройка обработчиков."""
        logger.info("Setting up command handlers...")
        self.application.add_handler(CommandHandler("test", self.test_command))
        logger.info("Command handlers setup completed")
    
    async def test_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обработчик команды /test.
        
        Args:
            update: Объект обновления
            context: Контекст бота
        """
        logger.info(f"Received /test command from user {update.effective_user.id}")
        try:
            # Проверяем, что пользователь - модератор
            user_id = update.effective_user.id
            logger.info(f"Checking if user {user_id} is moderator")
            logger.info(f"Available moderator IDs: {settings.moderator_ids}")
            
            if user_id not in settings.moderator_ids:
                logger.warning(f"User {user_id} is not a moderator")
                await update.message.reply_text(
                    "⛔️ У вас нет прав для выполнения этой команды."
                )
                return
            
            logger.info(f"User {user_id} is a moderator, preparing post")
            
            # Путь к папке с постом
            post_dir = "saved/post_20250512_044938"
            
            # Проверяем статус готовности
            ready_file = os.path.join(post_dir, "ready.txt")
            if not os.path.exists(ready_file):
                logger.error(f"Ready file not found: {ready_file}")
                await update.message.reply_text("❌ Файл ready.txt не найден")
                return
                
            with open(ready_file, 'r') as f:
                status = f.read().strip()
                
            if status != "ok":
                logger.error(f"Post is not ready, status: {status}")
                await update.message.reply_text("❌ Пост не готов к публикации")
                return
            
            # Читаем текст поста
            text_file = os.path.join(post_dir, "text.txt")
            if not os.path.exists(text_file):
                logger.error(f"Text file not found: {text_file}")
                await update.message.reply_text("❌ Файл text.txt не найден")
                return
                
            with open(text_file, 'r', encoding='utf-8') as f:
                post_text = f.read().strip()
            
            # Читаем информацию об источнике
            source_file = os.path.join(post_dir, "source.txt")
            if not os.path.exists(source_file):
                logger.error(f"Source file not found: {source_file}")
                await update.message.reply_text("❌ Файл source.txt не найден")
                return
                
            with open(source_file, 'r', encoding='utf-8') as f:
                source_info = f.read().strip()
            
            # Формируем полный текст поста
            full_text = f"{post_text}\n\n{source_info}"
            
            # Собираем все фотографии
            photos = []
            for file in sorted(os.listdir(post_dir)):
                if file.startswith('photo_') and file.endswith('.jpg'):
                    photos.append(os.path.join(post_dir, file))
            
            if not photos:
                logger.error("No photos found in post directory")
                await update.message.reply_text("❌ Фотографии не найдены")
                return
            
            logger.info(f"Found {len(photos)} photos")
            
            # Отправляем пост в группу модераторов
            try:
                if len(photos) == 1:
                    # Если одна фотография, отправляем как одиночное фото
                    logger.info("Sending single photo")
                    with open(photos[0], 'rb') as photo:
                        await context.bot.send_photo(
                            chat_id=settings.MODERATOR_GROUP_ID,
                            photo=photo,
                            caption=full_text,
                            read_timeout=30,
                            write_timeout=30,
                            connect_timeout=30,
                            pool_timeout=30
                        )
                else:
                    # Если несколько фотографий, отправляем как альбом
                    logger.info("Sending photo album")
                    media_group = []
                    for i, photo_path in enumerate(photos):
                        with open(photo_path, 'rb') as photo:
                            # Добавляем caption только к первой фотографии
                            media_group.append(
                                InputMediaPhoto(
                                    photo,
                                    caption=full_text if i == 0 else None
                                )
                            )
                    
                    await context.bot.send_media_group(
                        chat_id=settings.MODERATOR_GROUP_ID,
                        media=media_group,
                        read_timeout=30,
                        write_timeout=30,
                        connect_timeout=30,
                        pool_timeout=30
                    )
                
                logger.info("Post sent successfully to moderator group")
                await update.message.reply_text("✅ Пост успешно отправлен в группу модераторов")
                
            except Exception as e:
                logger.error(f"Error sending post: {e}", exc_info=True)
                await update.message.reply_text("❌ Ошибка при отправке поста")
            
        except Exception as e:
            logger.error(f"Error in test_command: {e}", exc_info=True)
            await update.message.reply_text(
                "❌ Произошла ошибка при выполнении команды."
            )

def main():
    """Основная функция."""
    logger.info("Starting main function")
    
    # Создаем и запускаем бота
    application = Application.builder().token(settings.BOT_TOKEN).build()
    
    # Добавляем обработчики
    application.add_handler(CommandHandler("test", Bot().test_command))
    
    # Запускаем бота
    logger.info("Starting bot...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    try:
        logger.info("Starting bot application")
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True) 