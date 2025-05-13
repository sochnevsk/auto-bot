from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
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
    CONFIRM_DELETE = auto()
    QUICK_DELETE = auto()

@dataclass
class PostContext:
    post_id: str
    chat_id: int
    message_id: int
    state: State
    temp_text: Optional[str] = None
    temp_media: Optional[List[str]] = None

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
        
        data = query.data.split('_')
        action = data[0]
        post_id = data[1]
        
        if post_id not in self.posts:
            self.posts[post_id] = PostContext(
                post_id=post_id,
                chat_id=query.message.chat_id,
                message_id=query.message.message_id,
                state=State.POST_VIEW
            )
        
        post_context = self.posts[post_id]
        
        # Обработка действий в зависимости от состояния
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
        elif action == "confirm":
            await self._handle_confirm(query, post_context, context)
        elif action == "cancel":
            await self._handle_cancel(query, post_context)

    async def _show_moderate_menu(self, query: CallbackQuery, post_context: PostContext):
        """Показать меню модерации"""
        keyboard = get_moderate_keyboard(post_context.post_id)
        await query.message.edit_reply_markup(reply_markup=keyboard)
        post_context.state = State.MODERATE_MENU

    async def _show_quick_delete_confirm(self, query: CallbackQuery, post_context: PostContext):
        """Показать подтверждение быстрого удаления"""
        keyboard = get_confirm_keyboard("quick_delete", post_context.post_id)
        await query.message.edit_reply_markup(reply_markup=keyboard)
        post_context.state = State.QUICK_DELETE

    async def _show_publish_confirm(self, query: CallbackQuery, post_context: PostContext):
        """Показать подтверждение публикации"""
        keyboard = get_confirm_keyboard("publish", post_context.post_id)
        await query.message.edit_reply_markup(reply_markup=keyboard)
        post_context.state = State.CONFIRM_PUBLISH

    async def _show_edit_menu(self, query: CallbackQuery, post_context: PostContext):
        """Показать меню редактирования"""
        keyboard = get_edit_keyboard(post_context.post_id)
        await query.message.edit_reply_markup(reply_markup=keyboard)
        post_context.state = State.EDIT_MENU

    async def _show_text_edit(self, query: CallbackQuery, post_context: PostContext):
        """Показать меню редактирования текста"""
        await query.message.reply_text("Отправьте новый текст")
        post_context.state = State.EDIT_TEXT_WAIT

    async def _show_media_edit(self, query: CallbackQuery, post_context: PostContext):
        """Показать меню редактирования медиа"""
        keyboard = get_media_edit_keyboard(post_context.post_id)
        await query.message.edit_reply_markup(reply_markup=keyboard)
        post_context.state = State.EDIT_MEDIA_MENU

    async def _handle_confirm(self, query: CallbackQuery, post_context: PostContext, context: ContextTypes.DEFAULT_TYPE):
        """Обработка подтверждения действия"""
        action = query.data.split('_')[1]
        
        if action == "publish":
            # Публикуем пост
            await query.message.edit_reply_markup(reply_markup=None)
            moderator_name = query.from_user.full_name
            await query.message.reply_text(f"Пост опубликован модератором {moderator_name}")
            del self.posts[post_context.post_id]
            
        elif action in ["delete", "quick_delete"]:
            # Удаляем пост и все связанные сообщения
            await context.bot.delete_message(
                chat_id=post_context.chat_id,
                message_id=post_context.message_id
            )
            
            # Удаляем все фото
            if post_context.temp_media:
                for media_id in post_context.temp_media:
                    try:
                        await context.bot.delete_message(
                            chat_id=post_context.chat_id,
                            message_id=media_id
                        )
                    except Exception as e:
                        logging.error(f"Error deleting media {media_id}: {e}")
            
            del self.posts[post_context.post_id]

    async def _handle_cancel(self, query: CallbackQuery, post_context: PostContext):
        """Обработка отмены действия"""
        if post_context.state == State.CONFIRM_PUBLISH:
            await self._show_moderate_menu(query, post_context)
        elif post_context.state == State.QUICK_DELETE:
            keyboard = get_post_keyboard(post_context.post_id)
            await query.message.edit_reply_markup(reply_markup=keyboard)
            post_context.state = State.POST_VIEW

    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Обработка текстовых сообщений"""
        message = update.message
        
        # Находим пост в состоянии ожидания текста
        post_context = next(
            (p for p in self.posts.values() if p.state == State.EDIT_TEXT_WAIT),
            None
        )
        
        if post_context:
            post_context.temp_text = message.text
            keyboard = get_confirm_keyboard("edit_text", post_context.post_id)
            await message.reply_text(
                "Сохранить новый текст?",
                reply_markup=keyboard
            )
            post_context.state = State.EDIT_TEXT_CONFIRM
            return

def setup_handlers(application: Application):
    post_handler = PostHandler()
    
    application.add_handler(CallbackQueryHandler(
        post_handler.handle_callback,
        pattern=r"^(moderate|quick_delete|publish|edit|delete|confirm|cancel)_"
    ))
    
    application.add_handler(MessageHandler(
        filters.TEXT & ~filters.COMMAND,
        post_handler.handle_message
    )) 