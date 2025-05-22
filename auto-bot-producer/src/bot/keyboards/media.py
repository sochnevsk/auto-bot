from telegram import InlineKeyboardMarkup, InlineKeyboardButton
from typing import Union, List

def get_media_confirm_keyboard(media_paths: Union[str, List[str]]) -> InlineKeyboardMarkup:
    """
    Создает клавиатуру для подтверждения сохранения медиа.
    
    Args:
        media_paths: Путь к одному файлу или список путей к файлам
        
    Returns:
        InlineKeyboardMarkup: Клавиатура с кнопками подтверждения
    """
    if isinstance(media_paths, str):
        media_paths = [media_paths]
        
    keyboard = [
        [
            InlineKeyboardButton("✅ Подтвердить", callback_data=f"confirmmedia:{','.join(media_paths)}"),
            InlineKeyboardButton("❌ Отменить", callback_data="cancelmedia")
        ]
    ]
    
    return InlineKeyboardMarkup(keyboard) 