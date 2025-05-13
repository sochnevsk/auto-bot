"""
Модуль для тестирования бота.
"""
import asyncio
import logging
import json
from typing import Dict, List, Optional
from dataclasses import dataclass
from datetime import datetime

# Настройка логгера
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

@dataclass
class TestPost:
    """Тестовый пост"""
    post_id: str
    text: str
    media: List[str]
    was_edited: bool
    was_published: bool
    was_deleted: bool

@dataclass
class MockMessage:
    """Мок объект сообщения"""
    message_id: int
    chat_id: str
    text: Optional[str] = None
    photo: Optional[List[Dict]] = None
    reply_markup: Optional[Dict] = None

@dataclass
class MockCallbackQuery:
    """Мок объект callback query"""
    data: str
    message: MockMessage
    from_user: Dict

@dataclass
class MockUpdate:
    """Мок объект update"""
    callback_query: Optional[MockCallbackQuery] = None
    message: Optional[MockMessage] = None
    effective_user: Dict = None

@dataclass
class MockContext:
    """Мок объект context"""
    bot: 'MockBot'

class MockBot:
    """Мок объект бота"""
    def __init__(self):
        self.messages: List[MockMessage] = []
        self.deleted_messages: List[int] = []
        self.media_groups: List[List[MockMessage]] = []
        
    async def send_message(self, chat_id: str, text: str, reply_markup=None) -> MockMessage:
        """Эмуляция отправки сообщения"""
        message = MockMessage(
            message_id=len(self.messages) + 1,
            chat_id=chat_id,
            text=text,
            reply_markup=reply_markup
        )
        self.messages.append(message)
        logger.info(f"Bot sent message: {text}")
        return message
        
    async def delete_message(self, chat_id: str, message_id: int) -> bool:
        """Эмуляция удаления сообщения"""
        self.deleted_messages.append(message_id)
        logger.info(f"Bot deleted message {message_id}")
        return True
        
    async def edit_message_reply_markup(self, chat_id: str, message_id: int, reply_markup=None) -> bool:
        """Эмуляция изменения клавиатуры"""
        for msg in self.messages:
            if msg.message_id == message_id:
                msg.reply_markup = reply_markup
                logger.info(f"Bot updated keyboard for message {message_id}")
                return True
        return False
        
    async def send_media_group(self, chat_id: str, media: List[Dict]) -> List[MockMessage]:
        """Эмуляция отправки группы медиа"""
        media_group = []
        for i, m in enumerate(media):
            message = MockMessage(
                message_id=len(self.messages) + 1 + i,
                chat_id=chat_id,
                text=m.get('caption'),
                photo=[{'file_id': f'photo_{i+1}'}]
            )
            media_group.append(message)
            self.messages.append(message)
        self.media_groups.append(media_group)
        logger.info(f"Bot sent media group with {len(media)} items")
        return media_group

class TestBot:
    """Класс для тестирования бота"""
    def __init__(self):
        self.bot = MockBot()
        self.storage = {}
        self._init_test_data()
        
        # Тестовые данные
        self.test_texts = {
            "text_1": "Новый текст для поста 1",
            "text_2": "Новый текст для поста 2",
            "text_3": "Новый текст для поста 3"
        }
        self.test_media = {
            "new_photo_1": "new_photo_1",
            "new_photo_2": "new_photo_2"
        }
    
    def _init_test_data(self):
        """Инициализация тестовых данных"""
        post_id = "post_20250512_044632"
        self.storage[post_id] = TestPost(
            post_id=post_id,
            text="Тестовый пост для проверки функционала",
            media=["photo_1", "photo_2", "photo_3"],
            was_edited=False,
            was_published=False,
            was_deleted=False
        )
    
    async def process_callback(self, callback_data: str):
        """Обработка callback запроса"""
        logger.info(f"Processing callback: {callback_data}")
        
        # Парсим callback_data
        parts = callback_data.split("_")
        action = parts[0]
        subaction = parts[1] if len(parts) > 2 and parts[1] in ["publish", "delete", "add", "remove"] else None
        post_id = "_".join(parts[1:]) if not subaction else "_".join(parts[2:])

        # Для cancel/confirm, если post_id не найден — не ошибка, а возврат в меню
        if action in ["cancel", "confirm"] and post_id not in self.storage:
            logger.warning(f"Post {post_id} not found in storage for {action}. Возврат в меню/ничего не делаем.")
            return
        # Для остальных — ошибка если нет поста
        if action not in ["cancel", "confirm"] and post_id not in self.storage:
            logger.error(f"Post {post_id} not found in storage")
            return

        # Логируем, что ищем пост
        logger.info(f"Ищем пост с post_id={post_id} для действия {action}{' ('+subaction+')' if subaction else ''}")
        post = self.storage.get(post_id)
        if post:
            logger.info(f"Найден пост: text='{post.text}', media={post.media}, was_edited={post.was_edited}, was_published={post.was_published}, was_deleted={post.was_deleted}")
        else:
            logger.info(f"Пост не найден (это допустимо для cancel/confirm)")

        # Обработка действий
        if action == "moderate":
            await self._handle_moderate(post_id)
        elif action == "edit":
            await self._handle_edit(post_id)
        elif action == "edittext":
            await self._handle_edit_text(post_id)
        elif action == "editmedia":
            await self._handle_edit_media(post_id)
        elif action == "publish":
            await self._handle_publish(post_id)
        elif action == "delete":
            await self._handle_delete(post_id)
        elif action == "quickdelete":
            await self._handle_quick_delete(post_id)
        elif action == "addmedia":
            await self._handle_add_media(post_id)
        elif action == "removemedia":
            await self._handle_remove_media(post_id)
        elif action == "confirm":
            if post:
                await self._handle_confirm(post_id, subaction)
            else:
                logger.info(f"Confirm {subaction} для несуществующего поста — пропускаем.")
        elif action == "cancel":
            if post:
                await self._handle_cancel(post_id, subaction)
            else:
                logger.info(f"Cancel {subaction} для несуществующего поста — возврат в меню.")
    
    async def _handle_moderate(self, post_id: str):
        """Обработка модерации поста"""
        logger.info(f"Handling moderate for post {post_id}")
        post = self.storage[post_id]
        await self.bot.send_message("-1001234567890", f"Пост {post_id} отправлен на модерацию")
    
    async def _handle_edit(self, post_id: str):
        """Обработка редактирования поста"""
        logger.info(f"Handling edit for post {post_id}")
        post = self.storage[post_id]
        await self.bot.send_message("-1001234567890", f"Редактирование поста {post_id}")
    
    async def _handle_edit_text(self, post_id: str):
        """Обработка редактирования текста"""
        logger.info(f"Handling edit text for post {post_id}")
        post = self.storage[post_id]
        await self.bot.send_message("-1001234567890", f"Отправьте новый текст для поста {post_id}")
    
    async def _handle_edit_media(self, post_id: str):
        """Обработка редактирования медиа"""
        logger.info(f"Handling edit media for post {post_id}")
        post = self.storage[post_id]
        await self.bot.send_message("-1001234567890", f"Редактирование медиа для поста {post_id}")
    
    async def _handle_publish(self, post_id: str):
        """Обработка публикации поста"""
        logger.info(f"Handling publish for post {post_id}")
        post = self.storage[post_id]
        await self.bot.send_message("-1001234567890", f"Подтвердите публикацию поста {post_id}")
    
    async def _handle_delete(self, post_id: str):
        """Обработка удаления поста"""
        logger.info(f"Handling delete for post {post_id}")
        post = self.storage[post_id]
        await self.bot.send_message("-1001234567890", f"Подтвердите удаление поста {post_id}")
    
    async def _handle_quick_delete(self, post_id: str):
        """Обработка быстрого удаления поста"""
        logger.info(f"Handling quick delete for post {post_id}")
        post = self.storage[post_id]
        post.was_deleted = True
        await self.bot.send_message("-1001234567890", f"Пост {post_id} удален")
    
    async def _handle_add_media(self, post_id: str):
        """Обработка добавления медиа"""
        logger.info(f"Handling add media for post {post_id}")
        post = self.storage[post_id]
        await self.bot.send_message("-1001234567890", f"Отправьте новое медиа для поста {post_id}")
    
    async def _handle_remove_media(self, post_id: str):
        """Обработка удаления медиа"""
        logger.info(f"Handling remove media for post {post_id}")
        post = self.storage[post_id]
        await self.bot.send_message("-1001234567890", f"Выберите медиа для удаления из поста {post_id}")
    
    async def _handle_confirm(self, post_id: str, subaction: str):
        """Обработка подтверждения действия"""
        logger.info(f"Handling confirm {subaction} for post {post_id}")
        post = self.storage.get(post_id)
        if not post:
            logger.info(f"Подтверждение {subaction} для несуществующего поста — пропускаем.")
            return
        logger.info(f"Перед подтверждением: text='{post.text}', media={post.media}, was_edited={post.was_edited}, was_published={post.was_published}, was_deleted={post.was_deleted}")
        if subaction == "publish":
            post.was_published = True
            await self.bot.send_message("-1001234567890", f"Пост {post_id} опубликован")
        elif subaction == "delete":
            post.was_deleted = True
            await self.bot.send_message("-1001234567890", f"Пост {post_id} удален")
        elif subaction == "add":
            await self.bot.send_message("-1001234567890", f"Медиа добавлено в пост {post_id}")
        elif subaction == "remove":
            await self.bot.send_message("-1001234567890", f"Медиа удалено из поста {post_id}")
        logger.info(f"После подтверждения: text='{post.text}', media={post.media}, was_edited={post.was_edited}, was_published={post.was_published}, was_deleted={post.was_deleted}")
    
    async def _handle_cancel(self, post_id: str, subaction: str):
        """Обработка отмены действия"""
        logger.info(f"Handling cancel {subaction} for post {post_id}")
        post = self.storage.get(post_id)
        if post:
            logger.info(f"Отмена действия {subaction} для поста: text='{post.text}', media={post.media}, was_edited={post.was_edited}, was_published={post.was_published}, was_deleted={post.was_deleted}")
        else:
            logger.info(f"Отмена действия {subaction} для несуществующего поста — возврат в меню.")
        await self.bot.send_message("-1001234567890", f"Действие отменено для поста {post_id}")
    
    async def handle_message(self, text: str, post_id: str):
        """Обработка текстового сообщения"""
        logger.info(f"Handling message for post {post_id}: {text}")
        post = self.storage[post_id]
        post.text = text
        post.was_edited = True
        logger.info(f"Updated post text: {text}")
    
    async def handle_media(self, media_items: List[str], post_id: str):
        """Обработка медиа сообщения"""
        logger.info(f"Handling media for post {post_id}: {len(media_items)} items")
        post = self.storage[post_id]
        post.media.extend(media_items)
        post.was_edited = True
        logger.info(f"Updated post media: {post.media}")

async def run_tests():
    """Запуск тестов"""
    logger.info("Starting tests...")
    
    # Создаем тестовый бот
    test_bot = TestBot()
    
    # Проверяем начальное состояние поста
    post_id = "post_20250512_044632"
    post = test_bot.storage[post_id]
    logger.info(f"Initial post state:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # Базовые сценарии
    logger.info("Starting basic scenarios...")
    
    # 1. Модерация
    logger.info("1. Moderation")
    await test_bot.process_callback(f"moderate_{post_id}")
    logger.info(f"Post state after moderation:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 2. Редактирование
    logger.info("2. Edit")
    await test_bot.process_callback(f"edit_{post_id}")
    logger.info(f"Post state after edit:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 3. Редактирование текста
    logger.info("3. Edit text")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.handle_message("Новый текст для поста", post_id)
    logger.info(f"Post state after text edit:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 4. Редактирование медиа
    logger.info("4. Edit media")
    await test_bot.process_callback(f"editmedia_{post_id}")
    logger.info(f"Post state after media edit:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 5. Публикация
    logger.info("5. Publish")
    await test_bot.process_callback(f"publish_{post_id}")
    logger.info(f"Post state after publish:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 6. Подтверждение публикации
    logger.info("6. Confirm publish")
    await test_bot.process_callback(f"confirm_publish_{post_id}")
    logger.info(f"Post state after confirm publish:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 7. Отмена публикации
    logger.info("7. Cancel publish")
    await test_bot.process_callback(f"cancel_publish_{post_id}")
    logger.info(f"Post state after cancel publish:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 8. Удаление
    logger.info("8. Delete")
    await test_bot.process_callback(f"delete_{post_id}")
    logger.info(f"Post state after delete:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 9. Подтверждение удаления
    logger.info("9. Confirm delete")
    await test_bot.process_callback(f"confirm_delete_{post_id}")
    logger.info(f"Post state after confirm delete:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 10. Отмена удаления
    logger.info("10. Cancel delete")
    await test_bot.process_callback(f"cancel_delete_{post_id}")
    logger.info(f"Post state after cancel delete:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 11. Быстрое удаление
    logger.info("11. Quick delete")
    await test_bot.process_callback(f"quickdelete_{post_id}")
    logger.info(f"Post state after quick delete:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 12. Добавление медиа
    logger.info("12. Add media")
    await test_bot.process_callback(f"addmedia_{post_id}")
    await test_bot.handle_media(["new_photo_1", "new_photo_2"], post_id)
    logger.info(f"Post state after add media:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 13. Удаление медиа
    logger.info("13. Remove media")
    await test_bot.process_callback(f"removemedia_{post_id}")
    logger.info(f"Post state after remove media:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 14. Подтверждение добавления медиа
    logger.info("14. Confirm add media")
    await test_bot.process_callback(f"confirm_add_{post_id}")
    logger.info(f"Post state after confirm add media:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 15. Подтверждение удаления медиа
    logger.info("15. Confirm remove media")
    await test_bot.process_callback(f"confirm_remove_{post_id}")
    logger.info(f"Post state after confirm remove media:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 16. Отмена добавления медиа
    logger.info("16. Cancel add media")
    await test_bot.process_callback(f"cancel_add_{post_id}")
    logger.info(f"Post state after cancel add media:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 17. Отмена удаления медиа
    logger.info("17. Cancel remove media")
    await test_bot.process_callback(f"cancel_remove_{post_id}")
    logger.info(f"Post state after cancel remove media:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    logger.info("Basic scenarios completed")
    
    # Расширенные пользовательские сценарии
    logger.info("Starting advanced scenarios...")
    
    # Группа 1: Сценарии редактирования текста
    logger.info("Group 1: Text editing scenarios")
    
    # 1.1 Редактирование текста → отправка текста → публикация → подтверждение
    logger.info("1.1 Edit text → send text → publish → confirm")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.handle_message("Новый текст для поста 1", post_id)
    await test_bot.process_callback(f"publish_{post_id}")
    await test_bot.process_callback(f"confirm_publish_{post_id}")
    logger.info(f"Post state after scenario 1.1:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 1.2 Редактирование текста → отправка текста → удаление → подтверждение
    logger.info("1.2 Edit text → send text → delete → confirm")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.handle_message("Новый текст для поста 2", post_id)
    await test_bot.process_callback(f"delete_{post_id}")
    await test_bot.process_callback(f"confirm_delete_{post_id}")
    logger.info(f"Post state after scenario 1.2:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 1.3 Редактирование текста → отправка текста → публикация → отмена
    logger.info("1.3 Edit text → send text → publish → cancel")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.handle_message("Новый текст для поста 3", post_id)
    await test_bot.process_callback(f"publish_{post_id}")
    await test_bot.process_callback(f"cancel_publish_{post_id}")
    logger.info(f"Post state after scenario 1.3:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 1.4 Редактирование текста → отправка текста → удаление → отмена
    logger.info("1.4 Edit text → send text → delete → cancel")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.handle_message("Новый текст для поста 4", post_id)
    await test_bot.process_callback(f"delete_{post_id}")
    await test_bot.process_callback(f"cancel_delete_{post_id}")
    logger.info(f"Post state after scenario 1.4:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 1.5 Редактирование текста → отмена
    logger.info("1.5 Edit text → cancel")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.process_callback(f"cancel_edit_{post_id}")
    logger.info(f"Post state after scenario 1.5:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # Группа 2: Сценарии редактирования медиа
    logger.info("Group 2: Media editing scenarios")
    
    # 2.1 Добавление медиа → подтверждение → публикация → подтверждение
    logger.info("2.1 Add media → confirm → publish → confirm")
    await test_bot.process_callback(f"addmedia_{post_id}")
    await test_bot.handle_media(["new_photo_1"], post_id)
    await test_bot.process_callback(f"confirm_add_{post_id}")
    await test_bot.process_callback(f"publish_{post_id}")
    await test_bot.process_callback(f"confirm_publish_{post_id}")
    logger.info(f"Post state after scenario 2.1:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 2.2 Добавление медиа → подтверждение → удаление → подтверждение
    logger.info("2.2 Add media → confirm → delete → confirm")
    await test_bot.process_callback(f"addmedia_{post_id}")
    await test_bot.handle_media(["new_photo_2"], post_id)
    await test_bot.process_callback(f"confirm_add_{post_id}")
    await test_bot.process_callback(f"delete_{post_id}")
    await test_bot.process_callback(f"confirm_delete_{post_id}")
    logger.info(f"Post state after scenario 2.2:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 2.3 Добавление медиа → подтверждение → публикация → отмена
    logger.info("2.3 Add media → confirm → publish → cancel")
    await test_bot.process_callback(f"addmedia_{post_id}")
    await test_bot.handle_media(["new_photo_3"], post_id)
    await test_bot.process_callback(f"confirm_add_{post_id}")
    await test_bot.process_callback(f"publish_{post_id}")
    await test_bot.process_callback(f"cancel_publish_{post_id}")
    logger.info(f"Post state after scenario 2.3:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 2.4 Добавление медиа → подтверждение → удаление → отмена
    logger.info("2.4 Add media → confirm → delete → cancel")
    await test_bot.process_callback(f"addmedia_{post_id}")
    await test_bot.handle_media(["new_photo_4"], post_id)
    await test_bot.process_callback(f"confirm_add_{post_id}")
    await test_bot.process_callback(f"delete_{post_id}")
    await test_bot.process_callback(f"cancel_delete_{post_id}")
    logger.info(f"Post state after scenario 2.4:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 2.5 Добавление медиа → отмена
    logger.info("2.5 Add media → cancel")
    await test_bot.process_callback(f"addmedia_{post_id}")
    await test_bot.process_callback(f"cancel_add_{post_id}")
    logger.info(f"Post state after scenario 2.5:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 2.6 Удаление медиа → подтверждение → публикация → подтверждение
    logger.info("2.6 Remove media → confirm → publish → confirm")
    await test_bot.process_callback(f"removemedia_{post_id}")
    await test_bot.process_callback(f"confirm_remove_{post_id}")
    await test_bot.process_callback(f"publish_{post_id}")
    await test_bot.process_callback(f"confirm_publish_{post_id}")
    logger.info(f"Post state after scenario 2.6:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 2.7 Удаление медиа → подтверждение → удаление → подтверждение
    logger.info("2.7 Remove media → confirm → delete → confirm")
    await test_bot.process_callback(f"removemedia_{post_id}")
    await test_bot.process_callback(f"confirm_remove_{post_id}")
    await test_bot.process_callback(f"delete_{post_id}")
    await test_bot.process_callback(f"confirm_delete_{post_id}")
    logger.info(f"Post state after scenario 2.7:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 2.8 Удаление медиа → подтверждение → публикация → отмена
    logger.info("2.8 Remove media → confirm → publish → cancel")
    await test_bot.process_callback(f"removemedia_{post_id}")
    await test_bot.process_callback(f"confirm_remove_{post_id}")
    await test_bot.process_callback(f"publish_{post_id}")
    await test_bot.process_callback(f"cancel_publish_{post_id}")
    logger.info(f"Post state after scenario 2.8:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 2.9 Удаление медиа → подтверждение → удаление → отмена
    logger.info("2.9 Remove media → confirm → delete → cancel")
    await test_bot.process_callback(f"removemedia_{post_id}")
    await test_bot.process_callback(f"confirm_remove_{post_id}")
    await test_bot.process_callback(f"delete_{post_id}")
    await test_bot.process_callback(f"cancel_delete_{post_id}")
    logger.info(f"Post state after scenario 2.9:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 2.10 Удаление медиа → отмена
    logger.info("2.10 Remove media → cancel")
    await test_bot.process_callback(f"removemedia_{post_id}")
    await test_bot.process_callback(f"cancel_remove_{post_id}")
    logger.info(f"Post state after scenario 2.10:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 2.11 Добавление медиа → удаление медиа → подтверждение
    logger.info("2.11 Add media → remove media → confirm")
    await test_bot.process_callback(f"addmedia_{post_id}")
    await test_bot.handle_media(["new_photo_5"], post_id)
    await test_bot.process_callback(f"removemedia_{post_id}")
    await test_bot.process_callback(f"confirm_remove_{post_id}")
    logger.info(f"Post state after scenario 2.11:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 2.12 Добавление медиа → удаление медиа → отмена
    logger.info("2.12 Add media → remove media → cancel")
    await test_bot.process_callback(f"addmedia_{post_id}")
    await test_bot.handle_media(["new_photo_6"], post_id)
    await test_bot.process_callback(f"removemedia_{post_id}")
    await test_bot.process_callback(f"cancel_remove_{post_id}")
    logger.info(f"Post state after scenario 2.12:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # Группа 3: Комбинированные сценарии (текст + медиа)
    logger.info("Group 3: Combined scenarios (text + media)")
    
    # 3.1 Редактирование текста → отправка текста → добавление медиа → подтверждение → публикация → подтверждение
    logger.info("3.1 Edit text → send text → add media → confirm → publish → confirm")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.handle_message("Новый текст для поста 5", post_id)
    await test_bot.process_callback(f"addmedia_{post_id}")
    await test_bot.handle_media(["new_photo_7"], post_id)
    await test_bot.process_callback(f"confirm_add_{post_id}")
    await test_bot.process_callback(f"publish_{post_id}")
    await test_bot.process_callback(f"confirm_publish_{post_id}")
    logger.info(f"Post state after scenario 3.1:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 3.2 Редактирование текста → отправка текста → добавление медиа → подтверждение → удаление → подтверждение
    logger.info("3.2 Edit text → send text → add media → confirm → delete → confirm")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.handle_message("Новый текст для поста 6", post_id)
    await test_bot.process_callback(f"addmedia_{post_id}")
    await test_bot.handle_media(["new_photo_8"], post_id)
    await test_bot.process_callback(f"confirm_add_{post_id}")
    await test_bot.process_callback(f"delete_{post_id}")
    await test_bot.process_callback(f"confirm_delete_{post_id}")
    logger.info(f"Post state after scenario 3.2:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 3.3 Редактирование текста → отправка текста → добавление медиа → подтверждение → публикация → отмена
    logger.info("3.3 Edit text → send text → add media → confirm → publish → cancel")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.handle_message("Новый текст для поста 7", post_id)
    await test_bot.process_callback(f"addmedia_{post_id}")
    await test_bot.handle_media(["new_photo_9"], post_id)
    await test_bot.process_callback(f"confirm_add_{post_id}")
    await test_bot.process_callback(f"publish_{post_id}")
    await test_bot.process_callback(f"cancel_publish_{post_id}")
    logger.info(f"Post state after scenario 3.3:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 3.4 Редактирование текста → отправка текста → добавление медиа → подтверждение → удаление → отмена
    logger.info("3.4 Edit text → send text → add media → confirm → delete → cancel")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.handle_message("Новый текст для поста 8", post_id)
    await test_bot.process_callback(f"addmedia_{post_id}")
    await test_bot.handle_media(["new_photo_10"], post_id)
    await test_bot.process_callback(f"confirm_add_{post_id}")
    await test_bot.process_callback(f"delete_{post_id}")
    await test_bot.process_callback(f"cancel_delete_{post_id}")
    logger.info(f"Post state after scenario 3.4:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 3.5 Редактирование текста → отправка текста → добавление медиа → отмена
    logger.info("3.5 Edit text → send text → add media → cancel")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.handle_message("Новый текст для поста 9", post_id)
    await test_bot.process_callback(f"addmedia_{post_id}")
    await test_bot.process_callback(f"cancel_add_{post_id}")
    logger.info(f"Post state after scenario 3.5:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 3.6 Редактирование текста → отправка текста → удаление медиа → подтверждение → публикация → подтверждение
    logger.info("3.6 Edit text → send text → remove media → confirm → publish → confirm")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.handle_message("Новый текст для поста 10", post_id)
    await test_bot.process_callback(f"removemedia_{post_id}")
    await test_bot.process_callback(f"confirm_remove_{post_id}")
    await test_bot.process_callback(f"publish_{post_id}")
    await test_bot.process_callback(f"confirm_publish_{post_id}")
    logger.info(f"Post state after scenario 3.6:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 3.7 Редактирование текста → отправка текста → удаление медиа → подтверждение → удаление → подтверждение
    logger.info("3.7 Edit text → send text → remove media → confirm → delete → confirm")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.handle_message("Новый текст для поста 11", post_id)
    await test_bot.process_callback(f"removemedia_{post_id}")
    await test_bot.process_callback(f"confirm_remove_{post_id}")
    await test_bot.process_callback(f"delete_{post_id}")
    await test_bot.process_callback(f"confirm_delete_{post_id}")
    logger.info(f"Post state after scenario 3.7:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 3.8 Редактирование текста → отправка текста → удаление медиа → подтверждение → публикация → отмена
    logger.info("3.8 Edit text → send text → remove media → confirm → publish → cancel")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.handle_message("Новый текст для поста 12", post_id)
    await test_bot.process_callback(f"removemedia_{post_id}")
    await test_bot.process_callback(f"confirm_remove_{post_id}")
    await test_bot.process_callback(f"publish_{post_id}")
    await test_bot.process_callback(f"cancel_publish_{post_id}")
    logger.info(f"Post state after scenario 3.8:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 3.9 Редактирование текста → отправка текста → удаление медиа → подтверждение → удаление → отмена
    logger.info("3.9 Edit text → send text → remove media → confirm → delete → cancel")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.handle_message("Новый текст для поста 13", post_id)
    await test_bot.process_callback(f"removemedia_{post_id}")
    await test_bot.process_callback(f"confirm_remove_{post_id}")
    await test_bot.process_callback(f"delete_{post_id}")
    await test_bot.process_callback(f"cancel_delete_{post_id}")
    logger.info(f"Post state after scenario 3.9:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 3.10 Редактирование текста → отправка текста → удаление медиа → отмена
    logger.info("3.10 Edit text → send text → remove media → cancel")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.handle_message("Новый текст для поста 14", post_id)
    await test_bot.process_callback(f"removemedia_{post_id}")
    await test_bot.process_callback(f"cancel_remove_{post_id}")
    logger.info(f"Post state after scenario 3.10:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 3.11 Редактирование текста → отправка текста → добавление медиа → удаление медиа → подтверждение
    logger.info("3.11 Edit text → send text → add media → remove media → confirm")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.handle_message("Новый текст для поста 15", post_id)
    await test_bot.process_callback(f"addmedia_{post_id}")
    await test_bot.handle_media(["new_photo_11"], post_id)
    await test_bot.process_callback(f"removemedia_{post_id}")
    await test_bot.process_callback(f"confirm_remove_{post_id}")
    logger.info(f"Post state after scenario 3.11:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 3.12 Редактирование текста → отправка текста → добавление медиа → удаление медиа → отмена
    logger.info("3.12 Edit text → send text → add media → remove media → cancel")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.handle_message("Новый текст для поста 16", post_id)
    await test_bot.process_callback(f"addmedia_{post_id}")
    await test_bot.handle_media(["new_photo_12"], post_id)
    await test_bot.process_callback(f"removemedia_{post_id}")
    await test_bot.process_callback(f"cancel_remove_{post_id}")
    logger.info(f"Post state after scenario 3.12:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # Группа 4: Сценарии отмены
    logger.info("Group 4: Cancellation scenarios")
    
    # 4.1 Отмена на этапе редактирования текста
    logger.info("4.1 Cancel at text editing stage")
    await test_bot.process_callback(f"edittext_{post_id}")
    await test_bot.process_callback(f"cancel_edit_{post_id}")
    logger.info(f"Post state after scenario 4.1:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 4.2 Отмена на этапе редактирования медиа
    logger.info("4.2 Cancel at media editing stage")
    await test_bot.process_callback(f"editmedia_{post_id}")
    await test_bot.process_callback(f"cancel_edit_{post_id}")
    logger.info(f"Post state after scenario 4.2:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    # 4.3 Отмена на этапе модерации
    logger.info("4.3 Cancel at moderation stage")
    await test_bot.process_callback(f"moderate_{post_id}")
    await test_bot.process_callback(f"cancel_moderate_{post_id}")
    logger.info(f"Post state after scenario 4.3:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    logger.info("Advanced scenarios completed")
    
    # Проверяем финальное состояние поста
    logger.info("Final post state:")
    logger.info(f"Text: {post.text}")
    logger.info(f"Media: {post.media}")
    logger.info(f"Edit status: {post.was_edited}")
    logger.info(f"Publish status: {post.was_published}")
    logger.info(f"Delete status: {post.was_deleted}")
    
    logger.info("All scenarios completed successfully")

if __name__ == "__main__":
    asyncio.run(run_tests()) 