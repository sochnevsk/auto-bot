import pytest
from unittest.mock import Mock, AsyncMock, mock_open, patch
from telegram import Update, Message, User, Chat, CallbackQuery
from telegram.ext import ContextTypes
from src.bot.bot import Bot
from src.bot.states import BotState, PostContext
import builtins

@pytest.fixture
def bot_instance():
    return Bot()

@pytest.fixture
def mock_context():
    context = Mock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = Mock()
    context.bot.delete_message = AsyncMock()
    context.bot.send_message = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.edit_message_reply_markup = AsyncMock()
    context.bot.send_media_group = AsyncMock()
    context.bot.edit_message_caption = AsyncMock()
    return context

# Вспомогательная функция для создания mock Update
def make_mock_update(user_id=123, chat_id=456, message_id=789, text=None, photo=None, callback_data=None):
    update = Mock(spec=Update)
    update.message = Mock(spec=Message)
    update.message.from_user = Mock(spec=User)
    update.message.from_user.id = user_id
    update.message.from_user.full_name = "Test User"
    update.message.chat = Mock(spec=Chat)
    update.message.chat.id = chat_id
    update.message.message_id = message_id
    update.message.reply_text = AsyncMock()
    update.message.edit_reply_markup = AsyncMock()
    update.message.edit_text = AsyncMock()
    update.message.text = text
    update.message.photo = photo
    update.callback_query = Mock(spec=CallbackQuery)
    update.callback_query.from_user = update.message.from_user
    update.callback_query.message = update.message
    update.callback_query.answer = AsyncMock()
    update.callback_query.data = callback_data
    return update

@pytest.mark.asyncio
async def test_edit_text_flow(bot_instance, mock_context):
    # Создаем пост-контекст вручную (эмулируем появление поста)
    post_id = "post_1"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=789,
        state=BotState.POST_VIEW,
        user_id=123,
        original_text="Старый текст",
        original_media=[]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)

    # 1. Модератор нажимает "Редактировать текст"
    update1 = make_mock_update(callback_data="edit_text_post_1")
    await bot_instance.handle_callback(update1, mock_context)
    assert bot_instance.state_manager.get_post_context(post_id).state == BotState.EDIT_TEXT_WAIT

    # 2. Модератор отправляет новый текст
    update2 = make_mock_update(text="Новый текст")
    await bot_instance.handle_message(update2, mock_context)
    assert bot_instance.state_manager.get_post_context(post_id).state == BotState.EDIT_TEXT_CONFIRM
    assert bot_instance.state_manager.get_post_context(post_id).temp_text == "Новый текст"

    # 3. Модератор подтверждает сохранение
    update3 = make_mock_update(callback_data="confirm_text_post_1")
    await bot_instance.handle_callback(update3, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    assert ctx.state == BotState.EDIT_MENU

@pytest.mark.asyncio
async def test_media_add_flow(bot_instance, mock_context):
    post_id = "post_2"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=790,
        state=BotState.POST_VIEW,
        user_id=123,
        original_text="Текст",
        original_media=[]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)

    # 1. Модератор нажимает "Добавить медиа"
    update1 = make_mock_update(callback_data="add_media_post_2")
    await bot_instance.handle_callback(update1, mock_context)
    assert bot_instance.state_manager.get_post_context(post_id).state == BotState.EDIT_MEDIA_ADD_WAIT

    # 2. Модератор отправляет фото
    photo_mock = Mock()
    photo_mock.get_file = AsyncMock()
    photo_mock.get_file.return_value.download_to_drive = AsyncMock()
    update2 = make_mock_update(photo=[photo_mock])
    # Мокаем open для отправки медиа-группы
    with patch.object(builtins, "open", mock_open(read_data=b"data")):
        await bot_instance.handle_message(update2, mock_context)
    # Проверяем переход в состояние подтверждения
    assert bot_instance.state_manager.get_post_context(post_id).state == BotState.EDIT_MEDIA_ADD_CONFIRM

    # 3. Модератор подтверждает добавление
    update3 = make_mock_update(callback_data="confirm_add_media_post_2")
    await bot_instance.handle_callback(update3, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    assert ctx.state == BotState.EDIT_MENU

@pytest.mark.asyncio
async def test_media_add_flow_real_files(bot_instance, mock_context):
    post_id = "post_20250512_044632"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=2001,
        state=BotState.POST_VIEW,
        user_id=123,
        original_text="Тестовый текст",
        original_media=[
            "saved/post_20250512_044632/photo_1.jpg",
            "saved/post_20250512_044632/photo_2.jpg"
        ]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)

    # 1. Модератор нажимает "Добавить медиа"
    update1 = make_mock_update(callback_data="add_media_post_20250512_044632")
    await bot_instance.handle_callback(update1, mock_context)
    assert bot_instance.state_manager.get_post_context(post_id).state == BotState.EDIT_MEDIA_ADD_WAIT

    # 2. Модератор отправляет реальное фото из папки
    class RealPhoto:
        async def get_file(self):
            class File:
                async def download_to_drive(self, path):
                    # Копируем photo_3.jpg в новый файл (photo_4.jpg)
                    import shutil
                    if path != "saved/post_20250512_044632/photo_3.jpg":
                        shutil.copy("saved/post_20250512_044632/photo_3.jpg", path)
            return File()
    real_photo = RealPhoto()
    update2 = make_mock_update(photo=[real_photo])
    await bot_instance.handle_message(update2, mock_context)
    # FSM должна перейти в состояние подтверждения
    assert bot_instance.state_manager.get_post_context(post_id).state == BotState.EDIT_MEDIA_ADD_CONFIRM

    # Тест завершён: FSM корректно перешла в состояние ожидания добавления медиа 

@pytest.mark.asyncio
async def test_media_remove_flow_real_files(bot_instance, mock_context):
    post_id = "post_20250512_044632"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=2002,
        state=BotState.POST_VIEW,
        user_id=123,
        original_text="Тестовый текст",
        original_media=[
            "saved/post_20250512_044632/photo_1.jpg",
            "saved/post_20250512_044632/photo_2.jpg",
            "saved/post_20250512_044632/photo_3.jpg"
        ]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)

    # 1. Модератор нажимает "Удалить медиа"
    update1 = make_mock_update(callback_data="remove_media_post_20250512_044632")
    await bot_instance.handle_callback(update1, mock_context)
    assert bot_instance.state_manager.get_post_context(post_id).state == BotState.EDIT_MEDIA_REMOVE_WAIT

    # 2. Модератор отправляет номера для удаления (например, 2)
    update2 = make_mock_update(text="2")
    await bot_instance.handle_message(update2, mock_context)
    assert bot_instance.state_manager.get_post_context(post_id).state == BotState.EDIT_MEDIA_REMOVE_CONFIRM

    # 3. Модератор подтверждает удаление
    update3 = make_mock_update(callback_data="confirm_remove_media_post_20250512_044632")
    await bot_instance.handle_callback(update3, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    assert ctx.state == BotState.EDIT_MENU

@pytest.mark.asyncio
async def test_publish_flow_real_files(bot_instance, mock_context):
    post_id = "post_20250512_044632"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=2003,
        state=BotState.POST_VIEW,
        user_id=123,
        original_text="Тестовый текст",
        original_media=[
            "saved/post_20250512_044632/photo_1.jpg",
            "saved/post_20250512_044632/photo_2.jpg",
            "saved/post_20250512_044632/photo_3.jpg"
        ]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)

    # 1. Модератор нажимает "Опубликовать"
    update1 = make_mock_update(callback_data="publish_post_20250512_044632")
    await bot_instance.handle_callback(update1, mock_context)
    assert bot_instance.state_manager.get_post_context(post_id).state == BotState.CONFIRM_PUBLISH

    # 2. Модератор подтверждает публикацию
    update2 = make_mock_update(callback_data="confirm_publish_post_20250512_044632")
    await bot_instance.handle_callback(update2, mock_context)
    # После публикации контекст должен быть очищен (None)
    assert bot_instance.state_manager.get_post_context(post_id) is None 

@pytest.mark.asyncio
async def test_quick_delete_flow_real_files(bot_instance, mock_context):
    post_id = "post_20250512_044632"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=2004,
        state=BotState.POST_VIEW,
        user_id=123,
        original_text="Тестовый текст",
        original_media=[
            "saved/post_20250512_044632/photo_1.jpg",
            "saved/post_20250512_044632/photo_2.jpg",
            "saved/post_20250512_044632/photo_3.jpg"
        ]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)

    # 1. Модератор нажимает "Быстро удалить"
    update1 = make_mock_update(callback_data="quick_delete_post_20250512_044632")
    await bot_instance.handle_callback(update1, mock_context)
    assert bot_instance.state_manager.get_post_context(post_id).state == BotState.QUICK_DELETE

    # 2. Модератор подтверждает удаление
    update2 = make_mock_update(callback_data="confirm_quick_delete_post_20250512_044632")
    await bot_instance.handle_callback(update2, mock_context)
    # После удаления контекст должен быть очищен (None)
    assert bot_instance.state_manager.get_post_context(post_id) is None 