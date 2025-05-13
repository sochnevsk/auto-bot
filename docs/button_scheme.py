"""
Документация схемы кнопок и состояний бота.
Этот файл используется только как документация и не импортируется в код.
"""
from enum import Enum, auto
from dataclasses import dataclass
from typing import List, Optional


class BotState(Enum):
    """Состояния бота."""
    # Основные состояния
    POST_VIEW = auto()           # Начальное состояние просмотра поста
    MODERATE_MENU = auto()       # Меню модерации
    CONFIRM_PUBLISH = auto()     # Подтверждение публикации
    CONFIRM_DELETE = auto()      # Подтверждение удаления
    QUICK_DELETE = auto()        # Быстрое удаление
    
    # Состояния редактирования
    EDIT_MENU = auto()           # Меню редактирования
    EDIT_TEXT_WAIT = auto()      # Ожидание нового текста
    EDIT_TEXT_CONFIRM = auto()   # Подтверждение нового текста
    EDIT_MEDIA_MENU = auto()     # Меню редактирования медиа
    EDIT_MEDIA_ADD_WAIT = auto() # Ожидание новых фото
    EDIT_MEDIA_ADD_CONFIRM = auto() # Подтверждение новых фото
    EDIT_MEDIA_REMOVE_WAIT = auto() # Ожидание номеров фото для удаления
    EDIT_MEDIA_REMOVE_CONFIRM = auto() # Подтверждение удаления фото


@dataclass
class PostContext:
    """Контекст поста."""
    post_id: str
    chat_id: int
    message_id: int
    state: BotState
    original_text: Optional[str] = None
    original_media: Optional[List[int]] = None
    temp_text: Optional[str] = None
    temp_media: Optional[List[int]] = None
    media_to_remove: Optional[List[int]] = None


class StateManager:
    """Менеджер состояний."""
    
    def __init__(self):
        """Инициализация менеджера состояний."""
        self._posts: dict[str, PostContext] = {}
    
    def get_post_context(self, post_id: str) -> Optional[PostContext]:
        """Получить контекст поста."""
        return self._posts.get(post_id)
    
    def set_post_context(self, post_id: str, context: PostContext) -> None:
        """Установить контекст поста."""
        self._posts[post_id] = context
    
    def clear_post_context(self, post_id: str) -> None:
        """Очистить контекст поста."""
        if post_id in self._posts:
            del self._posts[post_id]


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
│     │     ├── Текст → EDIT_TEXT_WAIT
│     │     │     ├── [Ввод текста] → EDIT_TEXT_CONFIRM
│     │     │     │     ├── ✅ Да   → сохранение, возврат к POST_VIEW
│     │     │     │     └── ❌ Нет  → возврат к EDIT_MENU
│     │     │
│     │     ├── 🖼 Медиа → EDIT_MEDIA_MENU
│     │     │     ├── Добавить → EDIT_MEDIA_ADD_WAIT
│     │     │     │     ├── [Ввод фото] → EDIT_MEDIA_ADD_CONFIRM
│     │     │     │     │     ├── ✅ Да   → сохранение, возврат к POST_VIEW
│     │     │     │     │     └── ❌ Нет  → возврат к EDIT_MEDIA_MENU
│     │     │     │
│     │     │     └── Удалить → EDIT_MEDIA_REMOVE_WAIT
│     │     │           ├── [Ввод номеров] → EDIT_MEDIA_REMOVE_CONFIRM
│     │     │           │     ├── ✅ Да   → удаление, возврат к POST_VIEW
│     │     │           │     └── ❌ Нет  → возврат к EDIT_MEDIA_MENU
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
3. Все подтверждения реализуются через отдельные клавиатуры с "Да/Нет"
4. После публикации или удаления всегда показывается служебное сообщение
5. При отмене действий возвращаться к предыдущему состоянию
6. Все временные данные хранить в контексте поста
7. Очищать контекст после завершения операций
""" 