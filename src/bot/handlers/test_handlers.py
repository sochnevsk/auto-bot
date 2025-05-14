from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from telegram.ext import (
    Application,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
from enum import Enum, auto
from dataclasses import dataclass
from typing import Dict, Optional, List
import logging

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class State(Enum):
    POST_VIEW = auto()
    MODERATE_MENU = auto()
    CONFIRM_PUBLISH = auto()
    EDIT_MENU = auto()
    EDIT_TEXT_WAIT = auto()
    EDIT_TEXT_CONFIRM = auto()
    EDIT_MEDIA_MENU = auto()
    EDIT_MEDIA_ADD_WAIT = auto()
    EDIT_MEDIA_ADD_CONFIRM = auto()
    EDIT_MEDIA_REMOVE_WAIT = auto()
    EDIT_MEDIA_REMOVE_CONFIRM = auto()
    CONFIRM_DELETE = auto()
    QUICK_DELETE = auto()

@dataclass
class PostContext:
    post_id: str
    chat_id: int
    message_id: int
    state: State
    user_id: Optional[int] = None
    temp_text: Optional[str] = None
    temp_media: Optional[List[str]] = None
    media_to_remove: Optional[List[int]] = None

def get_post_keyboard(post_id: str) -> InlineKeyboardMarkup:
    """Клавиатура под постом (две кнопки верхнего уровня)"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Модерировать", callback_data=f"moderate_{post_id}"),
            InlineKeyboardButton("❌ Удалить", callback_data=f"quick_delete_{post_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_moderate_keyboard(post_id: str) -> InlineKeyboardMarkup:
    """Клавиатура меню модерации"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Опубликовать", callback_data=f"publish_{post_id}"),
            InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_{post_id}")
        ],
        [
            InlineKeyboardButton("❌ Удалить", callback_data=f"delete_{post_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_edit_keyboard(post_id: str) -> InlineKeyboardMarkup:
    """Клавиатура меню редактирования"""
    keyboard = [
        [
            InlineKeyboardButton("Текст", callback_data=f"edit_text_{post_id}"),
            InlineKeyboardButton("🖼 Медиа", callback_data=f"edit_media_{post_id}")
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data=f"moderate_{post_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_media_edit_keyboard(post_id: str) -> InlineKeyboardMarkup:
    """Клавиатура редактирования медиа"""
    keyboard = [
        [
            InlineKeyboardButton("Добавить", callback_data=f"add_media_{post_id}"),
            InlineKeyboardButton("Удалить", callback_data=f"remove_media_{post_id}")
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data=f"edit_{post_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

def get_confirm_keyboard(action: str, post_id: str) -> InlineKeyboardMarkup:
    """Клавиатура подтверждения действия"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Да", callback_data=f"confirm_{action}_{post_id}"),
            InlineKeyboardButton("❌ Нет", callback_data=f"cancel_{action}_{post_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

class PostHandler:
    def __init__(self):
        self.posts: Dict[str, PostContext] = {}
        
    async def handle_callback(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        query = update.callback_query
        await query.answer()

        data = query.data
        if data.startswith("confirm_") or data.startswith("cancel_"):
            # Корректно извлекаем post_id
            if "_post_" in data:
                post_id = "post_" + data.split("_post_")[-1]
            else:
                post_id = data.split("_")[-1]
            if post_id not in self.posts:
                logging.warning(f"Post {post_id} not found for {data}")
                return
            if data.startswith("confirm_"):
                await self._handle_confirm(query, self.posts[post_id], context)
            else:
                await self._handle_cancel(query, self.posts[post_id])
            return
        if "_post_" in data:
            action, post_id = data.rsplit("_post_", 1)
            post_id = f"post_{post_id}"
            action = action.rstrip("_")
        else:
            parts = data.split("_")
            action = "_".join(parts[:-1])
            post_id = parts[-1]

        if post_id not in self.posts:
            logging.warning(f"Post {post_id} not found")
            return

        post_context = self.posts[post_id]
        
        if action == "moderate":
            await self._show_moderate_menu(query, post_context)
        elif action == "quick_delete":
            await self._show_quick_delete_confirm(query, post_context)
        elif action == "publish":
            await self._show_publish_confirm(query, post_context)
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

    async def _show_moderate_menu(self, query: CallbackQuery, post_context: PostContext):
        """Показать меню модерации"""
        post_context.state = State.MODERATE_MENU
        keyboard = get_moderate_keyboard(post_context.post_id)
        await query.message.edit_reply_markup(reply_markup=keyboard)

    async def _show_quick_delete_confirm(self, query: CallbackQuery, post_context: PostContext):
        """Показать подтверждение быстрого удаления"""
        post_context.state = State.QUICK_DELETE
        keyboard = get_confirm_keyboard("quick_delete", post_context.post_id)
        await query.message.edit_reply_markup(reply_markup=keyboard)

    async def _show_publish_confirm(self, query: CallbackQuery, post_context: PostContext):
        """Показать подтверждение публикации"""
        post_context.state = State.CONFIRM_PUBLISH
        keyboard = get_confirm_keyboard("publish", post_context.post_id)
        await query.message.edit_reply_markup(reply_markup=keyboard)

    async def _show_edit_menu(self, query: CallbackQuery, post_context: PostContext):
        """Показать меню редактирования"""
        post_context.state = State.EDIT_MENU
        keyboard = get_edit_keyboard(post_context.post_id)
        await query.message.edit_reply_markup(reply_markup=keyboard)

    async def _show_text_edit(self, query: CallbackQuery, post_context: PostContext):
        """Показать меню редактирования текста"""
        post_context.state = State.EDIT_TEXT_WAIT
        await query.message.reply_text("Отправьте новый текст")

    async def _show_media_edit(self, query: CallbackQuery, post_context: PostContext):
        """Показать меню редактирования медиа"""
        post_context.state = State.EDIT_MEDIA_MENU
        keyboard = get_media_edit_keyboard(post_context.post_id)
        await query.message.edit_reply_markup(reply_markup=keyboard)

    async def _show_add_media(self, query: CallbackQuery, post_context: PostContext):
        """Показать меню добавления медиа"""
        post_context.state = State.EDIT_MEDIA_ADD_WAIT
        await query.message.reply_text("Отправьте новые фотографии")

    async def _show_remove_media(self, query: CallbackQuery, post_context: PostContext):
        """Показать меню удаления медиа"""
        post_context.state = State.EDIT_MEDIA_REMOVE_WAIT
        await query.message.reply_text("Отправьте номера фотографий для удаления через запятую")

    async def _handle_confirm(self, query: CallbackQuery, post_context: PostContext, context: ContextTypes.DEFAULT_TYPE = None):
        action = query.data[len("confirm_"):].rsplit("_post_", 1)[0]
        if post_context is None:
            logging.warning(f"[FSM] confirm: post_context not found for action={action}")
            return
        if action == "edit_text":
            post_context.temp_text = None
            post_context.state = State.POST_VIEW
            self.posts[post_context.post_id] = post_context
            return
        elif action == "add_media":
            post_context.temp_media = []
            post_context.state = State.POST_VIEW
            self.posts[post_context.post_id] = post_context
            return
        elif action == "remove_media":
            # Очищаем temp_media, если media_to_remove не пустой
            if post_context.media_to_remove:
                post_context.temp_media = []
            post_context.media_to_remove = []
            post_context.state = State.POST_VIEW
            self.posts[post_context.post_id] = post_context
            return
        elif action == "publish":
            if post_context.post_id in self.posts:
                del self.posts[post_context.post_id]
            return
        elif action == "quick_delete":
            if post_context.post_id in self.posts:
                del self.posts[post_context.post_id]
            return
        elif action == "delete":
            if post_context.post_id in self.posts:
                del self.posts[post_context.post_id]
            return
        else:
            logging.warning(f"[FSM] Неизвестное действие confirm: {action}")
            return

    async def _handle_cancel(self, query: CallbackQuery, post_context: PostContext):
        action = query.data[len("cancel_"):].rsplit("_post_", 1)[0]
        if action == "edit_text":
            post_context.temp_text = None  # Сбросить временный текст при отмене
            post_context.state = State.EDIT_MENU
            return
        elif action in ["add_media", "remove_media"]:
            post_context.state = State.EDIT_MEDIA_MENU
            return
        elif action == "publish":
            post_context.state = State.POST_VIEW
            return
        elif action == "quick_delete":
            keyboard = get_post_keyboard(post_context.post_id)
            await query.message.edit_reply_markup(reply_markup=keyboard)
            post_context.state = State.POST_VIEW
            return
        else:
            # Для всех остальных состояний возвращаемся в меню модерации
            await self._show_moderate_menu(query, post_context)

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений"""
        message = update.message
        
        # Находим пост в состоянии ожидания текста или медиа
        post_context = next(
            (p for p in self.posts.values() 
             if p.state in [State.EDIT_TEXT_WAIT, State.EDIT_MEDIA_ADD_WAIT, State.EDIT_MEDIA_REMOVE_WAIT]),
            None
        )
        
        if not post_context:
            return
            
        # Проверяем, что сообщение от того же пользователя
        if message.from_user.id != post_context.user_id:
            await message.reply_text(
                "Пожалуйста, отправляйте сообщения только вы, как модератор"
            )
            return
            
        if post_context.state == State.EDIT_TEXT_WAIT:
            post_context.temp_text = message.text
            keyboard = get_confirm_keyboard("edit_text", post_context.post_id)
            await message.reply_text(
                "Сохранить новый текст?",
                reply_markup=keyboard
            )
            post_context.state = State.EDIT_TEXT_CONFIRM
            
        elif post_context.state == State.EDIT_MEDIA_ADD_WAIT:
            if message.photo:
                # Сохраняем новые фото
                new_photos = []
                for photo in message.photo:
                    try:
                        file = await photo.get_file()
                        path = f"saved/{post_context.post_id}/photo_{len(post_context.temp_media or []) + len(new_photos) + 1}.jpg"
                        await file.download_to_drive(path)
                        new_photos.append(path)
                        logging.info(f"Saved photo to {path}")
                    except Exception as e:
                        logging.error(f"Error saving photo: {e}")
                        await message.reply_text(
                            "Произошла ошибка при сохранении фотографии"
                        )
                        return
                
                if not new_photos:
                    await message.reply_text(
                        "Не удалось сохранить ни одной фотографии"
                    )
                    return
                    
                # Обновляем список медиа
                if post_context.temp_media is None:
                    post_context.temp_media = []
                post_context.temp_media.extend(new_photos)
                
                # Показываем подтверждение
                keyboard = get_confirm_keyboard("add_media", post_context.post_id)
                await message.reply_text(
                    f"Добавлено {len(new_photos)} фотографий. Сохранить изменения?",
                    reply_markup=keyboard
                )
                post_context.state = State.EDIT_MEDIA_ADD_CONFIRM
                
        elif post_context.state == State.EDIT_MEDIA_REMOVE_WAIT:
            try:
                # Парсим номера фотографий
                numbers = [int(n.strip()) for n in message.text.split(',')]
                # Проверяем, что номера в допустимом диапазоне
                if all(1 <= n <= len(post_context.temp_media or []) for n in numbers):
                    post_context.media_to_remove = numbers
                    keyboard = get_confirm_keyboard("remove_media", post_context.post_id)
                    await message.reply_text(
                        f"Удалить фотографии {', '.join(map(str, numbers))}?",
                        reply_markup=keyboard
                    )
                    post_context.state = State.EDIT_MEDIA_REMOVE_CONFIRM
                else:
                    await message.reply_text(
                        f"Номера должны быть от 1 до {len(post_context.temp_media or [])}"
                    )
            except ValueError:
                await message.reply_text(
                    "Пожалуйста, введите номера фотографий через запятую (например: 1, 2, 3)"
                )

def setup_handlers(application: Application):
    post_handler = PostHandler()
    
    application.add_handler(CallbackQueryHandler(
        post_handler.handle_callback,
        pattern=r"^(moderate|quick_delete|publish|edit|delete|confirm|cancel|add_media|remove_media)_"
    ))
    
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        post_handler.handle_message
    ))
    
    application.add_handler(MessageHandler(
        filters.PHOTO,
        post_handler.handle_message
    )) 