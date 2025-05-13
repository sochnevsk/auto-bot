"""
Основной модуль бота.
"""
import logging
import asyncio
import os
import json
from datetime import datetime
from typing import Dict, Any
from telegram import Update, InputMediaPhoto
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes
)
from telegram.error import TimedOut, NetworkError

from src.config.settings import settings
from src.utils.logger import setup_logger

# Настройка логгера
logger = setup_logger(__name__)

STORAGE_PATH = "storage.json"


class AsyncFileManager:
    """
    Асинхронный файловый менеджер с блокировкой для работы с storage.json
    """

    def __init__(self, path: str):
        self.path = path
        self.lock_path = f"{path}.lock"

    async def __aenter__(self):
        # Ждем, пока lock-файл не исчезнет
        while os.path.exists(self.lock_path):
            await asyncio.sleep(0.05)
        # Создаем lock-файл
        with open(self.lock_path, 'w') as f:
            f.write('lock')
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if os.path.exists(self.lock_path):
            os.remove(self.lock_path)

    async def read(self) -> Dict[str, Any]:
        if not os.path.exists(self.path):
            return {}
        with open(self.path, 'r', encoding='utf-8') as f:
            return json.load(f)

    async def write(self, data: Dict[str, Any]):
        with open(self.path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


class Bot:
    """Основной класс бота."""

    def __init__(self):
        """Инициализация бота."""
        logger.info("Initializing bot...")
        self.application = Application.builder().token(settings.BOT_TOKEN).build()
        self._setup_handlers()
        self.check_task = None
        self.is_checking = False
        logger.info("Bot initialized successfully")

    def _setup_handlers(self) -> None:
        """Настройка обработчиков."""
        logger.info("Setting up command handlers...")
        self.application.add_handler(CommandHandler("test", self.test_command))
        logger.info("Command handlers setup completed")

    async def is_post_sent(self, post_id: str) -> bool:
        async with AsyncFileManager(STORAGE_PATH) as storage:
            data = await storage.read()
            return post_id in data and data[post_id].get("status") == "sent"

    async def log_post(self, post_id: str, info: Dict[str, Any]):
        async with AsyncFileManager(STORAGE_PATH) as storage:
            data = await storage.read()
            data[post_id] = info
            await storage.write(data)

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

            # Проверяем статус готовности
            ready_file = os.path.join(post_dir, "ready.txt")
            if not os.path.exists(ready_file):
                logger.error(f"Ready file not found: {ready_file}")
                return False

            with open(ready_file, 'r') as f:
                status = f.read().strip()

            if status != "ok":
                logger.error(f"Post is not ready, status: {status}")
                return False

            # Проверяем, не был ли пост уже отправлен
            if await self.is_post_sent(post_id):
                logger.info(f"Post {post_id} already sent, skipping")
                return False

            # Читаем текст поста
            text_file = os.path.join(post_dir, "text.txt")
            if not os.path.exists(text_file):
                logger.error(f"Text file not found: {text_file}")
                return False

            with open(text_file, 'r', encoding='utf-8') as f:
                post_text = f.read().strip()

            # Читаем информацию об источнике
            source_file = os.path.join(post_dir, "source.txt")
            if not os.path.exists(source_file):
                logger.error(f"Source file not found: {source_file}")
                return False

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
                return False

            logger.info(f"Found {len(photos)} photos")

            # Формируем данные для storage
            post_info = {
                "id": post_id,
                "dir": post_dir,
                "datetime": datetime.now().isoformat(),
                "status": "sent",
                "text": post_text,
                "source": source_info,
                "photos": photos
            }

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
                            read_timeout=60,
                            write_timeout=60,
                            connect_timeout=60,
                            pool_timeout=60
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
                        read_timeout=60,
                        write_timeout=60,
                        connect_timeout=60,
                        pool_timeout=60
                    )

                logger.info(f"Post from {post_dir} sent successfully")
                await self.log_post(post_id, post_info)
                return True

            except (TimedOut, NetworkError) as e:
                logger.error(
                    f"Network error sending post from {post_dir}: {e}",
                    exc_info=True)
                return False
            except Exception as e:
                logger.error(
                    f"Error sending post from {post_dir}: {e}",
                    exc_info=True)
                return False

        except Exception as e:
            logger.error(
                f"Error processing post from {post_dir}: {e}",
                exc_info=True)
            return False

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

            # Отправляем итоговый отчет в группу модераторов
            try:
                if success_count > 0:
                    await context.bot.send_message(
                        chat_id=settings.MODERATOR_GROUP_ID,
                        text=f"✅ Периодическая проверка завершена\n\n"
                             f"✅ Успешно отправлено: {success_count}\n"
                             f"❌ Ошибок: {error_count}",
                        read_timeout=60,
                        write_timeout=60,
                        connect_timeout=60,
                        pool_timeout=60
                    )
                elif error_count > 0:
                    await context.bot.send_message(
                        chat_id=settings.MODERATOR_GROUP_ID,
                        text=f"❌ Периодическая проверка завершена с ошибками\n\n"
                             f"❌ Ошибок: {error_count}",
                        read_timeout=60,
                        write_timeout=60,
                        connect_timeout=60,
                        pool_timeout=60
                    )
            except (TimedOut, NetworkError) as e:
                logger.error(
                    f"Network error sending report: {e}",
                    exc_info=True)
            except Exception as e:
                logger.error(f"Error sending report: {e}", exc_info=True)

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
                await asyncio.sleep(60)  # Проверяем каждую минуту
        except asyncio.CancelledError:
            logger.info("Periodic check task cancelled")
        except Exception as e:
            logger.error(f"Error in periodic check task: {e}", exc_info=True)


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
