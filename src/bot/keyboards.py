"""
Модуль с клавиатурами для бота.
"""
from telegram import InlineKeyboardMarkup, InlineKeyboardButton


def get_post_keyboard(post_id: str) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для поста.

    Args:
        post_id: ID поста

    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопками
    """
    keyboard = [
        [
            InlineKeyboardButton("✅ Опубликовать", callback_data=f"publish_{post_id}"),
            InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_{post_id}")
        ],
        [
            InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_{post_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_confirm_keyboard(post_id: str) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру подтверждения удаления.

    Args:
        post_id: ID поста

    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопками подтверждения
    """
    keyboard = [
        [
            InlineKeyboardButton("✅ Да, удалить", callback_data=f"confirm_{post_id}"),
            InlineKeyboardButton("❌ Нет, отмена", callback_data=f"cancel_{post_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard)


def get_moderation_keyboard(post_id: str) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру модерации.

    Args:
        post_id: ID поста

    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопками модерации
    """
    keyboard = [
        [
            InlineKeyboardButton("✅ Опубликовать", callback_data=f"publish_{post_id}"),
            InlineKeyboardButton("✏️ Редактировать", callback_data=f"edit_{post_id}")
        ],
        [
            InlineKeyboardButton("🗑 Удалить", callback_data=f"delete_{post_id}")
        ],
        [
            InlineKeyboardButton("⬅️ Назад", callback_data=f"cancel_{post_id}")
        ]
    ]
    return InlineKeyboardMarkup(keyboard) 