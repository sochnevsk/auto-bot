"""
Основной модуль бота.
"""
import logging
import asyncio
import os
import json
from datetime import datetime
from typing import Dict, Any
from telegram import Update, InputMediaPhoto, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler
)
from telegram.error import TimedOut, NetworkError

from src.config.settings import settings
from src.utils.logger import setup_logger
from src.bot.keyboards import get_post_keyboard, get_confirm_keyboard, get_moderation_keyboard
from src.bot.storage import AsyncFileManager

# Настройка логгера
logger = setup_logger(__name__)

# Путь к файлу storage
STORAGE_PATH = "storage.json"


class Bot:
    """Основной класс бота."""

    def __init__(self):
        """Инициализация бота."""
        logger.info("Initializing bot...")
        self.application = Application.builder().token(settings.BOT_TOKEN).build()
        self._setup_handlers()
        self.check_task = None
        self.is_checking = False
        
        # Создаем storage.json если его нет
        if not os.path.exists(STORAGE_PATH):
            logger.info("Creating storage.json file")
            with open(STORAGE_PATH, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
            logger.info("storage.json created successfully")
            
        logger.info("Bot initialized successfully")

    def _setup_handlers(self) -> None:
        """Настройка обработчиков команд."""
        logger.info("Setting up command handlers...")
        
        # Обработчик команды /test
        self.application.add_handler(CommandHandler("test", self.test_command))
        logger.info("Added /test command handler")
        
        # Обработчик callback-запросов
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        logger.info("Added callback query handler")
        
        logger.info("Command handlers setup completed")

    async def is_post_sent(self, post_id: str) -> bool:
        """Проверяет, был ли пост уже отправлен."""
        async with AsyncFileManager(STORAGE_PATH) as storage:
            data = await storage.read()
            return post_id in data and data[post_id].get("status") == "sent"

    async def process_post(
            self,
            post_dir: str,
            context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Обработка одного поста.

        Args:
            post_dir: Путь к директории с постом
            context: Контекст бота

        Returns:
            bool: True если пост успешно отправлен, False в случае ошибки
        """
        try:
            post_id = os.path.basename(post_dir)
            logger.info(f"Processing post in directory: {post_dir}")

            # Проверяем, не был ли пост уже отправлен
            if await self.is_post_sent(post_id):
                logger.info(f"Post {post_id} already sent, skipping")
                return False

            # Проверяем статус готовности
            ready_file = os.path.join(post_dir, "ready.txt")
            if not os.path.exists(ready_file):
                logger.error(f"Post is not ready, no ready file found in {post_dir}")
                return False

            with open(ready_file, 'r') as f:
                status = f.read().strip()
                logger.info(f"Ready file status: {status}")

            if status != "ok":
                logger.error(f"Post is not ready, status: {status}")
                return False

            # Читаем текст поста
            text_file = os.path.join(post_dir, "text.txt")
            if not os.path.exists(text_file):
                logger.error(f"No text file found in {post_dir}")
                return False

            with open(text_file, 'r', encoding='utf-8') as f:
                post_text = f.read().strip()
                logger.info(f"Post text: {post_text[:100]}...")

            # Читаем информацию об источнике
            source_file = os.path.join(post_dir, "source.txt")
            if not os.path.exists(source_file):
                logger.error(f"No source file found in {post_dir}")
                return False

            with open(source_file, 'r', encoding='utf-8') as f:
                source_info = f.read().strip()
                logger.info(f"Source info: {source_info}")

            # Формируем полный текст поста с информацией об источнике
            full_text = f"{post_text}\n\n{source_info}"

            # Получаем список фотографий
            photos = sorted(
                [f for f in os.listdir(post_dir) if f.startswith("photo_") and f.endswith(".jpg")],
                key=lambda x: int(x.split("_")[1].split(".")[0])
            )
            if not photos:
                logger.error(f"No photos found in {post_dir}")
                return False

            photo_paths = [os.path.join(post_dir, photo) for photo in photos]
            logger.info(f"Found {len(photos)} photos: {photo_paths}")

            # Отправляем альбом с фотографиями и текстом
            logger.info("Sending photo album with caption")
            try:
                media_group = []
                for i, path in enumerate(photo_paths):
                    # Добавляем caption только к первой фотографии
                    if i == 0:
                        media_group.append(
                            InputMediaPhoto(
                                media=open(path, 'rb'),
                                caption=full_text
                            )
                        )
                    else:
                        media_group.append(
                            InputMediaPhoto(
                                media=open(path, 'rb')
                            )
                        )

                messages = await context.bot.send_media_group(
                    chat_id=settings.MODERATOR_GROUP_ID,
                    media=media_group,
                    read_timeout=30,
                    write_timeout=30,
                    connect_timeout=30,
                    pool_timeout=30
                )
                logger.info("Photo album sent successfully")

                # Отправляем клавиатуру с действиями
                logger.info("Sending keyboard with actions")
                keyboard_message = await context.bot.send_message(
                    chat_id=settings.MODERATOR_GROUP_ID,
                    text=f"Выберите действие для поста {post_id}:",
                    reply_markup=get_post_keyboard(post_id),
                    read_timeout=30,
                    write_timeout=30,
                    connect_timeout=30,
                    pool_timeout=30
                )
                logger.info("Keyboard sent successfully")

                # Сохраняем информацию о посте
                message_ids = [msg.message_id for msg in messages]
                message_ids.append(keyboard_message.message_id)

                post_info = {
                    "id": post_id,
                    "dir": post_dir,
                    "datetime": datetime.now().isoformat(),
                    "status": "sent",
                    "text": full_text,
                    "source": source_info,
                    "photos": photo_paths,
                    "message_ids": message_ids,
                    "keyboard_message_id": keyboard_message.message_id,
                    "chat_id": settings.MODERATOR_GROUP_ID
                }

                # Логируем отправку поста
                logger.info(f"Post from {post_dir} sent successfully")
                logger.info(f"Logging post {post_id} as sent")

                async with AsyncFileManager(STORAGE_PATH) as storage:
                    data = await storage.read()
                    logger.info(f"Current storage data: {data}")
                    data[post_id] = post_info
                    logger.info(f"Adding post info to storage: {post_info}")
                    await storage.write(data)
                    logger.info(f"Storage updated successfully for post {post_id}")

                logger.info(f"Post {post_id} logged as sent")
                return True

            except Exception as e:
                logger.error(f"Network error sending post from {post_dir}: {e}")
                raise

        except Exception as e:
            logger.error(f"Error processing post from {post_dir}: {e}")
            raise

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обработчик callback-запросов от inline кнопок.

        Args:
            update: Объект обновления
            context: Контекст бота
        """
        logger.info("Received callback query")
        query = update.callback_query
        await query.answer()
        logger.info(f"Callback query data: {query.data}")

        # Получаем данные из callback
        data = query.data
        # Разделяем на action и post_id, учитывая что post_id может содержать пробелы
        parts = data.split('_', 1)  # Разделяем только по первому '_'
        if len(parts) != 2:
            logger.error(f"Invalid callback data format: {data}")
            return
            
        action, post_id = parts
        logger.info(f"Parsed action: {action}, post_id: {post_id}")

        # Проверяем права пользователя
        user_id = update.effective_user.id
        logger.info(f"Checking permissions for user {user_id}")
        logger.info(f"Available moderator IDs: {settings.moderator_ids}")

        if user_id not in settings.moderator_ids:
            logger.warning(f"User {user_id} is not a moderator")
            await query.message.reply_text(
                "⛔️ У вас нет прав для выполнения этой команды."
            )
            return

        logger.info(f"User {user_id} is a moderator, processing action: {action}")

        if action == "delete":
            # Показываем клавиатуру подтверждения удаления
            logger.info("Showing delete confirmation keyboard")
            await query.message.edit_text(
                text=f"Удалить пост {post_id}?",
                reply_markup=get_confirm_keyboard(post_id)
            )
            logger.info(f"Delete confirmation keyboard shown for post {post_id}")

        elif action == "confirm":
            # Удаляем пост и убираем кнопки
            logger.info(f"Confirming deletion of post {post_id}")
            post_dir = os.path.join("saved", post_id)
            async with AsyncFileManager(STORAGE_PATH) as storage:
                data = await storage.read()
                post_info = data.get(post_id, {})
                message_ids = post_info.get("message_ids", [])
                chat_id = post_info.get("chat_id")
                
                # Удаляем все сообщения (фото, альбом, служебные, кнопки)
                if message_ids and chat_id:
                    for msg_id in message_ids:
                        try:
                            await context.bot.delete_message(
                                chat_id=chat_id,
                                message_id=msg_id
                            )
                            logger.info(f"Deleted message {msg_id}")
                        except Exception as e:
                            logger.error(f"Error deleting message {msg_id}: {e}")

            # Удаляем файлы поста
            if os.path.exists(post_dir):
                for file in os.listdir(post_dir):
                    os.remove(os.path.join(post_dir, file))
                os.rmdir(post_dir)
                logger.info(f"Post directory {post_dir} deleted")

            # Удаляем информацию о посте из storage
            async with AsyncFileManager(STORAGE_PATH) as storage:
                data = await storage.read()
                if post_id in data:
                    del data[post_id]
                    await storage.write(data)
                    logger.info(f"Post {post_id} deleted from storage")

            # Отправляем подтверждение
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"✅ Пост {post_id} и все связанные сообщения удалены"
            )

        elif action == "cancel":
            # Возвращаем основную клавиатуру
            logger.info("Cancelling action and returning to main keyboard")
            await query.message.edit_text(
                text=f"Выберите действие для поста {post_id}:",
                reply_markup=get_post_keyboard(post_id)
            )
            logger.info(f"Returned to main keyboard for post {post_id}")

        elif action == "publish":
            # TODO: Реализовать публикацию поста
            logger.info("Publish action received")
            await query.message.edit_text(
                text=f"Пост {post_id} опубликован"
            )
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"✅ Пост {post_id} опубликован"
            )

        elif action == "edit":
            # TODO: Реализовать редактирование поста
            logger.info("Edit action received")
            await query.message.edit_text(
                text=f"Редактирование поста {post_id} (заглушка)"
            )
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text=f"✏️ Редактирование поста {post_id} (заглушка)"
            )

        else:
            logger.warning(f"Unknown action received: {action}")

    async def check_posts(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Периодическая проверка постов.

        Args:
            context: Контекст бота
        """
        if self.is_checking:
            logger.info("Previous check is still running, skipping")
            return

        self.is_checking = True
        try:
            logger.info("Starting periodic post check")

            # Путь к папке с постами
            saved_dir = "saved"
            if not os.path.exists(saved_dir):
                logger.error(f"Saved directory not found: {saved_dir}")
                return

            # Получаем список всех подпапок
            post_dirs = []
            for item in os.listdir(saved_dir):
                item_path = os.path.join(saved_dir, item)
                if os.path.isdir(item_path) and item.startswith('post_'):
                    post_dirs.append(item_path)

            if not post_dirs:
                logger.info("No post directories found")
                return

            logger.info(f"Found {len(post_dirs)} post directories")

            # Обрабатываем каждый пост
            success_count = 0
            error_count = 0

            for post_dir in sorted(post_dirs):
                if await self.process_post(post_dir, context):
                    success_count += 1
                else:
                    error_count += 1

        except Exception as e:
            logger.error(f"Error in periodic check: {e}", exc_info=True)
        finally:
            self.is_checking = False

    async def test_command(
            self,
            update: Update,
            context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обработчик команды /test.

        Args:
            update: Объект обновления
            context: Контекст бота
        """
        logger.info(
            f"Received /test command from user {update.effective_user.id}")
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

            logger.info(f"User {user_id} is a moderator, checking posts")

            # Путь к папке с постами
            saved_dir = "saved"
            if not os.path.exists(saved_dir):
                logger.error(f"Saved directory not found: {saved_dir}")
                await update.message.reply_text("❌ Папка saved не найдена")
                return

            # Получаем список всех подпапок
            post_dirs = []
            for item in os.listdir(saved_dir):
                item_path = os.path.join(saved_dir, item)
                if os.path.isdir(item_path) and item.startswith('post_'):
                    post_dirs.append(item_path)

            if not post_dirs:
                logger.info("No post directories found")
                await update.message.reply_text("ℹ️ Нет папок с постами")
                return

            logger.info(f"Found {len(post_dirs)} post directories")

            # Обрабатываем каждый пост
            success_count = 0
            error_count = 0

            for post_dir in sorted(post_dirs):
                if await self.process_post(post_dir, context):
                    success_count += 1
                else:
                    error_count += 1

            # Отправляем итоговый отчет
            try:
                if success_count > 0:
                    await update.message.reply_text(
                        f"✅ Обработка завершена\n\n"
                        f"✅ Успешно отправлено: {success_count}\n"
                        f"❌ Ошибок: {error_count}"
                    )
                else:
                    await update.message.reply_text(
                        f"❌ Не удалось отправить ни одного поста\n\n"
                        f"❌ Ошибок: {error_count}"
                    )
            except (TimedOut, NetworkError) as e:
                logger.error(
                    f"Network error sending report: {e}",
                    exc_info=True)
            except Exception as e:
                logger.error(f"Error sending report: {e}", exc_info=True)

            # Запускаем периодическую проверку, если она еще не запущена
            if self.check_task is None or self.check_task.done():
                logger.info("Starting periodic post check task")
                self.check_task = asyncio.create_task(
                    self._run_periodic_check(context))
                try:
                    await update.message.reply_text("🔄 Запущена периодическая проверка постов")
                except (TimedOut, NetworkError) as e:
                    logger.error(
                        f"Network error sending message: {e}",
                        exc_info=True)
                except Exception as e:
                    logger.error(f"Error sending message: {e}", exc_info=True)

        except Exception as e:
            logger.error(f"Error in test_command: {e}", exc_info=True)
            try:
                await update.message.reply_text(
                    "❌ Произошла ошибка при выполнении команды."
                )
            except (TimedOut, NetworkError) as e:
                logger.error(
                    f"Network error sending error message: {e}",
                    exc_info=True)
            except Exception as e:
                logger.error(
                    f"Error sending error message: {e}",
                    exc_info=True)

    async def _run_periodic_check(
            self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Запуск периодической проверки.

        Args:
            context: Контекст бота
        """
        try:
            while True:
                await self.check_posts(context)
                await asyncio.sleep(20)  # Проверяем каждую минуту
        except asyncio.CancelledError:
            logger.info("Periodic check task cancelled")
        except Exception as e:
            logger.error(f"Error in periodic check task: {e}", exc_info=True)


def main():
    """Основная функция."""
    logger.info("Starting main function")

    # Создаем экземпляр бота
    bot = Bot()

    # Запускаем бота
    logger.info("Starting bot...")
    bot.application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    try:
        logger.info("Starting bot application")
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
