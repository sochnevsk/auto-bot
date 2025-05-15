"""
Модуль с клавиатурами для бота.
"""
from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from typing import List, Dict, Optional


def get_post_keyboard(post_id: str) -> InlineKeyboardMarkup:
    """Клавиатура под постом (две кнопки верхнего уровня)"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Модерировать", callback_data=f"moderate_{post_id}"),
            InlineKeyboardButton("❌ Удалить", callback_data=f"delete_{post_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_moderate_keyboard(post_id: str) -> InlineKeyboardMarkup:
    """Клавиатура меню модерации"""
    keyboard = [
        [
            InlineKeyboardButton("✅ Опубликовать", callback_data=f"publish_post_{post_id}"),
            InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_{post_id}")
        ],
        [
            InlineKeyboardButton("❌ Удалить", callback_data=f"delete_{post_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_edit_keyboard(post_id: str) -> InlineKeyboardMarkup:
    """Создает клавиатуру для редактирования поста"""
    keyboard = [
        [
            InlineKeyboardButton("Текст", callback_data=f"edittext_{post_id}"),
            InlineKeyboardButton("Медиа", callback_data=f"editmedia_{post_id}")
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
            InlineKeyboardButton("Добавить", callback_data=f"addmedia_{post_id}"),
            InlineKeyboardButton("Удалить", callback_data=f"removemedia_{post_id}")
        ],
        [
            InlineKeyboardButton("🔙 Назад", callback_data=f"edit_{post_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)

#