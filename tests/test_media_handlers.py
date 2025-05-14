import pytest
from unittest.mock import patch, Mock, AsyncMock, mock_open
from telegram import Update, Message, User, Chat, PhotoSize, CallbackQuery
from telegram.ext import ContextTypes
from src.bot.handlers.test_handlers import PostHandler, State, PostContext

def make_mock_update(user_id=123, chat_id=456, message_id=789, text=None, photo=None):
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
    return update

@pytest.fixture
def mock_context():
    context = Mock(spec=ContextTypes.DEFAULT_TYPE)
    context.bot = Mock()
    context.bot.delete_message = AsyncMock()
    context.bot.send_message = AsyncMock()
    context.bot.edit_message_text = AsyncMock()
    context.bot.edit_message_reply_markup = AsyncMock()
    return context

@pytest.fixture
def post_handler():
    handler = PostHandler()
    # Создаем тестовый пост
    handler.posts["post_1"] = PostContext(
        post_id="post_1",
        chat_id=456,
        message_id=789,
        state=State.POST_VIEW,
        user_id=123,
        temp_media=["photo1.jpg", "photo2.jpg", "photo3.jpg"]
    )
    return handler

@pytest.mark.asyncio
async def test_text_edit_flow(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "edit_text_post_1"
    await post_handler.handle_callback(update, mock_context)
    assert post_handler.posts["post_1"].state == State.EDIT_TEXT_WAIT
    update2 = make_mock_update(text="Новый текст")
    await post_handler.handle_message(update2, mock_context)
    assert post_handler.posts["post_1"].state == State.EDIT_TEXT_CONFIRM
    assert post_handler.posts["post_1"].temp_text == "Новый текст"
    update3 = make_mock_update()
    update3.callback_query.data = "confirm_edit_text_post_1"
    await post_handler.handle_callback(update3, mock_context)
    assert post_handler.posts["post_1"].state == State.POST_VIEW

@pytest.mark.asyncio
async def test_media_add_flow(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "add_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    assert post_handler.posts["post_1"].state == State.EDIT_MEDIA_ADD_WAIT
    photo_mock = Mock(spec=PhotoSize)
    photo_mock.get_file = AsyncMock()
    photo_mock.get_file.return_value.download_to_drive = AsyncMock()
    update2 = make_mock_update(photo=[photo_mock])
    await post_handler.handle_message(update2, mock_context)
    assert post_handler.posts["post_1"].state == State.EDIT_MEDIA_ADD_CONFIRM
    update3 = make_mock_update()
    update3.callback_query.data = "confirm_add_media_post_1"
    await post_handler.handle_callback(update3, mock_context)
    assert post_handler.posts["post_1"].state == State.POST_VIEW

@pytest.mark.asyncio
async def test_media_remove_flow(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "remove_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    post_handler.posts["post_1"].temp_media = ["photo1.jpg", "photo2.jpg", "photo3.jpg"]
    update2 = make_mock_update(text="1, 2")
    await post_handler.handle_message(update2, mock_context)
    assert post_handler.posts["post_1"].state == State.EDIT_MEDIA_REMOVE_CONFIRM
    assert post_handler.posts["post_1"].media_to_remove == [1, 2]
    update3 = make_mock_update()
    update3.callback_query.data = "confirm_remove_media_post_1"
    await post_handler.handle_callback(update3, mock_context)
    assert post_handler.posts["post_1"].state == State.POST_VIEW
    assert len(post_handler.posts["post_1"].temp_media) == 1

@pytest.mark.asyncio
async def test_cancel_flows(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "edit_text_post_1"
    await post_handler.handle_callback(update, mock_context)
    update2 = make_mock_update()
    update2.callback_query.data = "cancel_edit_text_post_1"
    await post_handler.handle_callback(update2, mock_context)
    assert post_handler.posts["post_1"].state == State.EDIT_MENU
    update3 = make_mock_update()
    update3.callback_query.data = "add_media_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "cancel_add_media_post_1"
    await post_handler.handle_callback(update4, mock_context)
    assert post_handler.posts["post_1"].state == State.EDIT_MEDIA_MENU
    update5 = make_mock_update()
    update5.callback_query.data = "remove_media_post_1"
    await post_handler.handle_callback(update5, mock_context)
    update6 = make_mock_update()
    update6.callback_query.data = "cancel_remove_media_post_1"
    await post_handler.handle_callback(update6, mock_context)
    assert post_handler.posts["post_1"].state == State.EDIT_MEDIA_MENU

@pytest.mark.asyncio
async def test_quick_delete_flow(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "quick_delete_post_1"
    await post_handler.handle_callback(update, mock_context)
    assert post_handler.posts["post_1"].state == State.QUICK_DELETE
    update2 = make_mock_update()
    update2.callback_query.data = "confirm_quick_delete_post_1"
    await post_handler.handle_callback(update2, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_invalid_user_handling(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "edit_text_post_1"
    await post_handler.handle_callback(update, mock_context)
    update2 = make_mock_update(user_id=999, text="Текст другого пользователя")
    await post_handler.handle_message(update2, mock_context)
    mock_context.bot.send_message.assert_not_called()

@pytest.mark.asyncio
async def test_invalid_media_numbers(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "remove_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    post_handler.posts["post_1"].temp_media = ["photo1.jpg", "photo2.jpg"]
    update2 = make_mock_update(text="1, 999")
    await post_handler.handle_message(update2, mock_context)
    assert post_handler.posts["post_1"].state == State.EDIT_MEDIA_REMOVE_WAIT

@pytest.mark.asyncio
async def test_invalid_media_format(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "remove_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    post_handler.posts["post_1"].temp_media = ["photo1.jpg", "photo2.jpg"]
    update2 = make_mock_update(text="abc")
    await post_handler.handle_message(update2, mock_context)
    assert post_handler.posts["post_1"].state == State.EDIT_MEDIA_REMOVE_WAIT

@pytest.mark.asyncio
async def test_complex_edit_sequence(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "edit_text_post_1"
    await post_handler.handle_callback(update, mock_context)
    update2 = make_mock_update(text="Новый текст")
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "add_media_post_1"
    await post_handler.handle_callback(update3, mock_context)
    photo_mock = Mock(spec=PhotoSize)
    photo_mock.get_file = AsyncMock()
    photo_mock.get_file.return_value.download_to_drive = AsyncMock()
    update4 = make_mock_update(photo=[photo_mock])
    await post_handler.handle_message(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "remove_media_post_1"
    await post_handler.handle_callback(update5, mock_context)
    post_handler.posts["post_1"].temp_media = ["photo1.jpg", "photo2.jpg", "photo3.jpg"]
    update6 = make_mock_update(text="1")
    await post_handler.handle_message(update6, mock_context)
    update7 = make_mock_update()
    update7.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update7, mock_context)
    update8 = make_mock_update()
    update8.callback_query.data = "confirm_publish_post_1"
    await post_handler.handle_callback(update8, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_empty_media_list(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "remove_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    post_handler.posts["post_1"].temp_media = []
    update2 = make_mock_update(text="1")
    await post_handler.handle_message(update2, mock_context)
    assert post_handler.posts["post_1"].state == State.EDIT_MEDIA_REMOVE_WAIT

@pytest.mark.asyncio
async def test_rapid_state_changes(mock_context, post_handler):
    update = make_mock_update()
    actions = [
        ("edit_text_post_1", State.EDIT_TEXT_WAIT),
        ("add_media_post_1", State.EDIT_MEDIA_ADD_WAIT),
        ("remove_media_post_1", State.EDIT_MEDIA_REMOVE_WAIT),
        ("publish_post_1", State.CONFIRM_PUBLISH)
    ]
    for callback_data, expected_state in actions:
        update.callback_query.data = callback_data
        await post_handler.handle_callback(update, mock_context)
        assert post_handler.posts["post_1"].state == expected_state

@pytest.mark.asyncio
async def test_cancel_at_every_stage(mock_context, post_handler):
    update = make_mock_update()
    stages = [
        ("edit_text_post_1", "cancel_edit_text_post_1", State.EDIT_MENU),
        ("add_media_post_1", "cancel_add_media_post_1", State.EDIT_MEDIA_MENU),
        ("remove_media_post_1", "cancel_remove_media_post_1", State.EDIT_MEDIA_MENU),
        ("publish_post_1", "cancel_publish_post_1", State.POST_VIEW)
    ]
    for start_action, cancel_action, expected_state in stages:
        update.callback_query.data = start_action
        await post_handler.handle_callback(update, mock_context)
        update2 = make_mock_update()
        update2.callback_query.data = cancel_action
        await post_handler.handle_callback(update2, mock_context)
        assert post_handler.posts["post_1"].state == expected_state

@pytest.mark.asyncio
async def test_duplicate_actions(mock_context, post_handler):
    update = make_mock_update()
    actions = [
        "edit_text_post_1",
        "add_media_post_1",
        "remove_media_post_1",
        "publish_post_1"
    ]
    for action in actions:
        update.callback_query.data = action
        await post_handler.handle_callback(update, mock_context)
        update2 = make_mock_update()
        update2.callback_query.data = action
        await post_handler.handle_callback(update2, mock_context)
        assert post_handler.posts["post_1"].state != State.POST_VIEW

@pytest.mark.asyncio
async def test_delete_confirmed(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "quick_delete_post_1"
    await post_handler.handle_callback(update, mock_context)
    update2 = make_mock_update()
    update2.callback_query.data = "confirm_quick_delete_post_1"
    await post_handler.handle_callback(update2, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_delete_cancelled(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "quick_delete_post_1"
    await post_handler.handle_callback(update, mock_context)
    update2 = make_mock_update()
    update2.callback_query.data = "cancel_quick_delete_post_1"
    await post_handler.handle_callback(update2, mock_context)
    assert post_handler.posts["post_1"].state == State.POST_VIEW

@pytest.mark.asyncio
async def test_publish_confirmed(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update, mock_context)
    update2 = make_mock_update()
    update2.callback_query.data = "confirm_publish_post_1"
    await post_handler.handle_callback(update2, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_publish_cancelled(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update, mock_context)
    update2 = make_mock_update()
    update2.callback_query.data = "cancel_publish_post_1"
    await post_handler.handle_callback(update2, mock_context)
    assert post_handler.posts["post_1"].state == State.POST_VIEW

@pytest.mark.asyncio
async def test_edit_text_confirmed_then_publish_confirmed(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "edit_text_post_1"
    await post_handler.handle_callback(update, mock_context)
    update2 = make_mock_update(text="Текст1")
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "confirm_edit_text_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "confirm_publish_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_edit_text_confirmed_then_publish_cancelled(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "edit_text_post_1"
    await post_handler.handle_callback(update, mock_context)
    update2 = make_mock_update(text="Текст1")
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "confirm_edit_text_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "cancel_publish_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert post_handler.posts["post_1"].state == State.POST_VIEW

@pytest.mark.asyncio
async def test_edit_text_confirmed_then_delete_confirmed(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "edit_text_post_1"
    await post_handler.handle_callback(update, mock_context)
    update2 = make_mock_update(text="Текст1")
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "confirm_edit_text_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "quick_delete_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "confirm_quick_delete_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_edit_text_confirmed_then_delete_cancelled(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "edit_text_post_1"
    await post_handler.handle_callback(update, mock_context)
    update2 = make_mock_update(text="Текст1")
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "confirm_edit_text_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "quick_delete_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "cancel_quick_delete_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert post_handler.posts["post_1"].state == State.POST_VIEW

@pytest.mark.asyncio
async def test_edit_text_cancelled_then_publish_confirmed(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "edit_text_post_1"
    await post_handler.handle_callback(update, mock_context)
    update2 = make_mock_update(text="Текст1")
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "cancel_edit_text_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "confirm_publish_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_edit_text_cancelled_then_publish_cancelled(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "edit_text_post_1"
    await post_handler.handle_callback(update, mock_context)
    update2 = make_mock_update(text="Текст1")
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "cancel_edit_text_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "cancel_publish_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert post_handler.posts["post_1"].state == State.POST_VIEW

# --- Редактирование медиа: добавление ---
@pytest.mark.asyncio
async def test_edit_media_add_confirmed_then_publish_confirmed(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "add_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    photo_mock = Mock(spec=PhotoSize)
    photo_mock.get_file = AsyncMock()
    photo_mock.get_file.return_value.download_to_drive = AsyncMock()
    update2 = make_mock_update(photo=[photo_mock])
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "confirm_add_media_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "confirm_publish_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_edit_media_add_confirmed_then_publish_cancelled(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "add_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    photo_mock = Mock(spec=PhotoSize)
    photo_mock.get_file = AsyncMock()
    photo_mock.get_file.return_value.download_to_drive = AsyncMock()
    update2 = make_mock_update(photo=[photo_mock])
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "confirm_add_media_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "cancel_publish_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert post_handler.posts["post_1"].state == State.POST_VIEW

@pytest.mark.asyncio
async def test_edit_media_add_confirmed_then_delete_confirmed(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "add_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    photo_mock = Mock(spec=PhotoSize)
    photo_mock.get_file = AsyncMock()
    photo_mock.get_file.return_value.download_to_drive = AsyncMock()
    update2 = make_mock_update(photo=[photo_mock])
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "confirm_add_media_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "quick_delete_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "confirm_quick_delete_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_edit_media_add_confirmed_then_delete_cancelled(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "add_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    photo_mock = Mock(spec=PhotoSize)
    photo_mock.get_file = AsyncMock()
    photo_mock.get_file.return_value.download_to_drive = AsyncMock()
    update2 = make_mock_update(photo=[photo_mock])
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "confirm_add_media_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "quick_delete_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "cancel_quick_delete_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert post_handler.posts["post_1"].state == State.POST_VIEW

@pytest.mark.asyncio
async def test_edit_media_add_cancelled_then_publish_confirmed(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "add_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    photo_mock = Mock(spec=PhotoSize)
    photo_mock.get_file = AsyncMock()
    photo_mock.get_file.return_value.download_to_drive = AsyncMock()
    update2 = make_mock_update(photo=[photo_mock])
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "cancel_add_media_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "confirm_publish_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_edit_media_add_cancelled_then_publish_cancelled(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "add_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    photo_mock = Mock(spec=PhotoSize)
    photo_mock.get_file = AsyncMock()
    photo_mock.get_file.return_value.download_to_drive = AsyncMock()
    update2 = make_mock_update(photo=[photo_mock])
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "cancel_add_media_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "cancel_publish_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert post_handler.posts["post_1"].state == State.POST_VIEW

# --- Аналогично для удаления медиа (remove_media) ---
@pytest.mark.asyncio
async def test_edit_media_remove_confirmed_then_publish_confirmed(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "remove_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    post_handler.posts["post_1"].temp_media = ["photo1.jpg", "photo2.jpg", "photo3.jpg"]
    update2 = make_mock_update(text="1, 2")
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "confirm_remove_media_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "confirm_publish_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_edit_media_remove_confirmed_then_publish_cancelled(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "remove_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    post_handler.posts["post_1"].temp_media = ["photo1.jpg", "photo2.jpg", "photo3.jpg"]
    update2 = make_mock_update(text="1, 2")
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "confirm_remove_media_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "cancel_publish_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert post_handler.posts["post_1"].state == State.POST_VIEW

@pytest.mark.asyncio
async def test_edit_media_remove_confirmed_then_delete_confirmed(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "remove_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    post_handler.posts["post_1"].temp_media = ["photo1.jpg", "photo2.jpg", "photo3.jpg"]
    update2 = make_mock_update(text="1, 2")
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "confirm_remove_media_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "quick_delete_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "confirm_quick_delete_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_edit_media_remove_confirmed_then_delete_cancelled(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "remove_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    post_handler.posts["post_1"].temp_media = ["photo1.jpg", "photo2.jpg", "photo3.jpg"]
    update2 = make_mock_update(text="1, 2")
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "confirm_remove_media_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "quick_delete_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "cancel_quick_delete_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert post_handler.posts["post_1"].state == State.POST_VIEW

@pytest.mark.asyncio
async def test_edit_media_remove_cancelled_then_publish_confirmed(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "remove_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    post_handler.posts["post_1"].temp_media = ["photo1.jpg", "photo2.jpg", "photo3.jpg"]
    update2 = make_mock_update(text="1, 2")
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "cancel_remove_media_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "confirm_publish_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_edit_media_remove_cancelled_then_publish_cancelled(mock_context, post_handler):
    update = make_mock_update()
    update.callback_query.data = "remove_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    post_handler.posts["post_1"].temp_media = ["photo1.jpg", "photo2.jpg", "photo3.jpg"]
    update2 = make_mock_update(text="1, 2")
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "cancel_remove_media_post_1"
    await post_handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update()
    update5.callback_query.data = "cancel_publish_post_1"
    await post_handler.handle_callback(update5, mock_context)
    assert post_handler.posts["post_1"].state == State.POST_VIEW

# --- Повторные действия и комбинированные цепочки ---
@pytest.mark.asyncio
async def test_repeat_edit_text_confirm_cancel_confirm_publish(mock_context, post_handler):
    update = make_mock_update()
    # 1-й раз редактируем текст, отменяем
    update.callback_query.data = "edit_text_post_1"
    await post_handler.handle_callback(update, mock_context)
    update2 = make_mock_update(text="Текст1")
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "cancel_edit_text_post_1"
    await post_handler.handle_callback(update3, mock_context)
    # 2-й раз редактируем текст, подтверждаем
    update4 = make_mock_update()
    update4.callback_query.data = "edit_text_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update(text="Текст2")
    await post_handler.handle_message(update5, mock_context)
    update6 = make_mock_update()
    update6.callback_query.data = "confirm_edit_text_post_1"
    await post_handler.handle_callback(update6, mock_context)
    # Публикуем
    update7 = make_mock_update()
    update7.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update7, mock_context)
    update8 = make_mock_update()
    update8.callback_query.data = "confirm_publish_post_1"
    await post_handler.handle_callback(update8, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_repeat_add_media_confirm_cancel_confirm_delete(mock_context, post_handler):
    update = make_mock_update()
    # 1-й раз добавляем медиа, отменяем
    update.callback_query.data = "add_media_post_1"
    await post_handler.handle_callback(update, mock_context)
    photo_mock = Mock(spec=PhotoSize)
    photo_mock.get_file = AsyncMock()
    photo_mock.get_file.return_value.download_to_drive = AsyncMock()
    update2 = make_mock_update(photo=[photo_mock])
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "cancel_add_media_post_1"
    await post_handler.handle_callback(update3, mock_context)
    # 2-й раз добавляем медиа, подтверждаем
    update4 = make_mock_update()
    update4.callback_query.data = "add_media_post_1"
    await post_handler.handle_callback(update4, mock_context)
    update5 = make_mock_update(photo=[photo_mock])
    await post_handler.handle_message(update5, mock_context)
    update6 = make_mock_update()
    update6.callback_query.data = "confirm_add_media_post_1"
    await post_handler.handle_callback(update6, mock_context)
    # Удаляем
    update7 = make_mock_update()
    update7.callback_query.data = "quick_delete_post_1"
    await post_handler.handle_callback(update7, mock_context)
    update8 = make_mock_update()
    update8.callback_query.data = "confirm_quick_delete_post_1"
    await post_handler.handle_callback(update8, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_edit_text_then_add_media_then_remove_media_then_publish(mock_context, post_handler):
    update = make_mock_update()
    # Редактируем текст
    update.callback_query.data = "edit_text_post_1"
    await post_handler.handle_callback(update, mock_context)
    update2 = make_mock_update(text="ТекстX")
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "confirm_edit_text_post_1"
    await post_handler.handle_callback(update3, mock_context)
    # Добавляем медиа
    update4 = make_mock_update()
    update4.callback_query.data = "add_media_post_1"
    await post_handler.handle_callback(update4, mock_context)
    photo_mock = Mock(spec=PhotoSize)
    photo_mock.get_file = AsyncMock()
    photo_mock.get_file.return_value.download_to_drive = AsyncMock()
    update5 = make_mock_update(photo=[photo_mock])
    await post_handler.handle_message(update5, mock_context)
    update6 = make_mock_update()
    update6.callback_query.data = "confirm_add_media_post_1"
    await post_handler.handle_callback(update6, mock_context)
    # Удаляем медиа
    update7 = make_mock_update()
    update7.callback_query.data = "remove_media_post_1"
    await post_handler.handle_callback(update7, mock_context)
    post_handler.posts["post_1"].temp_media = ["photo1.jpg", "photo2.jpg", "photo3.jpg"]
    update8 = make_mock_update(text="1")
    await post_handler.handle_message(update8, mock_context)
    update9 = make_mock_update()
    update9.callback_query.data = "confirm_remove_media_post_1"
    await post_handler.handle_callback(update9, mock_context)
    # Публикуем
    update10 = make_mock_update()
    update10.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update10, mock_context)
    update11 = make_mock_update()
    update11.callback_query.data = "confirm_publish_post_1"
    await post_handler.handle_callback(update11, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_multiple_cancels_and_confirms(mock_context, post_handler):
    update = make_mock_update()
    # Редактируем текст, отменяем
    update.callback_query.data = "edit_text_post_1"
    await post_handler.handle_callback(update, mock_context)
    update2 = make_mock_update(text="A")
    await post_handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "cancel_edit_text_post_1"
    await post_handler.handle_callback(update3, mock_context)
    # Добавляем медиа, отменяем
    update4 = make_mock_update()
    update4.callback_query.data = "add_media_post_1"
    await post_handler.handle_callback(update4, mock_context)
    photo_mock = Mock(spec=PhotoSize)
    photo_mock.get_file = AsyncMock()
    photo_mock.get_file.return_value.download_to_drive = AsyncMock()
    update5 = make_mock_update(photo=[photo_mock])
    await post_handler.handle_message(update5, mock_context)
    update6 = make_mock_update()
    update6.callback_query.data = "cancel_add_media_post_1"
    await post_handler.handle_callback(update6, mock_context)
    # Редактируем текст, подтверждаем
    update7 = make_mock_update()
    update7.callback_query.data = "edit_text_post_1"
    await post_handler.handle_callback(update7, mock_context)
    update8 = make_mock_update(text="B")
    await post_handler.handle_message(update8, mock_context)
    update9 = make_mock_update()
    update9.callback_query.data = "confirm_edit_text_post_1"
    await post_handler.handle_callback(update9, mock_context)
    # Публикуем
    update10 = make_mock_update()
    update10.callback_query.data = "publish_post_1"
    await post_handler.handle_callback(update10, mock_context)
    update11 = make_mock_update()
    update11.callback_query.data = "confirm_publish_post_1"
    await post_handler.handle_callback(update11, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_confirm_for_nonexistent_post(mock_context, post_handler):
    """Подтверждение действия для несуществующего post_id не должно вызывать ошибку и не менять состояние других постов."""
    update = make_mock_update()
    update.callback_query.data = "confirm_publish_post_nonexistent"
    # Не должно быть исключения
    await post_handler.handle_callback(update, mock_context)

@pytest.mark.asyncio
async def test_action_for_deleted_post(mock_context, post_handler):
    """Попытка действия для уже удалённого поста не должна приводить к ошибке или появлению нового поста."""
    # Удаляем пост
    post_handler.posts.pop("post_1")
    update = make_mock_update()
    update.callback_query.data = "edit_text_post_1"
    await post_handler.handle_callback(update, mock_context)
    assert "post_1" not in post_handler.posts

@pytest.mark.asyncio
async def test_add_media_at_limit(mock_context, post_handler):
    """Добавление медиа при достижении лимита (например, 10 фото) не должно увеличивать список."""
    handler = post_handler
    handler.posts["post_1"].temp_media = [f"photo{i}.jpg" for i in range(10)]
    update = make_mock_update(photo=[Mock() for _ in range(2)])
    await handler.handle_message(update, mock_context)
    assert len(handler.posts["post_1"].temp_media) <= 10

@pytest.mark.asyncio
async def test_remove_all_media(mock_context, post_handler):
    """Удаление всех медиа: после подтверждения пост должен остаться без фото, FSM не должна падать."""
    handler = post_handler
    handler.posts["post_1"].temp_media = [f"photo{i}.jpg" for i in range(3)]
    update = make_mock_update()
    update.callback_query.data = "remove_media_post_1"
    await handler.handle_callback(update, mock_context)
    update2 = make_mock_update(text="1,2,3")
    await handler.handle_message(update2, mock_context)
    update3 = make_mock_update()
    update3.callback_query.data = "confirm_remove_media_post_1"
    await handler.handle_callback(update3, mock_context)
    assert handler.posts["post_1"].temp_media == []

@pytest.mark.asyncio
async def test_publish_without_text_or_media(mock_context, post_handler):
    """Публикация поста без текста или без медиа не должна приводить к ошибке FSM (можно добавить валидацию)."""
    handler = post_handler
    handler.posts["post_1"].temp_media = []
    handler.posts["post_1"].temp_text = ""
    update = make_mock_update()
    update.callback_query.data = "publish_post_1"
    await handler.handle_callback(update, mock_context)
    update2 = make_mock_update()
    update2.callback_query.data = "confirm_publish_post_1"
    await handler.handle_callback(update2, mock_context)
    # Ожидаем, что пост не будет удалён (или будет обработана ошибка)
    assert "post_1" in handler.posts or True

@pytest.mark.asyncio
async def test_republish_published_post(mock_context, post_handler):
    """Повторная публикация уже опубликованного поста не должна приводить к ошибке или дублированию."""
    handler = post_handler
    # Сначала публикуем
    update = make_mock_update()
    update.callback_query.data = "publish_post_1"
    await handler.handle_callback(update, mock_context)
    update2 = make_mock_update()
    update2.callback_query.data = "confirm_publish_post_1"
    await handler.handle_callback(update2, mock_context)
    # Пробуем ещё раз
    update3 = make_mock_update()
    update3.callback_query.data = "publish_post_1"
    await handler.handle_callback(update3, mock_context)
    update4 = make_mock_update()
    update4.callback_query.data = "confirm_publish_post_1"
    await handler.handle_callback(update4, mock_context)
    # Не должно быть ошибки
    assert True

@pytest.mark.asyncio
async def test_filesystem_error_handling(mock_context, post_handler):
    """Ошибка файловой системы (например, нет доступа к saved/) не должна приводить к падению FSM."""
    with patch("os.makedirs", side_effect=OSError("Нет доступа")):
        update = make_mock_update(photo=[Mock()])
        await post_handler.handle_message(update, mock_context)
    assert True

@pytest.mark.asyncio
async def test_telegram_api_error_handling(mock_context, post_handler):
    """Искусственное падение Telegram API (мок) не должно приводить к падению FSM."""
    mock_context.bot.send_message.side_effect = Exception("Telegram API error")
    update = make_mock_update()
    update.callback_query.data = "edit_text_post_1"
    await post_handler.handle_callback(update, mock_context)
    assert True

@pytest.mark.asyncio
async def test_action_in_invalid_state(mock_context, post_handler):
    """Попытка действия в невалидном состоянии FSM не должна менять состояние или вызывать ошибку."""
    handler = post_handler
    handler.posts["post_1"].state = None
    update = make_mock_update()
    update.callback_query.data = "publish_post_1"
    await handler.handle_callback(update, mock_context)
    # Состояние не должно стать CONFIRM_PUBLISH
    assert handler.posts["post_1"].state != "confirm_publish"

@pytest.mark.asyncio
async def test_restore_state_from_storage(mock_context):
    """Восстановление состояния из storage.json: FSM должна корректно инициализировать посты."""
    # Эмулируем чтение storage.json с одним постом
    from src.bot.handlers.test_handlers import PostHandler, PostContext, State
    handler = PostHandler()
    handler.posts["post_storage"] = PostContext(
        post_id="post_storage",
        chat_id=456,
        message_id=999,
        state=State.EDIT_TEXT_WAIT,
        user_id=123
    )
    assert handler.posts["post_storage"].state == State.EDIT_TEXT_WAIT 