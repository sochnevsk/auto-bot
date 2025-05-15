"""
Основной модуль бота.
"""
import logging
import asyncio
import os
import json
from datetime import datetime
from typing import Dict, Any
from telegram import Update, InputMediaPhoto, InlineKeyboardMarkup, CallbackQuery
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from telegram.error import TimedOut, NetworkError
import time

from src.config.settings import settings
from src.utils.logger import setup_logger
from src.bot.keyboards import (
    get_post_keyboard,
    get_edit_keyboard,
    get_media_edit_keyboard,
    get_moderate_keyboard
)
from src.bot.storage import AsyncFileManager
from src.bot.states import BotState, StateManager, PostContext
from src.bot.handlers.callback import handle_media_callback

# Настройка логгера
logger = setup_logger("bot")

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
        self.state_manager = StateManager()
        
        # Создаем storage.json если его нет
        if not os.path.exists(STORAGE_PATH):
            logger.info("Creating storage.json file")
            with open(STORAGE_PATH, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
            logger.info("storage.json created successfully")
            
        logger.info("Bot initialized successfully")

    def _setup_handlers(self) -> None:
        """Настройка обработчиков команд."""
        logger.debug("Setting up command handlers...")
        
        # Обработчик команды /test
        self.application.add_handler(CommandHandler("test", self.test_command))
        logger.debug("Added /test command handler")
        
        # Обработчик callback-запросов для удаления
        self.application.add_handler(CallbackQueryHandler(
            self.handle_delete_callback,
            pattern=r"^delete_"
        ))
        logger.debug("Added delete callback handler")
        
        # Обработчик callback-запросов для модерации
        self.application.add_handler(CallbackQueryHandler(
            self.handle_moderate_callback,
            pattern=r"^moderate_"
        ))
        logger.debug("Added moderate callback handler")
        
        # Обработчик callback-запросов для публикации
        self.application.add_handler(CallbackQueryHandler(
            self.handle_publish_callback,
            pattern=r"^publish_"
        ))
        logger.debug("Added publish callback handler")
        
        # Обработчик текстовых сообщений
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        logger.debug("Added text message handler")
        
        # Обработчик фотографий
        self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_message))
        logger.debug("Added photo message handler")
        
        # Обработчик документов
        self.application.add_handler(MessageHandler(filters.Document.IMAGE, self.handle_message))
        logger.debug("Added document message handler")
        
        logger.debug("Command handlers setup completed")

    async def is_post_sent(self, post_id: str) -> bool:
        """Проверяет, был ли пост уже отправлен."""
        async with AsyncFileManager(STORAGE_PATH) as storage:
            data = await storage.read()
            return post_id in data and data[post_id].get("status") == "sent"

    async def process_post(self, post_dir: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Обработка одного поста."""
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
            full_text = f"{post_text}"

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
                    text=f"Выберите действие для поста \n{source_info}:",
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
                
                logger.info(f"Message IDs from media group: {[msg.message_id for msg in messages]}")
                logger.info(f"Keyboard message ID: {keyboard_message.message_id}")
                logger.info(f"All message IDs: {message_ids}")

                # Создаем контекст поста
                post_context = PostContext(
                    post_id=post_id,
                    chat_id=settings.MODERATOR_GROUP_ID,
                    message_id=messages[0].message_id,
                    state=BotState.POST_VIEW,
                    original_text=full_text,
                    original_media=message_ids[:-1]  # Все ID кроме последнего (клавиатуры)
                )
                logger.info(f"Created post context: {post_context}")
                self.state_manager.set_post_context(post_id, post_context)

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

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработчик сообщений."""
        logger.info("=== Начало обработки сообщения ===")
        logger.info(f"Message ID: {update.message.message_id}")
        logger.info(f"Chat ID: {update.message.chat_id}")
        logger.info(f"User ID: {update.message.from_user.id}")
        logger.info(f"User name: {update.message.from_user.full_name}")
        
        # Получаем контекст поста из состояния
        post_context = None
        for pid, ctx in self.state_manager._post_contexts.items():
            if ctx.chat_id == update.message.chat_id:
                post_context = ctx
                logger.info(f"Найден контекст поста: {pid}")
                break
        
        if not post_context:
            logger.info("Контекст поста не найден")
            return
        
        logger.info(f"Текущее состояние поста: {post_context.state}")
        logger.info(f"Текущий контекст поста: {post_context}")
        
        logger.info("=== Завершение обработки сообщения ===")

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
            logger.info(f"Available moderator ID: {settings.MODERATOR_IDS}")

            if user_id != settings.MODERATOR_IDS:
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

    async def handle_delete_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обработчик callback-запросов для удаления поста.
        
        Args:
            update: Объект обновления
            context: Контекст бота
        """
        query = update.callback_query
        await query.answer()
        
        logger.info("=== Начало обработки callback-запроса на удаление ===")
        logger.info(f"Callback query: {query.data}")
        logger.info(f"Message ID: {query.message.message_id}")
        logger.info(f"Chat ID: {query.message.chat_id}")
        
        try:
            # Получаем post_id из callback_data
            callback_data = query.data
            logger.info(f"Получен callback_data: {callback_data}")
            
            # Проверяем формат callback_data
            if not callback_data.startswith("delete_"):
                logger.error(f"Неверный формат callback_data: {callback_data}")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Неверный формат данных"
                )
                return
                
            post_id = callback_data.replace("delete_", "")
            logger.info(f"Извлечен post_id: {post_id}")
            
            if not post_id:
                logger.error("post_id пустой")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Не удалось определить ID поста"
                )
                return
            
            # Получаем контекст поста
            post_context = self.state_manager.get_post_context(post_id)
            logger.info(f"Контекст поста из памяти: {post_context}")
            
            if not post_context:
                logger.info(f"Контекст поста {post_id} не найден в памяти, пытаемся восстановить из storage")
                async with AsyncFileManager(STORAGE_PATH) as storage:
                    storage_data = await storage.read()
                    logger.info(f"Данные из storage: {storage_data}")
                    
                    if post_id in storage_data:
                        post_info = storage_data[post_id]
                        logger.info(f"Найдена информация о посте: {post_info}")
                        
                        # Получаем все message_ids из storage
                        message_ids = post_info.get('message_ids', [])
                        logger.info(f"Получены message_ids из storage: {message_ids}")
                        
                        if not message_ids:
                            logger.error("message_ids не найдены в storage")
                            await context.bot.send_message(
                                chat_id=query.message.chat_id,
                                text="❌ Не удалось найти сообщения поста"
                            )
                            return
                        
                        post_context = PostContext(
                            post_id=post_id,
                            chat_id=post_info['chat_id'],
                            message_id=message_ids[0],  # ID первого сообщения с фото
                            state=BotState.POST_VIEW,
                            original_text=post_info['text'],
                            original_media=message_ids[:-1]  # Все ID кроме последнего (клавиатуры)
                        )
                        self.state_manager.set_post_context(post_id, post_context)
                        logger.info(f"Контекст поста {post_id} восстановлен из storage: {post_context}")
                    else:
                        logger.error(f"Пост {post_id} не найден в storage")
                        await context.bot.send_message(
                            chat_id=query.message.chat_id,
                            text="❌ Пост не найден"
                        )
                        return
            
            # Проверяем наличие message_ids
            if not post_context.original_media:
                logger.error("original_media пустой в контексте поста")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Не удалось найти сообщения поста"
                )
                return
            
            # Удаляем сообщения с медиа
            logger.info("Удаление сообщений с медиа")
            logger.info(f"ID сообщений для удаления: {post_context.original_media}")
            
            for message_id in post_context.original_media:
                try:
                    logger.info(f"Попытка удаления сообщения {message_id} из чата {post_context.chat_id}")
                    await context.bot.delete_message(
                        chat_id=post_context.chat_id,
                        message_id=message_id
                    )
                    logger.info(f"Удалено сообщение с ID: {message_id}")
                except Exception as e:
                    logger.error(f"Ошибка при удалении сообщения {message_id}: {e}", exc_info=True)
            
            # Удаляем сообщение с клавиатурой
            logger.info("Удаление сообщения с клавиатурой")
            try:
                await query.message.delete()
                logger.info(f"Удалено сообщение с ID: {query.message.message_id}")
            except Exception as e:
                logger.error(f"Ошибка при удалении сообщения с клавиатурой: {e}", exc_info=True)
            
            # Удаляем файлы поста
            post_dir = os.path.join("saved", post_id)
            logger.info(f"Путь к директории поста: {post_dir}")
            logger.info(f"Директория существует: {os.path.exists(post_dir)}")
            
            if os.path.exists(post_dir):
                logger.info(f"Удаление файлов поста из директории: {post_dir}")
                try:
                    # Удаляем ready.txt
                    ready_file = os.path.join(post_dir, "ready.txt")
                    if os.path.exists(ready_file):
                        os.remove(ready_file)
                        logger.info("Удален файл ready.txt")
                    else:
                        logger.warning(f"Файл ready.txt не найден: {ready_file}")
                    
                    # Удаляем все фотографии
                    for file in os.listdir(post_dir):
                        if file.startswith("photo_") and file.endswith(".jpg"):
                            photo_path = os.path.join(post_dir, file)
                            os.remove(photo_path)
                            logger.info(f"Удален файл {file}")
                    
                    # Удаляем директорию поста
                    import shutil
                    shutil.rmtree(post_dir)
                    logger.info(f"Удалена директория {post_dir}")
                except Exception as e:
                    logger.error(f"Ошибка при удалении файлов поста: {e}", exc_info=True)
            else:
                logger.warning(f"Директория поста не найдена: {post_dir}")
            
            # Удаляем информацию о посте из storage
            logger.info("Удаление информации о посте из storage")
            async with AsyncFileManager(STORAGE_PATH) as storage:
                data = await storage.read()
                logger.info(f"Текущие данные в storage: {data}")
                if post_id in data:
                    del data[post_id]
                    await storage.write(data)
                    logger.info(f"Информация о посте {post_id} удалена из storage")
                else:
                    logger.warning(f"Пост {post_id} не найден в storage для удаления")
            
            # Очищаем контекст поста
            logger.info("Очистка контекста поста")
            self.state_manager.clear_post_context(post_id)
            
            # Отправляем уведомление об удалении
            logger.info("Отправка уведомления об удалении")
            await context.bot.send_message(
                chat_id=post_context.chat_id,
                text="✅ Пост успешно удален"
            )
            
            logger.info("=== Завершение обработки callback-запроса на удаление ===")
            
        except Exception as e:
            logger.error(f"Ошибка при удалении поста: {e}", exc_info=True)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Произошла ошибка при удалении поста"
            )
            raise

    async def handle_moderate_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обработчик callback-запросов для модерации поста.
        
        Args:
            update: Объект обновления
            context: Контекст бота
        """
        query = update.callback_query
        await query.answer()
        
        logger.info("=== Начало обработки callback-запроса на модерацию ===")
        logger.info(f"Callback query: {query.data}")
        logger.info(f"Message ID: {query.message.message_id}")
        logger.info(f"Chat ID: {query.message.chat_id}")
        
        try:
            # Получаем post_id из callback_data
            callback_data = query.data
            logger.info(f"Получен callback_data: {callback_data}")
            
            # Проверяем формат callback_data
            if not callback_data.startswith("moderate_"):
                logger.error(f"Неверный формат callback_data: {callback_data}")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Неверный формат данных"
                )
                return
                
            post_id = callback_data.replace("moderate_", "")
            logger.info(f"Извлечен post_id: {post_id}")
            
            if not post_id:
                logger.error("post_id пустой")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Не удалось определить ID поста"
                )
                return
            
            # Получаем контекст поста
            post_context = self.state_manager.get_post_context(post_id)
            logger.info(f"Контекст поста из памяти: {post_context}")
            
            if not post_context:
                logger.info(f"Контекст поста {post_id} не найден в памяти, пытаемся восстановить из storage")
                async with AsyncFileManager(STORAGE_PATH) as storage:
                    storage_data = await storage.read()
                    logger.info(f"Данные из storage: {storage_data}")
                    
                    if post_id in storage_data:
                        post_info = storage_data[post_id]
                        logger.info(f"Найдена информация о посте: {post_info}")
                        
                        # Получаем все message_ids из storage
                        message_ids = post_info.get('message_ids', [])
                        logger.info(f"Получены message_ids из storage: {message_ids}")
                        
                        if not message_ids:
                            logger.error("message_ids не найдены в storage")
                            await context.bot.send_message(
                                chat_id=query.message.chat_id,
                                text="❌ Не удалось найти сообщения поста"
                            )
                            return
                        
                        post_context = PostContext(
                            post_id=post_id,
                            chat_id=post_info['chat_id'],
                            message_id=message_ids[0],  # ID первого сообщения с фото
                            state=BotState.POST_VIEW,
                            original_text=post_info['text'],
                            original_media=message_ids[:-1]  # Все ID кроме последнего (клавиатуры)
                        )
                        self.state_manager.set_post_context(post_id, post_context)
                        logger.info(f"Контекст поста {post_id} восстановлен из storage: {post_context}")
                    else:
                        logger.error(f"Пост {post_id} не найден в storage")
                        await context.bot.send_message(
                            chat_id=query.message.chat_id,
                            text="❌ Пост не найден"
                        )
                        return
            
            # Обновляем сообщение с клавиатурой
            logger.info("Обновление сообщения с клавиатурой модерации")
            try:
                await query.message.edit_text(
                    text=f"Выберите действие для поста {post_id}:",
                    reply_markup=get_moderate_keyboard(post_id)
                )
                logger.info("Клавиатура модерации успешно обновлена")
            except Exception as e:
                logger.error(f"Ошибка при обновлении клавиатуры: {e}", exc_info=True)
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Произошла ошибка при обновлении клавиатуры"
                )
                return
            
            # Обновляем состояние поста
            post_context.state = BotState.MODERATE_MENU
            self.state_manager.set_post_context(post_id, post_context)
            logger.info(f"Состояние поста обновлено: {post_context.state}")
            
            logger.info("=== Завершение обработки callback-запроса на модерацию ===")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке модерации поста: {e}", exc_info=True)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Произошла ошибка при обработке модерации"
            )
            raise

    async def publish_post(self, post_id: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """
        Публикация поста в каналы.
        
        Args:
            post_id: ID поста
            context: Контекст бота
            
        Returns:
            bool: True если публикация успешна, False в противном случае
        """
        logger.info(f"=== Начало публикации поста {post_id} ===")
        
        try:
            # Получаем контекст поста
            post_context = self.state_manager.get_post_context(post_id)
            logger.info(f"Контекст поста из памяти: {post_context}")
            
            if not post_context:
                logger.info(f"Контекст поста {post_id} не найден в памяти, пытаемся восстановить из storage")
                async with AsyncFileManager(STORAGE_PATH) as storage:
                    storage_data = await storage.read()
                    logger.info(f"Данные из storage: {storage_data}")
                    
                    if post_id in storage_data:
                        post_info = storage_data[post_id]
                        logger.info(f"Найдена информация о посте: {post_info}")
                        
                        post_context = PostContext(
                            post_id=post_id,
                            chat_id=post_info['chat_id'],
                            message_id=post_info['message_ids'][0],
                            state=BotState.MODERATE_MENU,
                            original_text=post_info['text'],
                            original_media=post_info['message_ids'][:-1]
                        )
                        self.state_manager.set_post_context(post_id, post_context)
                        logger.info(f"Контекст поста {post_id} восстановлен из storage: {post_context}")
                    else:
                        logger.error(f"Пост {post_id} не найден в storage")
                        return False
            
            # Получаем текст поста (оригинальный или отредактированный)
            post_text = post_context.temp_text if post_context.temp_text else post_context.original_text
            logger.info(f"Текст поста для публикации: {post_text[:100]}...")
            
            # Получаем путь к папке поста
            post_dir = os.path.join("saved", post_id)
            if not os.path.exists(post_dir):
                logger.error(f"Папка поста не найдена: {post_dir}")
                return False
            
            # Получаем список фотографий
            photos = sorted(
                [f for f in os.listdir(post_dir) if f.startswith("photo_") and f.endswith(".jpg")],
                key=lambda x: int(x.split("_")[1].split(".")[0])
            )
            if not photos:
                logger.error(f"Нет фотографий в папке {post_dir}")
                return False
            
            photo_paths = [os.path.join(post_dir, photo) for photo in photos]
            logger.info(f"Найдено {len(photos)} фотографий: {photo_paths}")
            
            # Формируем медиа-группу
            media_group = []
            for i, path in enumerate(photo_paths):
                try:
                    # Добавляем caption только к первой фотографии
                    if i == 0:
                        media_group.append(
                            InputMediaPhoto(
                                media=open(path, 'rb'),
                                caption=post_text
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
                    return False
            
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
                return False
            
            # Публикуем в закрытый канал
            logger.info("Публикация в закрытый канал")
            try:
                await context.bot.send_media_group(
                    chat_id=settings.PRIVATE_CHANNEL_ID,
                    media=media_group,
                    read_timeout=30,
                    write_timeout=30,
                    connect_timeout=30,
                    pool_timeout=30
                )
                logger.info("Пост успешно опубликован в закрытый канал")
            except Exception as e:
                logger.error(f"Ошибка при публикации в закрытый канал: {e}", exc_info=True)
                return False
            
            # Обновляем статус поста в storage
            logger.info("Обновление статуса поста в storage")
            async with AsyncFileManager(STORAGE_PATH) as storage:
                data = await storage.read()
                if post_id in data:
                    data[post_id]['status'] = 'published'
                    await storage.write(data)
                    logger.info(f"Статус поста {post_id} обновлен на 'published'")
                else:
                    logger.warning(f"Пост {post_id} не найден в storage для обновления статуса")
            
            logger.info(f"=== Завершение публикации поста {post_id} ===")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка при публикации поста {post_id}: {e}", exc_info=True)
            return False

    async def handle_publish_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обработчик callback-запросов для публикации поста.
        
        Args:
            update: Объект обновления
            context: Контекст бота
        """
        query = update.callback_query
        await query.answer()
        
        logger.info("=== Начало обработки callback-запроса на публикацию ===")
        logger.info(f"Callback query: {query.data}")
        logger.info(f"Message ID: {query.message.message_id}")
        logger.info(f"Chat ID: {query.message.chat_id}")
        
        try:
            # Получаем post_id из callback_data
            callback_data = query.data
            logger.info(f"Получен callback_data: {callback_data}")
            
            # Проверяем формат callback_data
            if not callback_data.startswith("publish_post_"):
                logger.error(f"Неверный формат callback_data: {callback_data}")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Неверный формат данных"
                )
                return
                
            post_id = callback_data.replace("publish_post_", "")
            logger.info(f"Извлечен post_id: {post_id}")
            
            if not post_id:
                logger.error("post_id пустой")
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Не удалось определить ID поста"
                )
                return
            
            # Публикуем пост
            if await self.publish_post(post_id, context):
                # Удаляем сообщение с клавиатурой
                try:
                    await query.message.delete()
                    logger.info(f"Удалено сообщение с ID: {query.message.message_id}")
                except Exception as e:
                    logger.error(f"Ошибка при удалении сообщения с клавиатурой: {e}", exc_info=True)
                
                # Отправляем уведомление об успешной публикации
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="✅ Пост успешно опубликован в каналы"
                )
                
                # Очищаем контекст поста
                self.state_manager.clear_post_context(post_id)
                logger.info(f"Контекст поста {post_id} очищен")
            else:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Произошла ошибка при публикации поста"
                )
            
            logger.info("=== Завершение обработки callback-запроса на публикацию ===")
            
        except Exception as e:
            logger.error(f"Ошибка при обработке публикации поста: {e}", exc_info=True)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Произошла ошибка при обработке публикации"
            )
            raise

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
        main() 
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
