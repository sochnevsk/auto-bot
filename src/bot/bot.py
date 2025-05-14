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

from src.config.settings import settings
from src.utils.logger import setup_logger
from src.bot.keyboards import (
    get_post_keyboard,
    get_confirm_keyboard,
    get_edit_keyboard,
    get_media_edit_keyboard,
    get_text_edit_keyboard,
    get_media_add_confirm_keyboard,
    get_media_remove_confirm_keyboard,
    get_moderate_keyboard
)
from src.bot.storage import AsyncFileManager
from src.bot.states import BotState, StateManager, PostContext

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
        logger.info("Setting up command handlers...")
        
        # Обработчик команды /test
        self.application.add_handler(CommandHandler("test", self.test_command))
        logger.info("Added /test command handler")
        
        # Обработчик callback-запросов
        self.application.add_handler(CallbackQueryHandler(self.handle_callback))
        logger.info("Added callback query handler")
        
        # Обработчик текстовых сообщений
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        logger.info("Added message handler")
        
        logger.info("Command handlers setup completed")

    async def is_post_sent(self, post_id: str) -> bool:
        """Проверяет, был ли пост уже отправлен."""
        async with AsyncFileManager(STORAGE_PATH) as storage:
            data = await storage.read()
            return post_id in data and data[post_id].get("status") == "sent"

    async def process_post(self, post_dir: str, context: ContextTypes.DEFAULT_TYPE, update: Update = None) -> bool:
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
                
                logger.info(f"Message IDs from media group: {[msg.message_id for msg in messages]}")
                logger.info(f"Keyboard message ID: {keyboard_message.message_id}")
                logger.info(f"All message IDs: {message_ids}")

                # user_id из update
                user_id = 0
                if update and update.effective_user:
                    user_id = update.effective_user.id
                post_context = PostContext(
                    post_id=post_id,
                    chat_id=settings.MODERATOR_GROUP_ID,
                    message_id=messages[0].message_id,
                    state=BotState.POST_VIEW,
                    user_id=user_id,
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

    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()
        data = query.data
        import re
        # Универсальный парсер confirm/cancel + post_id
        m = re.match(r"(confirm|cancel)_(.+)_post_(.+)", data)
        if m:
            action_type, action, post_id = m.groups()
            post_id = f"post_{post_id}" if not post_id.startswith("post_") else post_id
            post_context = self.state_manager.get_post_context(post_id)
            if not post_context:
                logger.warning(f"[CALLBACK] Post {post_id} not found for {data}")
                # Для confirm/cancel не падать, просто возвращать
                return
            if action_type == "confirm":
                await self._handle_confirm(query, post_context, context, action)
            else:
                await self._handle_cancel(query, post_context, context, action)
            return
        # Старый парсер для остальных действий
        if "_post_" in data:
            action, post_id = data.rsplit("_post_", 1)
            post_id = f"post_{post_id}"
            action = action.rstrip("_")
        else:
            parts = data.split("_")
            action = "_".join(parts[:-1])
            post_id = parts[-1]
        logger.info(f"[CALLBACK] action={action}, post_id={post_id}")
        post_context = self.state_manager.get_post_context(post_id)
        if not post_context:
            logger.warning(f"[CALLBACK] Post {post_id} not found for action {action}")
            return
        # FSM-ветки
        if action == "moderate":
            await self._show_moderate_menu(query, post_context)
        elif action == "edit":
            await self._show_edit_menu(query, post_context)
        elif action == "edit_text":
            await self._show_text_edit(query, post_context)
        elif action == "edit_media":
            await self._show_media_edit(query, post_context)
        elif action == "add_media":
            await self._show_add_media(query, post_context)
        elif action == "remove_media":
            await self._show_remove_media(query, post_context)
        elif action == "publish":
            await self._show_publish_confirm(query, post_context)
        elif action in ("quick_delete", "quickdelete"):
            await self._handle_quick_delete(query, post_context, context)
        elif action == "delete":
            await self._show_delete_confirm(query, post_context)
        # ... остальные ветки ...

    async def _show_moderate_menu(self, query: CallbackQuery, post_context: PostContext):
        """Показать меню модерации"""
        keyboard = get_moderate_keyboard(post_context.post_id)
        try:
            await query.message.edit_reply_markup(reply_markup=keyboard)
        except Exception as e:
            if 'Message is not modified' in str(e):
                logger.warning(f"[FSM] Message is not modified for post {post_context.post_id}")
            else:
                logger.error(f"Ошибка при изменении клавиатуры: {e}")
        post_context.state = BotState.MODERATE_MENU
        self.state_manager.set_post_context(post_context.post_id, post_context)

    async def _show_quick_delete_confirm(self, query: CallbackQuery, post_context: PostContext):
        """Показать подтверждение быстрого удаления"""
        keyboard = get_confirm_keyboard("quick_delete", post_context.post_id)
        await query.message.edit_reply_markup(reply_markup=keyboard)
        post_context.state = BotState.QUICK_DELETE
        self.state_manager.set_post_context(post_context.post_id, post_context)

    async def _show_delete_confirm(self, query: CallbackQuery, post_context: PostContext):
        """Показать подтверждение удаления"""
        keyboard = get_confirm_keyboard("delete", post_context.post_id)
        try:
            await query.message.edit_reply_markup(reply_markup=keyboard)
        except Exception as e:
            if 'Message is not modified' in str(e):
                logger.warning(f"[FSM] Message is not modified for post {post_context.post_id}")
            else:
                logger.error(f"Ошибка при изменении клавиатуры: {e}")
        post_context.state = BotState.CONFIRM_DELETE
        self.state_manager.set_post_context(post_context.post_id, post_context)

    async def _show_publish_confirm(self, query: CallbackQuery, post_context: PostContext):
        """Показать подтверждение публикации"""
        keyboard = get_confirm_keyboard("publish", post_context.post_id)
        await query.message.edit_reply_markup(reply_markup=keyboard)
        post_context.state = BotState.CONFIRM_PUBLISH
        self.state_manager.set_post_context(post_context.post_id, post_context)

    async def _show_edit_menu(self, query: CallbackQuery, post_context: PostContext):
        """Показать меню редактирования"""
        logger.info(f"Showing edit menu for post {post_context.post_id}")
        logger.info(f"Current post context: {post_context}")
        keyboard = get_edit_keyboard(post_context.post_id)
        try:
            await query.message.edit_reply_markup(reply_markup=keyboard)
        except Exception as e:
            if 'Message is not modified' in str(e):
                logger.warning(f"[FSM] Message is not modified for post {post_context.post_id}")
            else:
                logger.error(f"Ошибка при изменении клавиатуры: {e}")
        post_context.state = BotState.EDIT_MENU
        self.state_manager.set_post_context(post_context.post_id, post_context)
        logger.info(f"Updated post state to {BotState.EDIT_MENU}")

    async def _show_text_edit(self, query: CallbackQuery, post_context: PostContext):
        """Показать меню редактирования текста"""
        logger.info(f"Showing text edit for post {post_context.post_id}")
        logger.info(f"Current post context: {post_context}")
        try:
            await query.message.reply_text("Отправьте новый текст")
        except Exception as e:
            logger.error(f"Ошибка при отправке запроса на ввод текста: {e}")
        post_context.state = BotState.EDIT_TEXT_WAIT
        self.state_manager.set_post_context(post_context.post_id, post_context)
        logger.info(f"Updated post state to {BotState.EDIT_TEXT_WAIT}")
        
        # Сохраняем состояние и контекст в хранилище
        async with AsyncFileManager(STORAGE_PATH) as storage:
            data = await storage.read()
            logger.info(f"Current storage data: {data}")
            if post_context.post_id in data:
                data[post_context.post_id].update({
                    'state': BotState.EDIT_TEXT_WAIT,
                    'chat_id': post_context.chat_id,
                    'message_id': post_context.message_id,
                    'text': post_context.original_text,
                    'message_ids': post_context.original_media + [query.message.message_id]
                })
                logger.info(f"[FSM] (DEBUG) Перед storage.write для post {post_context.post_id}")
                await storage.write(data)
                assert False, "storage.write(data) не выбросил исключение!"
                logger.info(f"[FSM] (DEBUG) После storage.write для post {post_context.post_id}")
                logger.info(f"Updated text in storage for post {post_context.post_id}")
                logger.info(f"Updated storage data: {data}")

    async def _show_media_edit(self, query: CallbackQuery, post_context: PostContext):
        """Показать меню редактирования медиа"""
        keyboard = get_media_edit_keyboard(post_context.post_id)
        await query.message.edit_reply_markup(reply_markup=keyboard)
        post_context.state = BotState.EDIT_MEDIA_MENU
        self.state_manager.set_post_context(post_context.post_id, post_context)

    async def _show_add_media(self, query: CallbackQuery, post_context: PostContext):
        """Показать меню добавления медиа"""
        await query.message.reply_text("Отправьте новые фотографии")
        post_context.state = BotState.EDIT_MEDIA_ADD_WAIT
        self.state_manager.set_post_context(post_context.post_id, post_context)

    async def _show_remove_media(self, query: CallbackQuery, post_context: PostContext):
        """Показать меню удаления медиа"""
        await query.message.reply_text("Отправьте номера фотографий для удаления через запятую")
        post_context.state = BotState.EDIT_MEDIA_REMOVE_WAIT
        self.state_manager.set_post_context(post_context.post_id, post_context)

    async def _handle_confirm(self, query: CallbackQuery, post_context: PostContext, context: ContextTypes.DEFAULT_TYPE, action: str = None) -> None:
        try:
            if post_context is None:
                logger.warning(f"[FSM] confirm: post_context not found for action={action}")
                return
            logger.info(f"[FSM] CONFIRM action={action} post_id={post_context.post_id}")
            old_state = post_context.state
            valid_states = {
                "edit_text": BotState.EDIT_TEXT_CONFIRM,
                "add_media": BotState.EDIT_MEDIA_ADD_CONFIRM,
                "remove_media": BotState.EDIT_MEDIA_REMOVE_CONFIRM,
                "publish": BotState.CONFIRM_PUBLISH,
                "delete": BotState.CONFIRM_DELETE,
                "quick_delete": BotState.QUICK_DELETE,
            }
            if action not in valid_states or post_context.state != valid_states[action]:
                logger.warning(f"[FSM] confirm: invalid state {post_context.state} for action={action}")
                return
            # Удаляем клавиатуру (кнопки подтверждения)
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=post_context.chat_id,
                    message_id=post_context.message_id,
                    reply_markup=None
                )
            except Exception as e:
                logger.error(f"[FSM] Ошибка удаления клавиатуры: {e}")
            # FSM действия с обработкой ошибок
            error_occurred = False
            try:
                if action == "edit_text":
                    await self._handle_confirm_text(query, post_context, context)
                elif action == "add_media":
                    await self._handle_confirm_media_add(query, post_context, context)
                elif action == "remove_media":
                    await self._handle_confirm_media_remove(query, post_context, context)
                elif action == "publish":
                    await self._handle_confirm_publish(query, post_context, context)
                elif action == "delete":
                    await self._handle_confirm_delete(query, post_context, context)
                elif action == "quick_delete":
                    await self._handle_quick_delete(query, post_context, context)
            except Exception as e:
                logger.error(f"[FSM] Ошибка в confirm ветке: {e}")
                error_occurred = True
            finally:
                logger.info(f"[FSM] После confirm-ветки error_occurred={error_occurred}")
                logger.info(f"[FSM] Перед сменой состояния error_occurred={error_occurred}")
                if not error_occurred:
                    if action in ["edit_text", "add_media", "remove_media"]:
                        post_context.state = BotState.EDIT_MENU
                        self.state_manager.set_post_context(post_context.post_id, post_context)
                        logger.info(f"[FSM] Смена состояния post_id={post_context.post_id}: {old_state} -> edit_menu")
                    elif action in ["publish", "delete", "quick_delete"]:
                        self.state_manager.clear_post_context(post_context.post_id)
                        logger.info(f"[FSM] Очистка контекста post_id={post_context.post_id} после {action}")
                else:
                    logger.warning(f"[FSM] Ошибка при confirm {action}, состояние не меняется")
        except Exception as e:
            logger.error(f"[FSM] Ошибка в _handle_confirm: {e}")

    async def _handle_cancel(self, query: CallbackQuery, post_context: PostContext, context: ContextTypes.DEFAULT_TYPE, action: str = None) -> None:
        try:
            if post_context is None:
                logger.warning(f"[FSM] cancel: post_context not found for action={action}")
                return
            logger.info(f"[FSM] CANCEL action={action} post_id={post_context.post_id}")
            old_state = post_context.state
            valid_states = {
                "edit_text": BotState.EDIT_TEXT_CONFIRM,
                "add_media": BotState.EDIT_MEDIA_ADD_CONFIRM,
                "remove_media": BotState.EDIT_MEDIA_REMOVE_CONFIRM,
                "publish": BotState.CONFIRM_PUBLISH,
                "delete": BotState.CONFIRM_DELETE,
                "quick_delete": BotState.QUICK_DELETE,
            }
            if action not in valid_states or post_context.state != valid_states[action]:
                logger.warning(f"[FSM] cancel: invalid state {post_context.state} for action={action}")
                return
            # Удаляем клавиатуру (кнопки подтверждения)
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=post_context.chat_id,
                    message_id=post_context.message_id,
                    reply_markup=None
                )
            except Exception as e:
                logger.error(f"[FSM] Ошибка удаления клавиатуры: {e}")
            # FSM действия с обработкой ошибок
            error_occurred = False
            try:
                if action in ["edit_text", "add_media", "remove_media"]:
                    post_context.state = BotState.EDIT_MENU
                    self.state_manager.set_post_context(post_context.post_id, post_context)
                    logger.info(f"[FSM] Смена состояния post_id={post_context.post_id}: {old_state} -> edit_menu")
                elif action in ["publish", "delete", "quick_delete"]:
                    post_context.state = BotState.MODERATE_MENU
                    self.state_manager.set_post_context(post_context.post_id, post_context)
                    logger.info(f"[FSM] Смена состояния post_id={post_context.post_id}: {old_state} -> moderate_menu")
            except Exception as e:
                logger.error(f"[FSM] Ошибка в _handle_cancel: {e}")
                error_occurred = True
            if error_occurred:
                logger.warning(f"[FSM] Ошибка при cancel {action}, состояние не меняется")
        except Exception as e:
            logger.error(f"[FSM] Ошибка в _handle_cancel: {e}")

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений"""
        message = update.message
        logger.info(f"Received message: {message.text}")
        
        # Находим пост в состоянии ожидания текста или медиа
        post_context = next(
            (p for p in self.state_manager._posts.values() 
             if p.state in [BotState.EDIT_TEXT_WAIT, BotState.EDIT_MEDIA_ADD_WAIT, BotState.EDIT_MEDIA_REMOVE_WAIT]),
            None
        )
        
        if not post_context:
            logger.info("Post context not found in state_manager, checking storage")
            # Если пост не найден в state_manager, ищем в хранилище
            async with AsyncFileManager(STORAGE_PATH) as storage:
                data = await storage.read()
                logger.info(f"Storage data: {data}")
                for post_id, post_info in data.items():
                    if post_info.get("state") in [BotState.EDIT_TEXT_WAIT, BotState.EDIT_MEDIA_ADD_WAIT, BotState.EDIT_MEDIA_REMOVE_WAIT]:
                        user_id = update.effective_user.id if update and update.effective_user else 0
                        post_context = PostContext(
                            post_id=post_id,
                            chat_id=post_info['chat_id'],
                            message_id=post_info['message_ids'][0],
                            state=post_info['state'],
                            user_id=user_id,
                            original_text=post_info['text'],
                            original_media=post_info['message_ids'][:-1]
                        )
                        self.state_manager.set_post_context(post_id, post_context)
                        logger.info(f"Restored post context from storage: {post_context}")
                        break
        
        if not post_context:
            logger.info("No post found in EDIT_TEXT_WAIT state")
            return
        
        logger.info(f"Processing message for post {post_context.post_id} in state {post_context.state}")

        # FSM переходы в *_CONFIRM состояния
        if post_context.state == BotState.EDIT_TEXT_WAIT and message.text:
            post_context.temp_text = message.text
            post_context.state = BotState.EDIT_TEXT_CONFIRM
            self.state_manager.set_post_context(post_context.post_id, post_context)
            await message.reply_text("Подтвердите изменение текста", reply_markup=get_confirm_keyboard("edit_text", post_context.post_id))
            return

        if post_context.state == BotState.EDIT_MEDIA_ADD_WAIT and message.photo:
            # Сохраняем temp_media (инициализация, если None)
            if post_context.temp_media is None:
                post_context.temp_media = []
            post_context.temp_media.extend(["mock_photo_id"] * len(message.photo))
            post_context.state = BotState.EDIT_MEDIA_ADD_CONFIRM
            self.state_manager.set_post_context(post_context.post_id, post_context)
            await message.reply_text("Подтвердите добавление медиа", reply_markup=get_confirm_keyboard("add_media", post_context.post_id))
            return

        if post_context.state == BotState.EDIT_MEDIA_REMOVE_WAIT and message.text:
            # Сохраняем media_to_remove (заглушка: парсим номера через запятую)
            try:
                numbers = [int(x.strip()) for x in message.text.split(",") if x.strip().isdigit()]
            except Exception:
                numbers = []
            post_context.media_to_remove = numbers
            post_context.state = BotState.EDIT_MEDIA_REMOVE_CONFIRM
            self.state_manager.set_post_context(post_context.post_id, post_context)
            await message.reply_text("Подтвердите удаление медиа", reply_markup=get_confirm_keyboard("remove_media", post_context.post_id))
            return

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

    async def _handle_confirm_text(self, query: CallbackQuery, post_context: PostContext, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Сохраняет новый текст поста (без смены состояния, set_post_context и вызова меню)
        """
        try:
            if not post_context.temp_text:
                logger.warning("No temp_text found in post context")
                await context.bot.send_message(
                    chat_id=post_context.chat_id,
                    text="Нет нового текста для сохранения"
                )
                return
            logger.info(f"Saving new text: {post_context.temp_text}")
            await context.bot.edit_message_caption(
                chat_id=post_context.chat_id,
                message_id=post_context.message_id,
                caption=post_context.temp_text
            )
            logger.info("Updated message caption")
            async with AsyncFileManager(STORAGE_PATH) as storage:
                data = await storage.read()
                logger.info(f"Current storage data: {data}")
                if post_context.post_id in data:
                    data[post_context.post_id]['text'] = post_context.temp_text
                    logger.info(f"[FSM] (DEBUG) Перед storage.write для post {post_context.post_id}")
                    await storage.write(data)
                    assert False, "storage.write(data) не выбросил исключение!"
                    logger.info(f"[FSM] (DEBUG) После storage.write для post {post_context.post_id}")
                    logger.info(f"Updated text in storage for post {post_context.post_id}")
                    logger.info(f"Updated storage data: {data}")
        except Exception as e:
            logger.error(f"[FSM] (EXCEPT) Ошибка в _handle_confirm_text (caption/storage): {e}")
            logger.error(f"[FSM] (EXCEPT) Пробрасываю исключение дальше из _handle_confirm_text")
            raise

    async def _handle_confirm_publish(self, query: CallbackQuery, post_context: PostContext, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Обработка подтверждения публикации поста.
        """
        logger.info(f"[FSM] _handle_confirm_publish (start): post_id={post_context.post_id}, keys={list(self.state_manager._posts.keys())}")
        try:
            logger.info(f"Publishing post with text: {post_context.original_text}")
            async with AsyncFileManager(STORAGE_PATH) as storage:
                data = await storage.read()
                post_info = data.get(post_context.post_id)
                if not post_info:
                    logger.warning(f"[FSM] RETURN: post_info not found for post_id={post_context.post_id}")
                    await context.bot.send_message(
                        chat_id=post_context.chat_id,
                        text="Ошибка: не найден пост для публикации"
                    )
                    return
            # Получаем список фото
            photo_ids = post_info['photos'] if 'photos' in post_info else []
            keyboard_message_id = post_info.get('keyboard_message_id', post_context.message_id)
            # Публикуем в открытый канал
            media_group = []
            for i, path in enumerate(photo_ids):
                if i == 0:
                    media_group.append(InputMediaPhoto(media=open(path, 'rb'), caption=post_context.original_text))
                else:
                    media_group.append(InputMediaPhoto(media=open(path, 'rb')))
            await context.bot.send_media_group(
                chat_id=settings.OPEN_CHANNEL_ID,
                media=media_group
            )
            await context.bot.send_media_group(
                chat_id=settings.CLOSED_CHANNEL_ID,
                media=media_group
            )
            moderator_name = query.from_user.full_name
            await context.bot.send_message(
                chat_id=post_context.chat_id,
                text=f"Пост опубликован модератором {moderator_name}"
            )
            # Удаляем клавиатуру у сообщения с кнопками
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=post_context.chat_id,
                    message_id=keyboard_message_id,
                    reply_markup=None
                )
                logger.info(f"Клавиатура удалена у сообщения {keyboard_message_id}")
            except Exception as e:
                logger.warning(f"Не удалось удалить клавиатуру: {e}")
            logger.info(f"[FSM] Перед clear_post_context: post_id={post_context.post_id}, keys={list(self.state_manager._posts.keys())}")
            self.state_manager.clear_post_context(post_context.post_id)
            logger.info(f"[FSM] После clear_post_context: post_id={post_context.post_id}, keys={list(self.state_manager._posts.keys())}")
            logger.info(f"[FSM] PostContext {post_context.post_id} должен быть удалён: {self.state_manager.get_post_context(post_context.post_id)}")
            logger.info(f"Post {post_context.post_id} published to both channels")
            logger.info(f"[FSM] RETURN: end of _handle_confirm_publish for post_id={post_context.post_id}")
            return
        except Exception as e:
            logger.error(f"[FSM] EXCEPTION in _handle_confirm_publish: {e}")
            await context.bot.send_message(
                chat_id=post_context.chat_id,
                text="Произошла ошибка при публикации поста"
            )
            logger.info(f"[FSM] RETURN: exception exit for post_id={post_context.post_id}")
            return

    async def _handle_quick_delete(self, query: CallbackQuery, post_context: PostContext, context: ContextTypes.DEFAULT_TYPE):
        """Быстрое удаление поста и всех связанных сообщений (аналогично обычному удалению)."""
        try:
            logger.info(f"[QUICK_DELETE] Вход в функцию для post_id={post_context.post_id}")
            message_ids = []
            keyboard_message_id = post_context.message_id
            async with AsyncFileManager(STORAGE_PATH) as storage:
                data = await storage.read()
                logger.info(f"[QUICK_DELETE] Ключи storage: {list(data.keys())}")
                post_info = data.get(post_context.post_id)
                if not post_info:
                    logger.warning(f"[QUICK_DELETE] post_info not found for {post_context.post_id}")
                else:
                    logger.info(f"[QUICK_DELETE] Найден post_info: {post_info}")
                    message_ids = post_info.get('message_ids', [])
                    keyboard_message_id = post_info.get('keyboard_message_id', post_context.message_id)
                    logger.info(f"[QUICK_DELETE] message_ids: {message_ids}")
                    if not message_ids:
                        logger.warning(f"[QUICK_DELETE] message_ids empty for {post_context.post_id}")
                    post_dir = post_info.get('dir')
                    if post_dir:
                        ready_file = os.path.join(post_dir, "ready.txt")
                        if os.path.exists(ready_file):
                            os.remove(ready_file)
                            logger.info(f"Deleted ready.txt file for post {post_context.post_id}")
            for msg_id in message_ids:
                try:
                    await context.bot.delete_message(chat_id=post_context.chat_id, message_id=msg_id)
                    logger.info(f"[QUICK_DELETE] Удалено сообщение {msg_id}")
                except Exception as e:
                    logger.warning(f"Не удалось удалить сообщение {msg_id}: {e}")
            # Удаляем клавиатуру у сообщения с кнопками
            try:
                await context.bot.edit_message_reply_markup(
                    chat_id=post_context.chat_id,
                    message_id=keyboard_message_id,
                    reply_markup=None
                )
                logger.info(f"Клавиатура удалена у сообщения {keyboard_message_id}")
            except Exception as e:
                logger.warning(f"Не удалось удалить клавиатуру: {e}")
            self.state_manager.clear_post_context(post_context.post_id)
            async with AsyncFileManager(STORAGE_PATH) as storage:
                data = await storage.read()
                if post_context.post_id in data:
                    del data[post_context.post_id]
                    await storage.write(data)
                logger.info(f"[QUICK_DELETE] post_id {post_context.post_id} удалён из storage")
            await context.bot.send_message(
                chat_id=post_context.chat_id,
                text="Пост и все связанные сообщения были быстро удалены."
            )
            logger.info(f"[QUICK_DELETE] Пост {post_context.post_id} и все сообщения удалены (quick delete)")
        except Exception as e:
            logger.error(f"Ошибка при быстром удалении поста: {e}")
            await context.bot.send_message(
                chat_id=post_context.chat_id,
                text="Произошла ошибка при быстром удалении поста."
            )

    async def _handle_confirm_delete(self, query: CallbackQuery, post_context: PostContext, context: ContextTypes.DEFAULT_TYPE):
        """Обычное удаление поста с подтверждением."""
        try:
            async with AsyncFileManager(STORAGE_PATH) as storage:
                data = await storage.read()
                post_info = data.get(post_context.post_id)
                if not post_info:
                    logger.warning(f"[FSM] confirm_delete: post_info not found for post_id={post_context.post_id}")
                    await context.bot.send_message(
                        chat_id=post_context.chat_id,
                        text="Ошибка: не найден пост для удаления"
                    )
                    return
            # Удаляем ready.txt файл
            post_dir = post_info.get('dir')
            if post_dir:
                ready_file = os.path.join(post_dir, "ready.txt")
                if os.path.exists(ready_file):
                    os.remove(ready_file)
                    logger.info(f"Deleted ready.txt file for post {post_context.post_id}")
            
            # Показываем подтверждение удаления
            keyboard = get_confirm_keyboard("delete", post_context.post_id)
            try:
                await query.message.edit_reply_markup(reply_markup=keyboard)
            except Exception as e:
                if 'Message is not modified' in str(e):
                    logger.warning(f"[FSM] Message is not modified for post {post_context.post_id}")
                else:
                    logger.error(f"Ошибка при изменении клавиатуры: {e}")
            post_context.state = BotState.CONFIRM_DELETE
            self.state_manager.set_post_context(post_context.post_id, post_context)
        except Exception as e:
            logger.error(f"Ошибка при показе подтверждения удаления: {e}")
            await context.bot.send_message(
                chat_id=post_context.chat_id,
                text="Произошла ошибка при попытке удалить пост."
            )

    async def _handle_confirm_media_add(self, query: CallbackQuery, post_context: PostContext, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Добавляет медиа к посту (без смены состояния, set_post_context и вызова меню)
        """
        try:
            if not post_context.temp_media:
                await context.bot.send_message(
                    chat_id=post_context.chat_id,
                    text="Нет новых медиа для сохранения"
                )
                return
            new_media = post_context.original_media + post_context.temp_media
            post_context.original_media = new_media
            async with AsyncFileManager(STORAGE_PATH) as storage:
                data = await storage.read()
                if post_context.post_id in data:
                    data[post_context.post_id]['message_ids'] = new_media + [data[post_context.post_id]['keyboard_message_id']]
                    await storage.write(data)
                    logger.info(f"Updated media list in storage for post {post_context.post_id}")
            await context.bot.send_message(
                chat_id=post_context.chat_id,
                text=f"Добавлено {len(post_context.temp_media)} новых фотографий"
            )
        except Exception as e:
            logger.error(f"[FSM] (EXCEPT) Ошибка в _handle_confirm_media_add (storage): {e}")
            logger.error(f"[FSM] (EXCEPT) Пробрасываю исключение дальше из _handle_confirm_media_add")
            raise

    async def _handle_confirm_media_remove(self, query: CallbackQuery, post_context: PostContext, context: ContextTypes.DEFAULT_TYPE) -> None:
        """
        Удаляет медиа из поста (без смены состояния, set_post_context и вызова меню)
        """
        try:
            if not post_context.media_to_remove:
                await context.bot.send_message(
                    chat_id=post_context.chat_id,
                    text="Нет медиа для удаления"
                )
                return
            media_to_remove = [post_context.original_media[i-1] for i in post_context.media_to_remove]
            deleted_count = 0
            for media_id in media_to_remove:
                try:
                    message = await context.bot.get_message(
                        chat_id=post_context.chat_id,
                        message_id=media_id
                    )
                    if message:
                        await context.bot.delete_message(
                            chat_id=post_context.chat_id,
                            message_id=media_id
                        )
                        deleted_count += 1
                        logger.info(f"Deleted media message {media_id}")
                except Exception as e:
                    logger.warning(f"Could not delete media {media_id}: {e}")
            if deleted_count > 0:
                new_media = [m for i, m in enumerate(post_context.original_media, 1) 
                           if i not in post_context.media_to_remove]
                post_context.original_media = new_media
                async with AsyncFileManager(STORAGE_PATH) as storage:
                    data = await storage.read()
                    if post_context.post_id in data:
                        data[post_context.post_id]['message_ids'] = new_media + [data[post_context.post_id]['keyboard_message_id']]
                        await storage.write(data)
                        logger.info(f"Updated media list in storage for post {post_context.post_id}")
                async with AsyncFileManager(STORAGE_PATH) as storage:
                    data = await storage.read()
                    post_info = data.get(post_context.post_id)
                    if post_info and 'photos' in post_info:
                        photo_ids = post_info['photos']
                        media_group = []
                        for i, path in enumerate(photo_ids):
                            if i == 0:
                                media_group.append(InputMediaPhoto(media=open(path, 'rb'), caption=post_info['text']))
                            else:
                                media_group.append(InputMediaPhoto(media=open(path, 'rb')))
                        await context.bot.send_media_group(chat_id=post_context.chat_id, media=media_group)
                await context.bot.send_message(
                    chat_id=post_context.chat_id,
                    text=f"Удалено {deleted_count} фотографий"
                )
            else:
                await context.bot.send_message(
                    chat_id=post_context.chat_id,
                    text="Не удалось удалить ни одной фотографии"
                )
        except Exception as e:
            logger.error(f"[FSM] (EXCEPT) Ошибка в _handle_confirm_media_remove (storage): {e}")
            logger.error(f"[FSM] (EXCEPT) Пробрасываю исключение дальше из _handle_confirm_media_remove")
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
        logger.info("Starting bot application")
        main()
    except KeyboardInterrupt:
        logger.info("Bot stopped by user")
    except Exception as e:
        logger.error(f"Fatal error: {e}", exc_info=True)
