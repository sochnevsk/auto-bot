"""
Модуль с состояниями FSM для бота.
"""
from enum import Enum, auto
from dataclasses import dataclass, field
from typing import List, Optional, Dict
import logging

# Настройка логгера
logger = logging.getLogger("bot")


class BotState(str, Enum):
    """Состояния бота."""
    POST_VIEW = 'post_view'
    MODERATE_MENU = 'moderate_menu'
    EDIT_MENU = 'edit_menu'
    EDIT_TEXT_WAIT = 'edit_text_wait'
    EDIT_MEDIA_MENU = 'edit_media_menu'
    EDIT_MEDIA_ADD_WAIT = 'edit_media_add_wait'
    EDIT_MEDIA_REMOVE_WAIT = 'edit_media_remove_wait'


@dataclass
class PostContext:
    """Контекст поста."""
    post_id: str
    chat_id: int
    message_id: int
    state: BotState
    original_text: str
    original_media: List[int]
    temp_text: Optional[str] = None
    temp_media: Optional[List[int]] = None
    media_to_remove: Optional[List[int]] = None
    service_messages: List[int] = field(default_factory=list)  # ID служебных сообщений


class StateManager:
    """Менеджер состояний постов."""
    
    def __init__(self):
        """Инициализация менеджера состояний."""
        self._post_contexts: Dict[str, PostContext] = {}
        logger.info("StateManager инициализирован")
    
    def get_post_context(self, post_id: str) -> Optional[PostContext]:
        """
        Получение контекста поста.
        
        Args:
            post_id: ID поста
            
        Returns:
            Optional[PostContext]: Контекст поста или None
        """
        context = self._post_contexts.get(post_id)
        if context:
            logger.info(f"Получен контекст поста {post_id}:")
            logger.info(f"  - Состояние: {context.state}")
            logger.info(f"  - Chat ID: {context.chat_id}")
            logger.info(f"  - Message ID: {context.message_id}")
        return context
    
    def set_post_context(self, post_id: str, context: PostContext) -> None:
        """
        Установка контекста поста.
        
        Args:
            post_id: ID поста
            context: Контекст поста
        """
        old_context = self._post_contexts.get(post_id)
        old_state = old_context.state if old_context else None
        
        self._post_contexts[post_id] = context
        
        logger.info(f"Контекст поста {post_id} обновлен:")
        logger.info(f"  - Старое состояние: {old_state}")
        logger.info(f"  - Новое состояние: {context.state}")
        logger.info(f"  - Chat ID: {context.chat_id}")
        logger.info(f"  - Message ID: {context.message_id}")
    
    def get_all_contexts(self) -> Dict[str, PostContext]:
        """
        Получение всех контекстов постов.
        
        Returns:
            Dict[str, PostContext]: Словарь с контекстами постов
        """
        return self._post_contexts
    
    def clear_post_context(self, post_id: str) -> None:
        """
        Очищает контекст поста.
        
        Args:
            post_id: ID поста
        """
        logger.info(f"Очистка контекста поста {post_id}")
        if post_id in self._post_contexts:
            del self._post_contexts[post_id]
            logger.info(f"Контекст поста {post_id} успешно очищен")
        else:
            logger.warning(f"Контекст поста {post_id} не найден для очистки")


"""
Схема переходов состояний:

[ПОСТ_VIEW]
│
├── ✅ Модерировать → MODERATE_MENU
│     ├── ✅ Опубликовать → CONFIRM_PUBLISH
│     │     ├── ✅ Да   → удаление кнопок, сообщение о публикации
│     │     └── ❌ Нет  → возврат к POST_VIEW
│     │
│     ├── ✏️ Редактировать → EDIT_MENU
│     │     ├── Текст → EDIT_TEXT_WAIT → сохранение, возврат к POST_VIEW
│     │     │
│     │     ├── 🖼 Медиа → EDIT_MEDIA_MENU
│     │     │     ├── Добавить → EDIT_MEDIA_ADD_WAIT → сохранение, возврат к POST_VIEW
│     │     │     │
│     │     │     └── Удалить → EDIT_MEDIA_REMOVE_WAIT → удаление, возврат к POST_VIEW
│     │     │
│     │     └── 🔙 Назад → MODERATE_MENU
│     │
│     └── ❌ Удалить → CONFIRM_DELETE
│           ├── ✅ Да   → удаление поста и фото
│           └── ❌ Нет  → возврат к MODERATE_MENU
│
└── ❌ Удалить → QUICK_DELETE
      ├── ✅ Да   → удаление поста и фото
      └── ❌ Нет  → возврат к POST_VIEW

Правила работы с кнопками:
1. Всегда сверяться со схемой при добавлении новых кнопок или изменении существующих
2. Каждое состояние должно иметь четкий переход в другое состояние

4. После публикации или удаления всегда показывается служебное сообщение
5. При отмене действий возвращаться к предыдущему состоянию
6. Все временные данные хранить в контексте поста
7. Очищать контекст после завершения операций
""" 