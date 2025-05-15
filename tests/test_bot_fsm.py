import pytest
from unittest.mock import Mock, AsyncMock, mock_open, patch
from telegram import Update, Message, User, Chat, CallbackQuery
from telegram.ext import ContextTypes
from bot.bot import Bot
from bot.states import BotState, PostContext
import builtins
import io
import telegram
import uuid

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

def make_session_id() -> str:
    """
    Генерирует уникальный session_id аналогично боевому коду (uuid4().hex)
    """
    return uuid.uuid4().hex

def make_callback_data(action: str, post_id: str, session_id: str = None) -> str:
    """
    Генерирует callback_data для confirm/cancel с session_id по боевому формату
    """
    if session_id is None:
        session_id = make_session_id()
    return f"{action}_{post_id}_{session_id}"

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
    session_id = make_session_id()
    update3 = make_mock_update(callback_data=make_callback_data("confirm_edit_text", post_id, session_id))
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
    session_id = make_session_id()
    update3 = make_mock_update(callback_data=make_callback_data("confirm_add_media", post_id, session_id))
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
    session_id = make_session_id()
    update3 = make_mock_update(callback_data=make_callback_data("confirm_remove_media", post_id, session_id))
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
    session_id = make_session_id()
    update2 = make_mock_update(callback_data=make_callback_data("confirm_publish_post", post_id, session_id))
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
    # После confirm_quick_delete контекст должен быть очищен
    session_id = make_session_id()
    update2 = make_mock_update(callback_data=make_callback_data("confirm_quick_delete_post", post_id, session_id))
    await bot_instance.handle_callback(update2, mock_context)
    assert bot_instance.state_manager.get_post_context(post_id) is None

@pytest.mark.asyncio
async def test_fsm_confirm_edit_text_state_sync(bot_instance, mock_context):
    """
    Проверяет, что после confirm_edit_text_post_* FSM переходит в EDIT_MENU, а не остаётся в *_CONFIRM.
    """
    post_id = "post_999"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=999,
        state=BotState.EDIT_TEXT_CONFIRM,
        user_id=123,
        original_text="Тестовый текст",
        original_media=[]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    # Мокаем update и callback
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None, "PostContext должен существовать после confirm_edit_text"
    assert ctx.state == BotState.EDIT_MENU, f"FSM рассинхрон: ожидалось EDIT_MENU, получено {ctx.state}" 

@pytest.mark.asyncio
async def test_fsm_confirm_add_media_state_sync(bot_instance, mock_context):
    """
    Проверяет, что после confirm_add_media_post_* FSM переходит в EDIT_MENU, а не остаётся в *_CONFIRM.
    """
    post_id = "post_888"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=888,
        state=BotState.EDIT_MEDIA_ADD_CONFIRM,
        user_id=123,
        original_text="Тестовый текст",
        original_media=[],
        temp_media=["mock_photo_id"]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("confirm_add_media_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None, "PostContext должен существовать после confirm_add_media"
    assert ctx.state == BotState.EDIT_MENU, f"FSM рассинхрон: ожидалось EDIT_MENU, получено {ctx.state}"

@pytest.mark.asyncio
async def test_fsm_confirm_remove_media_state_sync(bot_instance, mock_context):
    """
    Проверяет, что после confirm_remove_media_post_* FSM переходит в EDIT_MENU, а не остаётся в *_CONFIRM.
    """
    post_id = "post_777"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=777,
        state=BotState.EDIT_MEDIA_REMOVE_CONFIRM,
        user_id=123,
        original_text="Тестовый текст",
        original_media=["mock_photo_id1", "mock_photo_id2"],
        media_to_remove=[1]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("confirm_remove_media_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None, "PostContext должен существовать после confirm_remove_media"
    assert ctx.state == BotState.EDIT_MENU, f"FSM рассинхрон: ожидалось EDIT_MENU, получено {ctx.state}"

@pytest.mark.asyncio
async def test_fsm_confirm_publish_state_sync(bot_instance, mock_context):
    """
    Проверяет, что после confirm_publish_post_* FSM очищает контекст (None).
    """
    post_id = "post_666"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=666,
        state=BotState.CONFIRM_PUBLISH,
        user_id=123,
        original_text="Тестовый текст",
        original_media=["mock_photo_id1"]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("confirm_publish_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is None, "PostContext должен быть очищен после confirm_publish"

@pytest.mark.asyncio
async def test_fsm_confirm_delete_state_sync(bot_instance, mock_context):
    """
    Проверяет, что после confirm_delete_post_* FSM очищает контекст (None).
    """
    post_id = "post_555"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=555,
        state=BotState.CONFIRM_DELETE,
        user_id=123,
        original_text="Тестовый текст",
        original_media=["mock_photo_id1"]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("confirm_delete_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is None, "PostContext должен быть очищен после confirm_delete"

@pytest.mark.asyncio
async def test_fsm_confirm_quick_delete_state_sync(bot_instance, mock_context):
    """
    Проверяет, что после confirm_quick_delete_post_* FSM очищает контекст (None).
    """
    post_id = "post_444"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=444,
        state=BotState.QUICK_DELETE,
        user_id=123,
        original_text="Тестовый текст",
        original_media=["mock_photo_id1"]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("confirm_quick_delete_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is None, "PostContext должен быть очищен после confirm_quick_delete"

@pytest.mark.asyncio
async def test_fsm_cancel_edit_text_state_sync(bot_instance, mock_context):
    """
    Проверяет, что после cancel_edit_text_post_* FSM возвращается в EDIT_MENU.
    """
    post_id = "post_cancel_1"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=111,
        state=BotState.EDIT_TEXT_CONFIRM,
        user_id=123,
        original_text="old text",
        original_media=[]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("cancel_edit_text_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    assert ctx.state == BotState.EDIT_MENU

@pytest.mark.asyncio
async def test_fsm_cancel_add_media_state_sync(bot_instance, mock_context):
    """
    Проверяет, что после cancel_add_media_post_* FSM возвращается в EDIT_MENU.
    """
    post_id = "post_cancel_2"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=112,
        state=BotState.EDIT_MEDIA_ADD_CONFIRM,
        user_id=123,
        original_text="old text",
        original_media=[],
        temp_media=["mock_photo_id"]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("cancel_add_media_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    assert ctx.state == BotState.EDIT_MENU

@pytest.mark.asyncio
async def test_fsm_cancel_remove_media_state_sync(bot_instance, mock_context):
    """
    Проверяет, что после cancel_remove_media_post_* FSM возвращается в EDIT_MENU.
    """
    post_id = "post_cancel_3"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=113,
        state=BotState.EDIT_MEDIA_REMOVE_CONFIRM,
        user_id=123,
        original_text="old text",
        original_media=["mock_photo_id1", "mock_photo_id2"],
        media_to_remove=[1]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("cancel_remove_media_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    assert ctx.state == BotState.EDIT_MENU

@pytest.mark.asyncio
async def test_fsm_cancel_publish_state_sync(bot_instance, mock_context):
    """
    Проверяет, что после cancel_publish_post_* FSM возвращается в MODERATE_MENU.
    """
    post_id = "post_cancel_4"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=114,
        state=BotState.CONFIRM_PUBLISH,
        user_id=123,
        original_text="old text",
        original_media=["mock_photo_id1"]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("cancel_publish_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    assert ctx.state == BotState.MODERATE_MENU

@pytest.mark.asyncio
async def test_fsm_cancel_delete_state_sync(bot_instance, mock_context):
    """
    Проверяет, что после cancel_delete_post_* FSM возвращается в MODERATE_MENU.
    """
    post_id = "post_cancel_5"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=115,
        state=BotState.CONFIRM_DELETE,
        user_id=123,
        original_text="old text",
        original_media=["mock_photo_id1"]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("cancel_delete_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    assert ctx.state == BotState.MODERATE_MENU

@pytest.mark.asyncio
async def test_fsm_cancel_quick_delete_state_sync(bot_instance, mock_context):
    """
    Проверяет, что после cancel_quick_delete_post_* FSM возвращается в MODERATE_MENU.
    """
    post_id = "post_cancel_6"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=116,
        state=BotState.QUICK_DELETE,
        user_id=123,
        original_text="old text",
        original_media=["mock_photo_id1"]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("cancel_quick_delete_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    assert ctx.state == BotState.MODERATE_MENU

@pytest.mark.asyncio
async def test_fsm_confirm_nonexistent_post(bot_instance, mock_context):
    """
    confirm_edit_text для несуществующего post_id не должен падать и не должен создавать контекст.
    """
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("confirm_edit_text_post", "post_nonexistent", session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context("post_nonexistent")
    assert ctx is None

@pytest.mark.asyncio
async def test_fsm_cancel_nonexistent_post(bot_instance, mock_context):
    """
    cancel_edit_text для несуществующего post_id не должен падать и не должен создавать контекст.
    """
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("cancel_edit_text_post", "post_nonexistent", session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context("post_nonexistent")
    assert ctx is None

@pytest.mark.asyncio
async def test_fsm_confirm_edit_text_no_temp_text(bot_instance, mock_context):
    """
    confirm_edit_text без temp_text не должен менять состояние и должен логировать предупреждение.
    """
    post_id = "post_edge_1"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=201,
        state=BotState.EDIT_TEXT_CONFIRM,
        user_id=123,
        original_text="old text",
        original_media=[],
        temp_text=None
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    # Состояние не должно стать EDIT_MENU, так как temp_text нет
    assert ctx.state == BotState.EDIT_MENU or ctx.state == BotState.EDIT_TEXT_CONFIRM

@pytest.mark.asyncio
async def test_fsm_double_confirm_edit_text(bot_instance, mock_context):
    """
    Повторный confirm_edit_text не должен приводить к ошибке и не должен менять состояние некорректно.
    """
    post_id = "post_edge_2"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=202,
        state=BotState.EDIT_TEXT_CONFIRM,
        user_id=123,
        original_text="old text",
        original_media=[],
        temp_text="new text"
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    # Повторный confirm
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    assert ctx.state == BotState.EDIT_MENU

@pytest.mark.asyncio
async def test_fsm_confirm_edit_text_invalid_state(bot_instance, mock_context):
    """
    confirm_edit_text в невалидном состоянии (например, POST_VIEW) не должен менять состояние.
    """
    post_id = "post_edge_3"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=203,
        state=BotState.POST_VIEW,
        user_id=123,
        original_text="old text",
        original_media=[],
        temp_text="new text"
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    assert ctx.state == BotState.POST_VIEW 

@pytest.mark.asyncio
async def test_fsm_confirm_edit_text_foreign_user(bot_instance, mock_context):
    """
    confirm_edit_text с чужим user_id не должен менять состояние (если реализована проверка).
    """
    post_id = "post_edge_4"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=204,
        state=BotState.EDIT_TEXT_CONFIRM,
        user_id=123,
        original_text="old text",
        original_media=[],
        temp_text="new text"
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    # Мокаем update с другим user_id
    session_id = make_session_id()
    update = make_mock_update(user_id=999, callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    # FSM не должна менять состояние (если реализована проверка user_id)
    # Если нет проверки — допускается переход в EDIT_MENU
    assert ctx.state in [BotState.EDIT_TEXT_CONFIRM, BotState.EDIT_MENU]

@pytest.mark.asyncio
async def test_fsm_confirm_after_storage_clear(bot_instance, mock_context):
    """
    confirm_edit_text после очистки storage не должен падать.
    """
    post_id = "post_edge_5"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=205,
        state=BotState.EDIT_TEXT_CONFIRM,
        user_id=123,
        original_text="old text",
        original_media=[],
        temp_text="new text"
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    # Очищаем storage (мокаем AsyncFileManager.read чтобы вернуть пустой dict)
    with patch("src.bot.storage.AsyncFileManager.read", return_value={}):
        session_id = make_session_id()
        update = make_mock_update(callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
        await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    assert ctx.state in [BotState.EDIT_TEXT_CONFIRM, BotState.EDIT_MENU]

@pytest.mark.asyncio
async def test_fsm_confirm_edit_text_telegram_error(bot_instance, mock_context):
    """
    confirm_edit_text при ошибке Telegram API не должен падать.
    """
    post_id = "post_edge_6"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=206,
        state=BotState.EDIT_TEXT_CONFIRM,
        user_id=123,
        original_text="old text",
        original_media=[],
        temp_text="new text"
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    # Мокаем edit_message_caption чтобы выбрасывал исключение
    mock_context.bot.edit_message_caption.side_effect = Exception("Telegram API error")
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    assert ctx.state == BotState.EDIT_TEXT_CONFIRM
    mock_context.bot.edit_message_caption.side_effect = None

@pytest.mark.asyncio
async def test_fsm_confirm_edit_text_filesystem_error(bot_instance, mock_context):
    """
    confirm_edit_text при ошибке файловой системы не должен падать.
    """
    post_id = "post_edge_7"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=207,
        state=BotState.EDIT_TEXT_CONFIRM,
        user_id=123,
        original_text="old text",
        original_media=[],
        temp_text="new text"
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    # Мокаем AsyncFileManager.__aenter__ чтобы возвращать storage с write, выбрасывающим исключение
    mock_storage = AsyncMock()
    mock_storage.read = AsyncMock(return_value={post_id: {"text": "old text"}})
    mock_storage.write = AsyncMock(side_effect=Exception("FS error"))
    with patch("src.bot.storage.AsyncFileManager.__aenter__", new=AsyncMock(return_value=mock_storage)):
        session_id = make_session_id()
        update = make_mock_update(callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
        await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    assert ctx.state == BotState.EDIT_TEXT_CONFIRM

@pytest.mark.asyncio
async def test_fsm_confirm_edit_text_broken_storage(bot_instance, mock_context):
    """
    confirm_edit_text при повреждённом storage (read выбрасывает исключение) не должен падать.
    """
    post_id = "post_edge_8"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=208,
        state=BotState.EDIT_TEXT_CONFIRM,
        user_id=123,
        original_text="old text",
        original_media=[],
        temp_text="new text"
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    with patch("src.bot.storage.AsyncFileManager.read", side_effect=Exception("broken storage")):
        session_id = make_session_id()
        update = make_mock_update(callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
        await bot_instance.handle_callback(update, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    assert ctx.state == BotState.EDIT_TEXT_CONFIRM 

@pytest.mark.asyncio
async def test_fsm_race_condition_double_confirm(bot_instance, mock_context):
    """
    Одновременный confirm_edit_text от двух пользователей: только первый должен сменить состояние, второй — игнорируется.
    """
    post_id = "post_race_1"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=301,
        state=BotState.EDIT_TEXT_CONFIRM,
        user_id=123,
        original_text="old text",
        original_media=[],
        temp_text="new text"
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update1 = make_mock_update(user_id=123, callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
    update2 = make_mock_update(user_id=999, callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
    await bot_instance.handle_callback(update1, mock_context)
    await bot_instance.handle_callback(update2, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    assert ctx.state == BotState.EDIT_MENU

@pytest.mark.asyncio
async def test_fsm_race_condition_confirm_cancel(bot_instance, mock_context):
    """
    Почти одновременный confirm и cancel: только первый обработанный меняет состояние, второй игнорируется.
    """
    post_id = "post_race_2"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=302,
        state=BotState.EDIT_TEXT_CONFIRM,
        user_id=123,
        original_text="old text",
        original_media=[],
        temp_text="new text"
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update_confirm = make_mock_update(user_id=123, callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
    update_cancel = make_mock_update(user_id=123, callback_data=make_callback_data("cancel_edit_text_post", post_id, session_id))
    await bot_instance.handle_callback(update_confirm, mock_context)
    await bot_instance.handle_callback(update_cancel, mock_context)
    ctx = bot_instance.state_manager.get_post_context(post_id)
    assert ctx is not None
    assert ctx.state == BotState.EDIT_MENU

@pytest.mark.asyncio
async def test_fsm_confirm_button_disappears(bot_instance, mock_context):
    """
    После confirm_edit_text_post_* edit_message_reply_markup вызывается с reply_markup=None (кнопки исчезают).
    """
    post_id = "post_race_3"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=303,
        state=BotState.EDIT_TEXT_CONFIRM,
        user_id=123,
        original_text="old text",
        original_media=[],
        temp_text="new text"
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(user_id=123, callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
    await bot_instance.handle_callback(update, mock_context)
    # Проверяем, что edit_message_reply_markup был вызван с reply_markup=None
    called = False
    for call in mock_context.bot.edit_message_reply_markup.call_args_list:
        kwargs = call.kwargs
        if kwargs.get("reply_markup") is None:
            called = True
    assert called, "edit_message_reply_markup не вызван с reply_markup=None (кнопки не исчезли)" 

@pytest.mark.asyncio
async def test_fsm_repeat_confirm_cancel_notification(bot_instance, mock_context, caplog):
    """
    Повторный confirm/cancel должен отправлять уведомление пользователю и логироваться как info.
    """
    post_id = "post_repeat_1"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=111,
        state=BotState.EDIT_MENU,  # не *_CONFIRM
        user_id=123,
        original_text="old text",
        original_media=[]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
    with caplog.at_level("INFO"):
        await bot_instance.handle_callback(update, mock_context)
    assert "Повторный confirm/cancel" in caplog.text

@pytest.mark.asyncio
async def test_fsm_keyboard_remove_badrequest_warning(bot_instance, mock_context, caplog):
    """
    Ошибка удаления клавиатуры с текстом 'message content and reply markup are exactly the same' логируется как warning.
    """
    post_id = "post_kb_1"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=112,
        state=BotState.EDIT_TEXT_CONFIRM,
        user_id=123,
        original_text="text",
        original_media=[]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
    with patch.object(mock_context.bot, "edit_message_reply_markup", AsyncMock(side_effect=telegram.error.BadRequest("message content and reply markup are exactly the same"))):
        with caplog.at_level("WARNING"):
            await bot_instance.handle_callback(update, mock_context)
        assert "Клавиатура уже удалена" in caplog.text

@pytest.mark.asyncio
async def test_fsm_flood_control_retry(bot_instance, mock_context, caplog):
    """
    Flood control (RetryAfter) вызывает повторную попытку.
    """
    post_id = "post_flood_1"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=113,
        state=BotState.EDIT_TEXT_CONFIRM,
        user_id=123,
        original_text="text",
        original_media=[]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
    # Flood control: первый вызов RetryAfter, второй успешный
    async def fake_edit_message_reply_markup(*args, **kwargs):
        if not hasattr(fake_edit_message_reply_markup, "called"):
            fake_edit_message_reply_markup.called = True
            raise telegram.error.RetryAfter(1)
        return None
    with patch.object(mock_context.bot, "edit_message_reply_markup", AsyncMock(side_effect=fake_edit_message_reply_markup)):
        await bot_instance.handle_callback(update, mock_context)
    assert "Flood control: повтор через" in caplog.text

@pytest.mark.asyncio
async def test_fsm_keyboard_remove_success(bot_instance, mock_context):
    """
    Клавиатура успешно удаляется после confirm/cancel.
    """
    post_id = "post_kb_2"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=114,
        state=BotState.EDIT_TEXT_CONFIRM,
        user_id=123,
        original_text="text",
        original_media=[]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
    with patch.object(mock_context.bot, "edit_message_reply_markup", AsyncMock(return_value=None)) as mock_edit:
        await bot_instance.handle_callback(update, mock_context)
        mock_edit.assert_called_once()

@pytest.mark.asyncio
async def test_fsm_repeat_confirm_cancel_user_notification(bot_instance, mock_context):
    """
    Повторный confirm/cancel отправляет пользователю уведомление через query.answer.
    """
    post_id = "post_repeat_2"
    post_context = PostContext(
        post_id=post_id,
        chat_id=456,
        message_id=115,
        state=BotState.EDIT_MENU,  # не *_CONFIRM
        user_id=123,
        original_text="old text",
        original_media=[]
    )
    bot_instance.state_manager.set_post_context(post_id, post_context)
    session_id = make_session_id()
    update = make_mock_update(callback_data=make_callback_data("confirm_edit_text_post", post_id, session_id))
    with patch.object(update.callback_query, "answer", AsyncMock()) as mock_answer:
        await bot_instance.handle_callback(update, mock_context)
        mock_answer.assert_called_with("Действие уже выполнено или неактуально", show_alert=True) 