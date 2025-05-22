"""
Основной модуль бота.
"""
import logging
import asyncio
import os
import json
from datetime import datetime
from typing import Dict, Any, Optional, List
from telegram import Update, InputMediaPhoto, InlineKeyboardMarkup, CallbackQuery, InlineKeyboardButton
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
    CallbackQueryHandler,
    MessageHandler,
    filters
)
from telegram.error import TimedOut, NetworkError, TelegramError
import time
import collections
import re
import sys

from src.config.settings import settings
from src.utils.logger import setup_logger
from src.bot.keyboards import (
    get_post_keyboard,
    get_edit_keyboard,
    get_media_edit_keyboard,
    get_moderate_keyboard
)
from src.bot.storage import AsyncFileManager, SentPostsCache
from src.bot.states import BotState, StateManager, PostContext
from src.bot.handlers.callback import handle_media_callback
from src.bot.text_processor import TextProcessor

# Настройка логгера
logger = setup_logger("bot")

# Путь к файлу storage
STORAGE_PATH = "storage.json"
SAVED_DIR = settings.SAVE_DIR

media_group_temp = collections.defaultdict(dict)  # {user_id: {media_group_id: [PhotoSize, ...]}}
media_group_tasks = collections.defaultdict(dict)  # {user_id: {media_group_id: asyncio.Task}}
MEDIA_GROUP_TIMEOUT = 9.0  # секунд

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
        self.storage = AsyncFileManager("storage.json")
        self.sent_posts_cache = SentPostsCache()
        self.text_processor = TextProcessor()
        
        # Создаем storage.json если его нет
        if not os.path.exists(STORAGE_PATH):
            logger.info("Creating storage.json file")
            with open(STORAGE_PATH, 'w', encoding='utf-8') as f:
                json.dump({}, f, ensure_ascii=False, indent=2)
            logger.info("storage.json created successfully")
        
        # Запускаем периодическую проверку
        self.application.post_init = self._start_periodic_check
            
        logger.info("Bot initialized successfully")

    async def _start_periodic_check(self, application: Application) -> None:
        """Запуск периодической проверки после инициализации бота."""
        # Синхронизируем кэш с storage
        await self.sent_posts_cache.sync_with_storage(STORAGE_PATH)
        
        # Запускаем периодическую проверку
        self.check_task = asyncio.create_task(self._run_periodic_check(application))
        logger.info("Periodic check started")

    def _setup_handlers(self) -> None:
        """Настройка обработчиков команд."""
        logger.info("=== Начало настройки обработчиков команд ===")
        try:
            # Обработчик команды /test
            logger.info("Регистрация обработчика /test")
            self.application.add_handler(CommandHandler("test", self.test_command))
            logger.info("Обработчик /test успешно зарегистрирован")

            # Обработчик callback-запросов для удаления
            logger.info("Регистрация обработчика delete_")
            self.application.add_handler(CallbackQueryHandler(
                self.handle_delete_callback,
                pattern=r"^delete_"
            ))
            logger.info("Обработчик delete_ успешно зарегистрирован")

            # Обработчик callback-запросов для модерации
            logger.info("Регистрация обработчика moderate_")
            self.application.add_handler(CallbackQueryHandler(
                self.handle_moderate_callback,
                pattern=r"^moderate_"
            ))
            logger.info("Обработчик moderate_ успешно зарегистрирован")

            # Обработчик callback-запросов для публикации
            logger.info("Регистрация обработчика publish_")
            self.application.add_handler(CallbackQueryHandler(
                self.handle_publish_callback,
                pattern=r"^publish_"
            ))
            logger.info("Обработчик publish_ успешно зарегистрирован")

            # Обработчик callback-запросов для редактирования текста
            logger.info("Регистрация обработчика edittext_")
            self.application.add_handler(CallbackQueryHandler(
                self.handle_edit_text_callback,
                pattern=r"^edittext_"
            ))
            logger.info("Обработчик edittext_ успешно зарегистрирован")

            # Обработчик callback-запросов для редактирования
            logger.info("Регистрация обработчика edit_")
            self.application.add_handler(CallbackQueryHandler(
                self.handle_edit,
                pattern=r"^edit_"
            ))
            logger.info("Обработчик edit_ успешно зарегистрирован")

            # Обработчик callback-запросов для редактирования медиа (editmedia_)
            logger.info("Регистрация обработчика editmedia_")
            self.application.add_handler(CallbackQueryHandler(
                self.handle_edit_media_callback,
                pattern=r"^editmedia_"
            ))
            logger.info("Обработчик editmedia_ успешно зарегистрирован")

            # Обработчик callback-запросов для добавления медиа (addmedia_)
            logger.info("Регистрация обработчика addmedia_")
            self.application.add_handler(CallbackQueryHandler(
                self.handle_add_media_callback,
                pattern=r"^addmedia_"
            ))
            logger.info("Обработчик addmedia_ успешно зарегистрирован")

            # Обработчик текстовых сообщений
            logger.info("Регистрация обработчика текстовых сообщений")
            self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
            logger.info("Обработчик текстовых сообщений успешно зарегистрирован")

            # Обработчик фотографий
            logger.info("Регистрация обработчика фотографий")
            self.application.add_handler(MessageHandler(filters.PHOTO, self.handle_message))
            logger.info("Обработчик фотографий успешно зарегистрирован")

            # Обработчик документов
            logger.info("Регистрация обработчика документов")
            self.application.add_handler(MessageHandler(filters.Document.IMAGE, self.handle_message))
            logger.info("Обработчик документов успешно зарегистрирован")

            # Обработчик callback-запросов для удаления медиа (removemedia_)
            logger.info("Регистрация обработчика removemedia_")
            self.application.add_handler(CallbackQueryHandler(
                self.handle_remove_media_callback,
                pattern=r"^removemedia_"
            ))
            logger.info("Обработчик removemedia_ успешно зарегистрирован")

            logger.info("=== Настройка обработчиков команд успешно завершена ===")
        except Exception as e:
            logger.error(f"Ошибка при настройке обработчиков: {e}", exc_info=True)
            raise

    async def is_post_sent(self, post_id: str) -> bool:
        """Проверяет, был ли пост уже отправлен."""
        result = self.sent_posts_cache.is_post_sent(post_id)
        logger.info(f"[is_post_sent] Проверка поста {post_id}: {'уже отправлен' if result else 'еще не отправлен'}")
        logger.info(f"[is_post_sent] Текущее состояние кэша: {self.sent_posts_cache._cache}")
        return result

    async def process_post(self, post_dir: str, context: ContextTypes.DEFAULT_TYPE) -> bool:
        """Обработка одного поста."""
        try:
            post_id = os.path.basename(post_dir)
            logger.info(f"[process_post] Начало обработки поста {post_id} из директории: {post_dir}")

            # Проверяем, не был ли пост уже отправлен
            if await self.is_post_sent(post_id):
                logger.info(f"[process_post] Пост {post_id} уже отправлен, пропускаем")
                return False

            # Проверяем статус готовности
            ready_file = os.path.join(post_dir, "ready.txt")
            if not os.path.exists(ready_file):
                logger.error(f"[process_post] Пост не готов, файл ready.txt не найден в {post_dir}")
                return False

            with open(ready_file, 'r') as f:
                status = f.read().strip()
                logger.info(f"[process_post] Статус ready.txt: {status}")

            if status != "ok":
                logger.error(f"[process_post] Пост не готов, статус: {status}")
                return False

            # Читаем текст поста
            text_file = os.path.join(post_dir, "text.txt")
            if not os.path.exists(text_file):
                logger.error(f"[process_post] Файл text.txt не найден в {post_dir}")
                return False

            with open(text_file, 'r', encoding='utf-8') as f:
                post_text = f.read().strip()
                logger.info(f"[process_post] Текст поста: {post_text[:100]}...")

            # Обрабатываем текст с учетом лимитов
            processed_text, was_truncated = await self.text_processor.process_text(post_text)
            if was_truncated:
                logger.info("[process_post] Текст был обрезан из-за превышения лимита")
            
            # Читаем информацию об источнике
            source_file = os.path.join(post_dir, "source.txt")
            if not os.path.exists(source_file):
                logger.error(f"[process_post] Файл source.txt не найден в {post_dir}")
                return False

            with open(source_file, 'r', encoding='utf-8') as f:
                source_info = f.read().strip()
                logger.info(f"[process_post] Информация об источнике: {source_info}")

            # Формируем полный текст поста с информацией об источнике
            full_text = f"{processed_text}"

            # Получаем список фотографий
            photos = sorted(
                [f for f in os.listdir(post_dir) if f.startswith("photo_") and f.endswith(".jpg")],
                key=lambda x: int(x.split("_")[1].split(".")[0])
            )
            if not photos:
                logger.error(f"[process_post] Фотографии не найдены в {post_dir}")
                return False

            photo_paths = [os.path.join(post_dir, photo) for photo in photos]
            logger.info(f"[process_post] Найдено {len(photos)} фотографий: {photo_paths}")

            # Отправляем альбом с фотографиями и текстом
            logger.info("[process_post] Отправка альбома с подписью")
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
                logger.info("[process_post] Альбом успешно отправлен")

                # Отправляем клавиатуру с действиями
                logger.info("[process_post] Отправка клавиатуры с действиями")
                keyboard_message = await context.bot.send_message(
                    chat_id=settings.MODERATOR_GROUP_ID,
                    text=f"Выберите действие для поста \n{source_info}:",
                    reply_markup=get_post_keyboard(post_id),
                    read_timeout=20,
                    write_timeout=15,
                    connect_timeout=15,
                    pool_timeout=15
                )
                logger.info("[process_post] Клавиатура успешно отправлена")

                # Сохраняем информацию о посте
                message_ids = [msg.message_id for msg in messages]
                message_ids.append(keyboard_message.message_id)
                
                logger.info(f"[process_post] ID сообщений из media group: {[msg.message_id for msg in messages]}")
                logger.info(f"[process_post] ID сообщения с клавиатурой: {keyboard_message.message_id}")
                logger.info(f"[process_post] Все ID сообщений: {message_ids}")

                # Создаем контекст поста
                post_context = PostContext(
                    post_id=post_id,
                    chat_id=settings.MODERATOR_GROUP_ID,
                    message_id=messages[0].message_id,
                    state=BotState.POST_VIEW,
                    original_text=full_text,
                    original_media=message_ids[:-1]  # Все ID кроме последнего (клавиатуры)
                )
                logger.info(f"[process_post] Создан новый контекст поста: {post_context}")
                self.state_manager.set_post_context(post_id, post_context)
                logger.info(f"[process_post] Контекст поста {post_id} сохранен с состоянием {BotState.POST_VIEW}")

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
                logger.info(f"[process_post] Пост из {post_dir} успешно отправлен")
                logger.info(f"[process_post] Логирование поста {post_id} как отправленного")

                async with AsyncFileManager(STORAGE_PATH) as storage:
                    data = await storage.read()
                    logger.info(f"[process_post] Текущие данные в storage: {data}")
                    data[post_id] = post_info
                    logger.info(f"[process_post] Добавление информации о посте в storage: {post_info}")
                    await storage.write(data)
                    logger.info(f"[process_post] Storage успешно обновлен для поста {post_id}")

                # Добавляем пост в кэш отправленных
                self.sent_posts_cache.add_post(post_id)
                logger.info(f"[process_post] Пост {post_id} добавлен в кэш отправленных")
                logger.info(f"[process_post] Текущее состояние кэша: {self.sent_posts_cache._cache}")

                logger.info(f"[process_post] Пост {post_id} успешно обработан")
                return True

            except Exception as e:
                logger.error(f"[process_post] Ошибка сети при отправке поста из {post_dir}: {e}")
                raise

        except Exception as e:
            logger.error(f"[process_post] Ошибка при обработке поста из {post_dir}: {e}")
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
        post_id = None

        # Ищем контекст поста по chat_id и состоянию (EDIT_MEDIA_ADD_WAIT или EDIT_TEXT_WAIT)
        logger.info("Поиск контекста поста...")
        for pid, ctx in self.state_manager.get_all_contexts().items():
            logger.info(f"Проверка контекста поста {pid}:")
            logger.info(f"  - Chat ID: {ctx.chat_id}")
            logger.info(f"  - State: {ctx.state}")
            logger.info(f"  - Original Text: {ctx.original_text}")
            if ctx.chat_id == update.message.chat_id and ctx.state in [BotState.EDIT_MEDIA_ADD_WAIT, BotState.EDIT_TEXT_WAIT, BotState.EDIT_MEDIA_REMOVE_WAIT]:
                post_context = ctx
                post_id = pid
                logger.info(f"Найден подходящий контекст поста: {post_id} (state={ctx.state})")
                break
        logger.info(f"Текущий контекст: {post_context}")
        if post_context:
            logger.info(f"Текущее состояние поста: {post_context.state}")
        if post_context and post_context.state == BotState.EDIT_MEDIA_ADD_WAIT:
            logger.info(f"handle_message: переход к handle_media_add_message (state={post_context.state})")
            await self.handle_media_add_message(update, context)
            return
        if post_context and post_context.state == BotState.EDIT_TEXT_WAIT:
            logger.info(f"handle_message: обработка нового текста (state={post_context.state})")
            # --- обработка нового текста (оставить существующую логику) ---
            logger.info("Состояние EDIT_TEXT_WAIT подтверждено")
            # Сохраняем ID пользовательского сообщения (текст)
            post_context.user_message_ids.append(update.message.message_id)
            self.state_manager.set_post_context(post_id, post_context)
            try:
                # Получаем путь к папке поста
                post_dir = os.path.join(SAVED_DIR, post_id)
                logger.info(f"Путь к папке поста: {post_dir}")
                if not os.path.exists(post_dir):
                    logger.error(f"Папка поста не найдена: {post_dir}")
                    await update.message.reply_text("❌ Ошибка: папка поста не найдена")
                    return
                # Сохраняем новый текст в temp.txt
                temp_file = os.path.join(post_dir, "temp.txt")
                logger.info(f"Путь к временному файлу: {temp_file}")
                try:
                    with open(temp_file, 'w', encoding='utf-8') as f:
                        f.write(update.message.text)
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
                        logger.error(f"Ошибка при удалении старого сообщения {message_id}: {e}")
                # Удаляем служебные сообщения
                logger.info("Удаление служебных сообщений")
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
                # Отправляем новый пост
                logger.info("Отправка нового поста")
                messages = []
                media_group = []
                # Находим все фотографии в папке поста
                photos = [f for f in os.listdir(post_dir) if f.startswith("photo_") and f.endswith(".jpg")]
                photos.sort(key=lambda x: int(x.split("_")[1].split(".")[0]))
                logger.info(f"Найдено фотографий: {len(photos)}")
                # Формируем пути к фотографиям
                photo_paths = [os.path.join(post_dir, photo) for photo in photos]
                logger.info(f"Пути к фотографиям: {photo_paths}")
                # Обрабатываем текст с учетом лимитов
                processed_text, was_truncated = await self.text_processor.process_text(update.message.text)
                if was_truncated:
                    logger.info("Текст был обрезан из-за превышения лимита")
                    await update.message.reply_text("⚠️ Текст был обрезан из-за превышения лимита Telegram (1024 символа)")
                # Добавляем фотографии в media_group
                for i, photo_path in enumerate(photo_paths):
                    logger.info(f"Обработка фото {i+1}/{len(photo_paths)}: {photo_path}")
                    with open(photo_path, 'rb') as photo:
                        if i == 0:  # Первое фото с caption
                            media_group.append(
                                InputMediaPhoto(
                                    media=photo,
                                    caption=processed_text
                                )
                            )
                            logger.info("Добавлено фото с caption")
                        else:  # Остальные фото без caption
                            media_group.append(
                                InputMediaPhoto(
                                    media=photo
                                )
                            )
                            logger.info("Добавлено фото без caption")
                # Отправляем новый пост
                logger.info("Отправка нового поста")
                messages = await context.bot.send_media_group(
                    chat_id=post_context.chat_id,
                    media=media_group
                )
                logger.info("Новый пост успешно отправлен")
                # Обновляем контекст поста с новыми ID
                message_ids = [msg.message_id for msg in messages]
                logger.info(f"Получены новые ID сообщений: {message_ids}")
                post_context.original_media = message_ids
                post_context.original_text = processed_text
                post_context.state = BotState.MODERATE_MENU
                logger.info(f"Смена состояния: EDIT_TEXT_WAIT -> MODERATE_MENU для поста {post_id}")
                self.state_manager.set_post_context(post_id, post_context)
                logger.info("Контекст поста обновлен")
                # Отправляем клавиатуру к новому посту
                logger.info("Отправка клавиатуры")
                # Читаем информацию об источнике
                source_file = os.path.join(post_dir, "source.txt")
                if not os.path.exists(source_file):
                    logger.error(f"No source file found in {post_dir}")
                    return False
                with open(source_file, 'r', encoding='utf-8') as f:
                    source_info = f.read().strip()
                    logger.info(f"Source info: {source_info}")
                keyboard_message = await context.bot.send_message(
                    chat_id=post_context.chat_id,
                    text=f"Выберите действие для поста \n{source_info}:",
                    reply_markup=get_moderate_keyboard(post_id),
                    read_timeout=20,
                    write_timeout=15,
                    connect_timeout=15,
                    pool_timeout=15
                )
                logger.info(f"Клавиатура отправлена, message_id={keyboard_message.message_id}")
                # Сохраняем ID сообщения с клавиатурой в service_messages
                post_context.service_messages.append(keyboard_message.message_id)
                self.state_manager.set_post_context(post_id, post_context)
                # Добавляем ID сообщения с клавиатурой в список сообщений
                message_ids.append(keyboard_message.message_id)
                logger.info(f"Обновленный список ID сообщений: {message_ids}")
                # Обновляем storage
                logger.info("Обновление storage")
                async with AsyncFileManager(STORAGE_PATH) as storage:
                    data = await storage.read()
                    if post_id in data:
                        data[post_id]['message_ids'] = message_ids
                        data[post_id]['text'] = processed_text
                        await storage.write(data)
                        logger.info(f"Storage обновлен для поста {post_id}")
                    else:
                        logger.warning(f"Пост {post_id} не найден в storage")
                # Удаляем temp.txt после успешного обновления
                try:
                    os.remove(temp_file)
                    logger.info(f"Временный файл {temp_file} удален")
                except Exception as e:
                    logger.error(f"Ошибка при удалении temp.txt: {e}")
            except Exception as e:
                logger.error(f"Ошибка при обработке нового текста: {e}", exc_info=True)
                await update.message.reply_text("❌ Произошла ошибка при обработке текста")
                return
            logger.info("=== Завершение обработки сообщения ===")
            return
        if post_context and post_context.state == BotState.EDIT_MEDIA_REMOVE_WAIT:
            logger.info(f"handle_message: обработка удаления фото (state={post_context.state})")
            # Сохраняем ID пользовательского сообщения
            post_context.user_message_ids.append(update.message.message_id)
            self.state_manager.set_post_context(post_id, post_context)
            
            # Получаем номера фото для удаления
            text = update.message.text.strip()
            try:
                numbers = list(map(int, text.split()))
            except Exception:
                error_msg = await update.message.reply_text("❌ Ошибка: введите номера фото через пробел, например: 1 3 4")
                post_context.service_messages.append(error_msg.message_id)
                self.state_manager.set_post_context(post_id, post_context)
                return

            post_dir = os.path.join(SAVED_DIR, post_id)
            photos = [f for f in os.listdir(post_dir) if f.startswith("photo_") and f.endswith(".jpg")]
            photos.sort(key=lambda x: int(x.split('_')[1].split('.')[0]))
            
            if not photos:
                no_photos_msg = await update.message.reply_text("В этом посте нет фото для удаления.")
                post_context.service_messages.append(no_photos_msg.message_id)
                self.state_manager.set_post_context(post_id, post_context)
                return

            # Проверяем валидность номеров
            to_delete = set()
            for n in numbers:
                if 1 <= n <= len(photos):
                    to_delete.add(n-1)
            
            if not to_delete:
                invalid_msg = await update.message.reply_text("❌ Ошибка: нет корректных номеров для удаления.")
                post_context.service_messages.append(invalid_msg.message_id)
                self.state_manager.set_post_context(post_id, post_context)
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
            self.state_manager.set_post_context(post_id, post_context)

            # Отправляем сообщение об успешном удалении
            success_msg = await update.message.reply_text(f"✅ Фото удалены: {' '.join(deleted) if deleted else 'ничего не удалено'}")
            post_context.service_messages.append(success_msg.message_id)
            self.state_manager.set_post_context(post_id, post_context)
            logger.info(f"Фото удалены из поста {post_id}: {deleted}")
            logger.info("=== Завершение обработки сообщения ===")
            return
        logger.info("Контекст поста не найден")
        return

    async def handle_media_add_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Обработка входящих фото/альбомов в состоянии EDIT_MEDIA_ADD_WAIT.
        """
        logger.info("=== handle_media_add_message: старт ===")
        user_id = update.message.from_user.id
        post_context = None
        post_id = None
        # Поиск контекста поста в состоянии EDIT_MEDIA_ADD_WAIT
        for pid, ctx in self.state_manager.get_all_contexts().items():
            if ctx.chat_id == update.message.chat_id and ctx.state == BotState.EDIT_MEDIA_ADD_WAIT:
                post_context = ctx
                post_id = pid
                break
        if not post_context:
            logger.error("Контекст поста не найден для добавления медиа")
            return
        # Сохраняем ID пользовательского сообщения (фото)
        post_context.user_message_ids.append(update.message.message_id)
        self.state_manager.set_post_context(post_id, post_context)
        post_dir = os.path.join(SAVED_DIR, post_id)
        if not update.message.photo:
            await update.message.reply_text("❌ Пожалуйста, отправьте фото.")
            return
        media_group_id = update.message.media_group_id
        if media_group_id:
            # Альбом: собираем фото во временное хранилище
            if media_group_id not in media_group_temp[user_id]:
                media_group_temp[user_id][media_group_id] = []
            media_group_temp[user_id][media_group_id].append(update.message.photo[-1])
            logger.info(f"Альбом: добавлено фото в media_group_temp[{user_id}][{media_group_id}] (текущее кол-во: {len(media_group_temp[user_id][media_group_id])})")
            # Сбросить старый таймер, если есть
            if media_group_id in media_group_tasks[user_id]:
                media_group_tasks[user_id][media_group_id].cancel()
            # Запустить новый таймер
            async def timer():
                try:
                    await asyncio.sleep(MEDIA_GROUP_TIMEOUT)
                    await self.finalize_media_add_album(user_id, media_group_id, post_context, context)
                except asyncio.CancelledError:
                    pass
            media_group_tasks[user_id][media_group_id] = asyncio.create_task(timer())
        else:
            # Одиночное фото — сразу финализируем
            await self.finalize_media_add_single(update, context, post_context)
        logger.info("=== handle_media_add_message: завершено ===")

    async def finalize_media_add_album(self, user_id, media_group_id, post_context, context):
        """
        Финализация добавления альбома: сохраняет фото, удаляет старые сообщения, отправляет новый пост.
        """
        logger.info(f"=== finalize_media_add_album: старт для post_id={post_context.post_id}, media_group_id={media_group_id} ===")
        post_id = post_context.post_id
        post_dir = os.path.join(SAVED_DIR, post_id)
        album_photos = media_group_temp[user_id][media_group_id]
        old_photos = [f for f in os.listdir(post_dir) if f.startswith("photo_") and f.endswith(".jpg")]
        old_photos.sort(key=lambda x: int(x.split('_')[1].split('.')[0]))
        old_photo_paths = [os.path.join(post_dir, f) for f in old_photos]
        new_photo_paths = []
        start_idx = len(old_photo_paths) + 1
        for i, photo in enumerate(album_photos):
            file = await photo.get_file()
            file_path = os.path.join(post_dir, f"photo_{start_idx + i}.jpg")
            await file.download_to_drive(file_path)
            new_photo_paths.append(file_path)
            logger.info(f"Сохранено фото: {file_path}")
        all_photo_paths = old_photo_paths + new_photo_paths
        # Удаляем старые сообщения
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
        # Отправляем новый пост
        media_group = []
        for i, path in enumerate(all_photo_paths):
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
        self.state_manager.set_post_context(post_id, post_context)
        # Очистка временных данных
        del media_group_temp[user_id][media_group_id]
        del media_group_tasks[user_id][media_group_id]
        logger.info(f"Пост {post_id} обновлён с новыми фото (альбом)")
        await context.bot.send_message(chat_id=post_context.chat_id, text="✅ Фото успешно добавлены к посту!")
        logger.info(f"=== finalize_media_add_album: завершено для post_id={post_id} ===")

    async def finalize_media_add_single(self, update, context, post_context):
        """
        Финализация добавления одиночного фото: сохраняет фото, удаляет старые сообщения, отправляет новый пост.
        """
        logger.info(f"=== finalize_media_add_single: старт для post_id={post_context.post_id} ===")
        user_id = update.message.from_user.id
        post_id = post_context.post_id
        post_dir = os.path.join(SAVED_DIR, post_id)
        old_photos = [f for f in os.listdir(post_dir) if f.startswith("photo_") and f.endswith(".jpg")]
        old_photos.sort(key=lambda x: int(x.split('_')[1].split('.')[0]))
        old_photo_paths = [os.path.join(post_dir, f) for f in old_photos]
        photo = update.message.photo[-1]
        file = await photo.get_file()
        file_path = os.path.join(post_dir, f"photo_{len(old_photo_paths)+1}.jpg")
        await file.download_to_drive(file_path)
        all_photo_paths = old_photo_paths + [file_path]
        # Удаляем старые сообщения
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
        # Отправляем новый пост
        media_group = []
        for i, path in enumerate(all_photo_paths):
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
        self.state_manager.set_post_context(post_id, post_context)
        logger.info(f"Пост {post_id} обновлён с новым фото (одиночное)")
        await context.bot.send_message(chat_id=post_context.chat_id, text="✅ Фото успешно добавлены к посту!")
        logger.info(f"=== finalize_media_add_single: завершено для post_id={post_id} ===")

    async def check_posts(self, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Периодическая проверка постов.

        Args:
            context: Контекст бота
        """
        if self.is_checking:
            logger.info("[check_posts] Предыдущая проверка все еще выполняется, пропускаем")
            return

        self.is_checking = True
        try:
            logger.info("[check_posts] Начало периодической проверки постов")

            # Путь к папке с постами
            saved_dir = SAVED_DIR
            if not os.path.exists(saved_dir):
                logger.error(f"[check_posts] Директория saved не найдена: {saved_dir}")
                return

            # Получаем список всех подпапок
            post_dirs = []
            for item in os.listdir(saved_dir):
                item_path = os.path.join(saved_dir, item)
                if os.path.isdir(item_path) and item.startswith('post_'):
                    post_dirs.append(item_path)

            if not post_dirs:
                logger.info("[check_posts] Директории с постами не найдены")
                return

            logger.info(f"[check_posts] Найдено {len(post_dirs)} директорий с постами")

            # Обрабатываем каждый пост
            success_count = 0
            error_count = 0

            for post_dir in sorted(post_dirs):
                post_id = os.path.basename(post_dir)
                logger.info(f"[check_posts] Проверка поста {post_id}")
                
                # Проверяем, не был ли пост уже отправлен
                if await self.is_post_sent(post_id):
                    logger.info(f"[check_posts] Пост {post_id} уже отправлен, пропускаем")
                    continue

                # Проверяем, есть ли пост в storage
                async with AsyncFileManager(STORAGE_PATH) as storage:
                    data = await storage.read()
                    if post_id in data:
                        logger.info(f"[check_posts] Пост {post_id} уже есть в storage, пропускаем")
                        continue

                processing_result = False
                try:
                    processing_result = await self.process_post(post_dir, context)
                except Exception as e:
                    logger.error(f"[check_posts] Ошибка при обработке поста {post_id}: {e}", exc_info=True)
                if processing_result:
                    success_count += 1
                    logger.info(f"[check_posts] Пост {post_id} успешно обработан")
                else:
                    error_count += 1
                    logger.info(f"[check_posts] Ошибка при обработке поста {post_id}")

            logger.info(f"[check_posts] Проверка завершена. Успешно: {success_count}, Ошибок: {error_count}")
        except Exception as e:
            logger.error(f"[check_posts] Ошибка в периодической проверке: {e}", exc_info=True)
        finally:
            self.is_checking = False
            self.sent_posts_cache.update_last_check()
            logger.info("[check_posts] Проверка завершена, флаг is_checking сброшен")

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
            saved_dir = SAVED_DIR
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
                processing_result = False
                try:
                    processing_result = await self.process_post(post_dir, context)
                except Exception as e:
                    logger.error(f"Error processing post_dir: {e}", exc_info=True)
                if processing_result:
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
        """Запуск периодической проверки постов."""
        while True:
            try:
                await self.check_posts(context)
            except Exception as e:
                logger.error(f"Error in periodic check: {e}", exc_info=True)
            await asyncio.sleep(20)  # Проверка каждые 20 секунд

    async def handle_delete_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обработчик callback-запросов для удаления поста.
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
            # Получаем актуальный контекст поста
            post_context = self.state_manager.get_post_context(post_id)
            logger.info(f"Контекст поста из памяти: {post_context}")
            if not post_context:
                logger.info(f"Контекст поста {post_id} не найден в памяти, пытаемся восстановить из storage")
                async with AsyncFileManager(STORAGE_PATH) as storage:
                    storage_data = await storage.read()
                    logger.info(f"Данные из storage: {storage_data}")
                    if post_id in storage_data:
                        post_info = storage_data[post_id]
                        message_ids = post_info.get('message_ids', [])
                        post_context = PostContext(
                            post_id=post_id,
                            chat_id=post_info['chat_id'],
                            message_id=message_ids[0] if message_ids else None,
                            state=BotState.POST_VIEW,
                            original_text=post_info['text'],
                            original_media=message_ids[:-1] if message_ids else []
                        )
                        self.state_manager.set_post_context(post_id, post_context)
                    else:
                        logger.error(f"Пост {post_id} не найден в storage")
                        await context.bot.send_message(
                            chat_id=query.message.chat_id,
                            text="❌ Пост не найден"
                        )
                        return
            # Удаляем все сообщения (медиа, служебные, пользовательские)
            for message_id in getattr(post_context, 'original_media', []):
                try:
                    await context.bot.delete_message(chat_id=post_context.chat_id, message_id=message_id)
                except Exception as e:
                    logger.error(f"Ошибка при удалении сообщения {message_id}: {e}")
            for message_id in getattr(post_context, 'service_messages', []):
                try:
                    await context.bot.delete_message(chat_id=post_context.chat_id, message_id=message_id)
                except Exception as e:
                    logger.error(f"Ошибка при удалении служебного сообщения {message_id}: {e}")
            for message_id in getattr(post_context, 'user_message_ids', []):
                try:
                    await context.bot.delete_message(chat_id=post_context.chat_id, message_id=message_id)
                except Exception as e:
                    logger.error(f"Ошибка при удалении пользовательского сообщения {message_id}: {e}")
            # Удаляем сообщение с клавиатурой (если оно ещё есть)
            try:
                await query.message.delete()
                logger.info(f"Удалено сообщение с ID: {query.message.message_id}")
            except Exception as e:
                logger.error(f"Ошибка при удалении сообщения с клавиатурой: {e}", exc_info=True)
            # Удаляем файлы поста и storage/context (оставляю как было)
            post_dir = os.path.join(SAVED_DIR, post_id)
            logger.info(f"Путь к директории поста: {post_dir}")
            logger.info(f"Директория существует: {os.path.exists(post_dir)}")
            if os.path.exists(post_dir):
                logger.info(f"Удаление файлов поста из директории: {post_dir}")
                try:
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
            # Очищаем контекст
            logger.info("Очистка контекста поста")
            self.state_manager.clear_post_context(post_id)
            # Отправляем уведомление об удалении
            logger.info("Отправка уведомления об удалении")
            await context.bot.send_message(
                chat_id=post_context.chat_id,
                text=f"✅ Пост успешно удален"
            )
            logger.info("=== Завершение обработки callback-запроса на удаление ===")
        except Exception as e:
            logger.error(f"Ошибка при удалении поста: {e}", exc_info=True)
            await context.bot.send_message(
                chat_id=query.message.chat_id,
                text="❌ Произошла ошибка при удалении поста"
            )

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
                    reply_markup=get_moderate_keyboard(post_id),
                    read_timeout=20,
                    write_timeout=15,
                    connect_timeout=15,
                    pool_timeout=15
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
            post_dir = os.path.join(SAVED_DIR, post_id)
            if not os.path.exists(post_dir):
                logger.error(f"Папка поста не найдена: {post_dir}")
                return False

            # Читаем text_close.txt для закрытого канала
            text_close_file = os.path.join(post_dir, "text_close.txt")
            if not os.path.exists(text_close_file):
                logger.error(f"Файл text_close.txt не найден в {post_dir}")
                return False

            # Читаем текст для закрытого канала
            with open(text_close_file, 'r', encoding='utf-8') as f:
                close_text = f.read().strip()
                logger.info(f"Текст из text_close.txt: {close_text[:100]}...")

            # Читаем первые две строки из source.txt
            source_file = os.path.join(post_dir, "source.txt")
            if not os.path.exists(source_file):
                logger.error(f"Файл source.txt не найден в {post_dir}")
                return False

            with open(source_file, 'r', encoding='utf-8') as f:
                source_lines = f.readlines()
                if len(source_lines) >= 2:
                    source_text = ''.join(source_lines[:2]).strip()
                    logger.info(f"Первые две строки из source.txt: {source_text}")
                else:
                    logger.error(f"В файле source.txt недостаточно строк: {source_lines}")
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
            
            # Обрабатываем текст для публикации в открытый канал
            processed_text, was_truncated = await self.text_processor.process_text(post_text, is_channel=True)
            if was_truncated:
                logger.info("Текст был обрезан из-за превышения лимита")
            
            # Обрабатываем текст для закрытого канала
            processed_close_text, was_truncated = await self.text_processor.process_private_channel_text(
                close_text,
                source_text
            )
            if was_truncated:
                logger.info("Текст для закрытого канала был обрезан из-за превышения лимита")
            
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

            media_group[0] = private_first_media_photo

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

    async def _delete_post_and_messages_by_id(self, post_id: str, context: ContextTypes.DEFAULT_TYPE, moderator_message=None) -> None:
        """
        Удаляет все сообщения, файлы и контекст, связанные с постом по post_id (используется для автозачистки после публикации).
        """
        logger.info(f"[delete_post_and_messages_by_id] Начало удаления поста {post_id}")
        post_context = self.state_manager.get_post_context(post_id)
        logger.info(f"[delete_post_and_messages_by_id] Контекст поста: {post_context}")
        if not post_context:
            # Пробуем восстановить из storage
            async with AsyncFileManager(STORAGE_PATH) as storage:
                storage_data = await storage.read()
                if post_id in storage_data:
                    post_info = storage_data[post_id]
                    message_ids = post_info.get('message_ids', [])
                    post_context = PostContext(
                        post_id=post_id,
                        chat_id=post_info['chat_id'],
                        message_id=message_ids[0] if message_ids else None,
                        state=BotState.POST_VIEW,
                        original_text=post_info['text'],
                        original_media=message_ids[:-1] if message_ids else []
                    )
                    self.state_manager.set_post_context(post_id, post_context)
        if post_context:
            # Удаляем сообщения с медиа
            for message_id in post_context.original_media:
                try:
                    await context.bot.delete_message(
                        chat_id=post_context.chat_id,
                        message_id=message_id
                    )
                except Exception as e:
                    logger.error(f"[delete_post_and_messages_by_id] Ошибка при удалении сообщения {message_id}: {e}")
            
            # Удаляем все служебные сообщения
            for message_id in getattr(post_context, 'service_messages', []):
                try:
                    await context.bot.delete_message(
                        chat_id=post_context.chat_id,
                        message_id=message_id
                    )
                except Exception as e:
                    logger.error(f"[delete_post_and_messages_by_id] Ошибка при удалении служебного сообщения {message_id}: {e}")
            
            # Удаляем все пользовательские сообщения
            for message_id in getattr(post_context, 'user_message_ids', []):
                try:
                    await context.bot.delete_message(
                        chat_id=post_context.chat_id,
                        message_id=message_id
                    )
                except Exception as e:
                    logger.error(f"[delete_post_and_messages_by_id] Ошибка при удалении пользовательского сообщения {message_id}: {e}")
            
            # Удаляем сообщение с клавиатурой (если оно ещё есть)
            if moderator_message:
                try:
                    await moderator_message.delete()
                    logger.info(f"Удалено сообщение с клавиатурой ID: {moderator_message.message_id}")
                except Exception as e:
                    logger.error(f"Ошибка при удалении сообщения с клавиатурой: {e}", exc_info=True)
            
            # Удаляем директорию поста и файлы
            post_dir = os.path.join(SAVED_DIR, post_id)
            if os.path.exists(post_dir):
                logger.info(f"Удаление файлов поста из директории: {post_dir}")
                try:
                    import shutil
                    shutil.rmtree(post_dir)
                    logger.info(f"Удалена директория {post_dir}")
                except Exception as e:
                    logger.error(f"[delete_post_and_messages_by_id] Ошибка при удалении файлов поста: {e}", exc_info=True)
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
                    logger.info(f"[delete_post_and_messages_by_id] Информация о посте {post_id} удалена из storage")
                else:
                    logger.warning(f"Пост {post_id} не найден в storage для удаления")
            
            # Очищаем контекст
            logger.info("Очистка контекста поста")
            self.state_manager.clear_post_context(post_id)
            
            # Отправляем уведомление об удалении
            logger.info("Отправка уведомления об удалении")
            await context.bot.send_message(
                chat_id=post_context.chat_id,
                text=f"✅ Пост успешно опубликован в каналах"
            )
            
            logger.info("=== Завершение обработки callback-запроса на удаление ===")

    async def handle_publish_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обработчик callback-запросов для публикации поста.
        """
        query = update.callback_query
        await query.answer()
        logger.info("=== Начало обработки callback-запроса на публикацию ===")
        try:
            callback_data = query.data
            if not callback_data.startswith("publish_post_"):
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Неверный формат данных"
                )
                return
            post_id = callback_data.replace("publish_post_", "")
            if not post_id:
                await context.bot.send_message(
                    chat_id=query.message.chat_id,
                    text="❌ Не удалось определить ID поста"
                )
                return
            if await self.publish_post(post_id, context):
                try:
                    await query.message.delete()
                except Exception as e:
                    logger.error(f"Ошибка при удалении сообщения с клавиатурой: {e}", exc_info=True)
                # Вместо служебного сообщения вызываем новый метод автозачистки
                await self._delete_post_and_messages_by_id(post_id, context, query.message)
                logger.info(f"Пост {post_id} удалён после публикации (автоматически)")
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

    async def handle_edit(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик нажатия на кнопку 'Редактировать' или 'Назад' из меню медиа."""
        logger.info("=== Начало обработки callback-запроса на редактирование ===")
        
        query = update.callback_query
        await query.answer()
        
        # Корректно извлекаем post_id
        post_id = query.data[len("edit_ "):] if query.data.startswith("edit_ ") else query.data[len("edit_"):]
        logger.info(f"Обработка редактирования поста {post_id}")
        
        # Получаем контекст поста
        post_context = self.state_manager.get_post_context(post_id)
        logger.info(f"Текущий контекст: {post_context}")
        if not post_context:
            logger.error(f"Контекст поста {post_id} не найден")
            await query.message.edit_text("Ошибка: пост не найден")
            return
        
        # Проверяем текущее состояние
        logger.info(f"Текущее состояние поста: {post_context.state}")
        allowed_states = [
            BotState.POST_VIEW, BotState.MODERATE_MENU,
            BotState.EDIT_MEDIA_MENU, BotState.EDIT_MEDIA_ADD_WAIT, BotState.EDIT_MEDIA_REMOVE_WAIT
        ]
        if post_context.state not in allowed_states:
            logger.error(f"Некорректное состояние для редактирования: {post_context.state}")
            await query.message.edit_text("Ошибка: некорректное состояние поста")
            return
        
        # Меняем состояние на EDIT_MENU
        old_state = post_context.state
        post_context.state = BotState.EDIT_MENU
        self.state_manager.set_post_context(post_id, post_context)
        logger.info(f"Смена состояния: {old_state} -> {post_context.state} для поста {post_id}")
        
        # Обновляем сообщение с новой клавиатурой
        msg = await query.message.edit_text(
            text="Выберите, что хотите отредактировать:",
            reply_markup=get_edit_keyboard(post_id),
            read_timeout=20,
            write_timeout=15,
            connect_timeout=15,
            pool_timeout=15
        )
        logger.info(f"Служебное сообщение с клавиатурой отправлено, message_id={msg.message_id}")
        # Сохраняем ID сообщения с клавиатурой в service_messages
        post_context.service_messages.append(msg.message_id)
        self.state_manager.set_post_context(post_id, post_context)
        
        logger.info(f"Пост {post_id} переведен в состояние {BotState.EDIT_MENU}")
        logger.info("=== Завершение обработки callback-запроса на редактирование ===")

    async def handle_edit_text_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """Обработчик нажатия на кнопку 'Текст'."""
        logger.info("=== Начало обработки callback-запроса на редактирование текста ===")
        
        query = update.callback_query
        await query.answer()
        
        # Извлекаем post_id
        post_id = query.data[len("edittext_"):]
        logger.info(f"Получен post_id: {post_id}")
        
        # Получаем контекст поста
        post_context = self.state_manager.get_post_context(post_id)
        logger.info(f"Текущий контекст: {post_context}")
        
        if not post_context:
            logger.error(f"Контекст поста {post_id} не найден")
            await query.message.edit_text("Ошибка: пост не найден")
            return
        
        # Проверяем текущее состояние
        logger.info(f"Текущее состояние поста: {post_context.state}")
        if post_context.state != BotState.EDIT_MENU:
            logger.error(f"Некорректное состояние для редактирования текста: {post_context.state}")
            await query.message.edit_text("Ошибка: некорректное состояние поста")
            return
        
        # Меняем состояние на EDIT_TEXT_WAIT
        old_state = post_context.state
        post_context.state = BotState.EDIT_TEXT_WAIT
        self.state_manager.set_post_context(post_id, post_context)
        logger.info(f"Смена состояния: {old_state} -> {post_context.state} для поста {post_id}")
        
        # Отправляем служебное сообщение и сохраняем его ID
        message = await context.bot.send_message(
            chat_id=post_context.chat_id,
            text="Введите новый текст для поста:"
        )
        post_context.service_messages.append(message.message_id)
        self.state_manager.set_post_context(post_id, post_context)
        logger.info(f"ID служебного сообщения {message.message_id} сохранен")
        
        logger.info("Отправлено сообщение с запросом нового текста")
        logger.info(f"Пост {post_id} переведен в состояние {BotState.EDIT_TEXT_WAIT}")
        logger.info("=== Завершение обработки callback-запроса на редактирование текста ===")

    async def handle_edit_media_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обработчик callback-запроса для кнопки "Медиа" (editmedia_{post_id})
        Переводит пост в состояние EDIT_MEDIA_MENU и показывает меню "Добавить/Удалить".
        """
        query = update.callback_query
        await query.answer()
        post_id = query.data[len("editmedia_"):]
        logger.info(f"=== Начало обработки editmedia для поста {post_id} ===")
        logger.info(f"Получен callback_data: {query.data}")
        logger.info(f"Ожидаемый формат: editmedia_{post_id}")
        
        post_context = self.state_manager.get_post_context(post_id)
        logger.info(f"Текущий контекст: {post_context}")
        if not post_context:
            logger.error(f"Контекст поста {post_id} не найден")
            await query.message.edit_text("Ошибка: пост не найден")
            return
        
        logger.info(f"Текущее состояние поста: {post_context.state}")
        logger.info(f"Перевод поста в состояние {BotState.EDIT_MEDIA_MENU}")
        old_state = post_context.state
        post_context.state = BotState.EDIT_MEDIA_MENU
        self.state_manager.set_post_context(post_id, post_context)
        logger.info(f"Смена состояния: {old_state} -> {post_context.state} для поста {post_id}")
        
        logger.info("Отправка меню редактирования медиа")
        await query.message.edit_text(
            text="Выберите действие с медиа:",
            reply_markup=get_media_edit_keyboard(post_id)
        )
        logger.info(f"=== Завершение обработки editmedia для поста {post_id} ===")

    async def handle_add_media_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обработчик callback-запроса для кнопки "Добавить" (addmedia_{post_id})
        Переводит пост в состояние EDIT_MEDIA_ADD_WAIT и сообщает, сколько фото можно добавить.
        """
        query = update.callback_query
        await query.answer()
        post_id = query.data[len("addmedia_"):]
        logger.info(f"=== Начало обработки addmedia для поста {post_id} ===")
        logger.info(f"Получен callback_data: {query.data}")
        logger.info(f"Ожидаемый формат: addmedia_{post_id}")
        
        post_context = self.state_manager.get_post_context(post_id)
        logger.info(f"Текущий контекст: {post_context}")
        if not post_context:
            logger.error(f"Контекст поста {post_id} не найден")
            await query.message.edit_text("Ошибка: пост не найден")
            return
        
        logger.info(f"Текущее состояние поста: {post_context.state}")
        logger.info(f"Перевод поста в состояние {BotState.EDIT_MEDIA_ADD_WAIT}")
        old_state = post_context.state
        post_context.state = BotState.EDIT_MEDIA_ADD_WAIT
        self.state_manager.set_post_context(post_id, post_context)
        logger.info(f"Смена состояния: {old_state} -> {post_context.state} для поста {post_id}")
        
        # Считаем, сколько фото уже есть
        post_dir = os.path.join(SAVED_DIR, post_id)
        old_photos = [f for f in os.listdir(post_dir) if f.startswith("photo_") and f.endswith(".jpg")]
        max_to_add = 10 - len(old_photos)
        logger.info(f"Текущее количество фото: {len(old_photos)}")
        logger.info(f"Можно добавить ещё фото: {max_to_add}")
        
        msg = await context.bot.send_message(
            chat_id=post_context.chat_id,
            text=f"Отправьте новые фото для поста (можно загрузить ещё {max_to_add} фото):"
        )
        logger.info(f"Служебное сообщение отправлено, message_id={msg.message_id}")
        post_context.service_messages.append(msg.message_id)
        self.state_manager.set_post_context(post_id, post_context)
        logger.info(f"=== Завершение обработки addmedia для поста {post_id} ===")

    async def handle_remove_media_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обработчик callback-запроса для кнопки "Удалить" (removemedia_{post_id})
        Переводит пост в состояние EDIT_MEDIA_REMOVE_WAIT и показывает сообщение о выборе фото для удаления.
        """
        query = update.callback_query
        await query.answer()
        post_id = query.data[len("removemedia_"):]
        logger.info(f"=== Начало обработки removemedia для поста {post_id} ===")
        logger.info(f"Получен callback_data: {query.data}")
        logger.info(f"Ожидаемый формат: removemedia_{post_id}")
        
        post_context = self.state_manager.get_post_context(post_id)
        logger.info(f"Текущий контекст: {post_context}")
        if not post_context:
            logger.error(f"Контекст поста {post_id} не найден")
            await query.message.edit_text("Ошибка: пост не найден")
            return
        
        logger.info(f"Текущее состояние поста: {post_context.state}")
        logger.info(f"Перевод поста в состояние {BotState.EDIT_MEDIA_REMOVE_WAIT}")
        old_state = post_context.state
        post_context.state = BotState.EDIT_MEDIA_REMOVE_WAIT
        self.state_manager.set_post_context(post_id, post_context)
        logger.info(f"Смена состояния: {old_state} -> {post_context.state} для поста {post_id}")
        
        # Получаем список фото
        post_dir = os.path.join(SAVED_DIR, post_id)
        photos = [f for f in os.listdir(post_dir) if f.startswith("photo_") and f.endswith(".jpg")]
        photos.sort(key=lambda x: int(x.split('_')[1].split('.')[0]))
        
        if not photos:
            await query.message.edit_text(
                text="В этом посте нет фото для удаления.",
                reply_markup=get_media_edit_keyboard(post_id)
            )
            post_context.state = BotState.EDIT_MEDIA_MENU
            self.state_manager.set_post_context(post_id, post_context)
            return
        
        # Формируем сообщение со списком фото
        message = "Выберите номера фото для удаления (через пробел):\n\n"
        for i, photo in enumerate(photos, 1):
            message += f"{i}. {photo}\n"
        
        msg = await context.bot.send_message(
            chat_id=post_context.chat_id,
            text=message
        )
        post_context.service_messages.append(msg.message_id)
        self.state_manager.set_post_context(post_id, post_context)
        
        logger.info(f"=== Завершение обработки removemedia для поста {post_id} ===")

def main():
    """Запуск бота."""
    try:
        logger.info("Starting bot...")
        bot = Bot()
        
        # Запускаем бота
        bot.application.run_polling(allowed_updates=Update.ALL_TYPES)
    except Exception as e:
        logger.error(f"Error starting bot: {e}", exc_info=True)
        raise


if __name__ == "__main__":
    try:
        main() 
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
