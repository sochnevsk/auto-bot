import os
import re
import asyncio
import logging
from telegram import Bot, InputMediaPhoto, InlineKeyboardMarkup, InlineKeyboardButton, Update, PhotoSize
from telegram.ext import (
    Application, CallbackQueryHandler, ConversationHandler, MessageHandler, CommandHandler, ContextTypes, filters
)
from telegram.error import TelegramError
import time
from telegram.constants import ParseMode
import functools
import json
import sys

# === Параметры ===
MODERATOR_IDS = [179112258, 700270343, 7583480927, 244305655]
MODERATOR_GROUP_ID = -1002697639369  # ID вашей группы для модерации
BOT_TOKEN = '7589930248:AAGpkpuUofGAYomr1A1Q9XQLug6_CWbV1XU'
OPEN_CHANNEL_ID = -1002664287229
CLOSED_CHANNEL_ID = -1002482158935
WATCH_FOLDER = 'saved'
MAX_MEDIA_PER_ALBUM = 10
STATUS_FILE = os.path.join(WATCH_FOLDER, 'moderation_status.txt')
CONTACT_SIGNATURE = "\n\nНаш контакт: @Anastasiya_Sochneva"
MAX_CAPTION_LENGTH = 1024
MAX_TEXT_LENGTH = 4096

# === Логирование ===
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ptb_bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

# === Состояния FSM ===
STATE_IDLE = 'idle'
STATE_EDIT_TEXT = 'edit_text'
STATE_EDIT_PHOTO = 'edit_photo'
STATE_CHOOSE_EDIT = 'choose_edit'

# === Глобальные переменные ===
processed_posts = set()
moderator_context = {}
media_group_temp = {}  # {user_id: {media_group_id: [photo, ...]}}
media_group_tasks = {}  # {user_id: {media_group_id: asyncio.Task}}
MEDIA_GROUP_TIMEOUT = 9.0
# Для групповой модерации:
processed_group_posts = set()  # set of message_ids
# === Для блокировки редактирования ===
edit_locks = {}  # message_id: user_id

# === Глобальный логгер callback-запросов ===
async def log_all_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Логирует все callback-запросы для отладки.
    """
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    print(f"[GLOBAL LOG] CallbackQuery: data={data}, user_id={user_id}")
    logging.info(f"[GLOBAL LOG] CallbackQuery: data={data}, user_id={user_id}")

# === Вспомогательные функции ===
def mark_post(post_folder, value):
    """
    Помечает пост определённым статусом в STATUS_FILE.
    Используется для отслеживания, был ли пост отправлен или обработан.
    """
    if not os.path.exists(STATUS_FILE):
        with open(STATUS_FILE, 'w', encoding='utf-8') as f:
            pass
    status = {}
    with open(STATUS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) == 2:
                status[parts[0]] = parts[1]
    status[os.path.basename(post_folder)] = value
    with open(STATUS_FILE, 'w', encoding='utf-8') as f:
        for k, v in status.items():
            f.write(f'{k}|{v}\n')

def is_sent(post_folder):
    """
    Проверяет, был ли пост уже отправлен (по STATUS_FILE).
    """
    if not os.path.exists(STATUS_FILE):
        return False
    with open(STATUS_FILE, 'r', encoding='utf-8') as f:
        for line in f:
            parts = line.strip().split('|')
            if len(parts) == 2 and parts[0] == os.path.basename(post_folder) and parts[1] == 'sent':
                return True
    return False

def is_sent_file(post_folder):
    """
    Проверяет наличие файла sent.txt в папке поста.
    """
    return os.path.exists(os.path.join(post_folder, 'sent.txt'))

def create_inline_keyboard(message_id=None):
    """
    Создаёт inline-клавиатуру для управления постом (отправить, редактировать, отклонить).
    """
    # message_id — id исходного сообщения с постом
    if message_id is not None:
        keyboard = [[
            InlineKeyboardButton('Отправить', callback_data=f'send_to_channel:{message_id}'),
            InlineKeyboardButton('Редактировать', callback_data=f'edit_post:{message_id}'),
            InlineKeyboardButton('Отклонить', callback_data=f'reject_post:{message_id}')
        ]]
        logging.info(f"[BUTTONS] Создана inline-клавиатура с message_id={message_id}")
    else:
        keyboard = [[
            InlineKeyboardButton('Отправить', callback_data='send_to_channel'),
            InlineKeyboardButton('Редактировать', callback_data='edit_post'),
            InlineKeyboardButton('Отклонить', callback_data='reject_post')
        ]]
        logging.info(f"[BUTTONS] Создана inline-клавиатура без message_id")
    return InlineKeyboardMarkup(keyboard)

def create_save_keyboard():
    """
    Клавиатура с одной кнопкой "Сохранить" для подтверждения редактирования.
    """
    keyboard = [[InlineKeyboardButton('Сохранить', callback_data='save_edited_post')]]
    return InlineKeyboardMarkup(keyboard)

def create_edit_choice_keyboard(control_message_id):
    """
    Клавиатура для выбора типа редактирования (текст или фото).
    """
    keyboard = [[
        InlineKeyboardButton('Править текст', callback_data=f'edit_text:{control_message_id}'),
        InlineKeyboardButton('Править фото', callback_data=f'edit_photo:{control_message_id}')
    ]]
    return InlineKeyboardMarkup(keyboard)

def create_confirm_keyboard(message_id=None):
    """
    Клавиатура для подтверждения публикации в открытый канал.
    """
    keyboard = [[
        InlineKeyboardButton('✅ Отправить в открытый канал', callback_data=f'confirm_open:{message_id}'),
        InlineKeyboardButton('❌ Не отправлять', callback_data=f'cancel_open:{message_id}')
    ], [
        InlineKeyboardButton('✏️ Редактировать текст', callback_data=f'edit_open_text:{message_id}')
    ]]
    return InlineKeyboardMarkup(keyboard)

def get_posts():
    """
    Возвращает список путей к постам, которые готовы к модерации (есть ready.txt, нет moderated.txt и sent.txt).
    """
    posts = []
    for d in os.listdir(WATCH_FOLDER):
        post_path = os.path.join(WATCH_FOLDER, d)
        if os.path.isdir(post_path) and not is_sent(post_path) and not is_sent_file(post_path):
            if os.path.exists(os.path.join(post_path, 'ready.txt')) and not os.path.exists(os.path.join(post_path, 'moderated.txt')):
                posts.append(post_path)
    posts.sort(key=lambda x: os.path.getctime(x))
    return posts

async def safe_send(func, *args, retries=10, delay=10, **kwargs):
    """
    Асинхронно выполняет функцию с повторными попытками при ошибках Telegram.
    """
    for attempt in range(retries):
        try:
            result = await func(*args, **kwargs)
            if result is not None:
                return result  # Если хотя бы одна попытка успешна — не повторяем!
        except TelegramError as e:
            logging.warning(f"Ошибка отправки ({attempt+1}/{retries}): {e}")
            await asyncio.sleep(delay)
    logging.error(f"Не удалось выполнить {func.__name__} после {retries} попыток.")
    return None

def truncate_caption(text, max_bytes=1024):
    """
    Обрезает подпись для медиа до ограничения Telegram (1024 байта).
    """
    encoded = text.encode('utf-8')
    if len(encoded) <= max_bytes:
        return text
    truncated = encoded[:max_bytes]
    return truncated.decode('utf-8', errors='ignore')

def truncate_text(text, max_chars=4096):
    """
    Обрезает текст до максимальной длины Telegram (4096 символов).
    """
    if len(text) <= max_chars:
        return text
    return text[:max_chars]

async def send_media_with_text(chat_id, media_files, text, bot, log_channel_name=None, post_path=None, channel_type=None):
    """
    Отправляет альбом или одиночное фото с текстом в указанный канал.
    Обеспечивает защиту от повторной отправки, создание lock-файлов и обработку ошибок.
    """
    media_group_id_path = None
    if post_path and chat_id:
        media_group_id_path = os.path.join(post_path, f"media_group_id_{chat_id}.txt")
    album = []
    caption = truncate_caption(text, MAX_CAPTION_LENGTH)
    if len(caption.encode('utf-8')) < len(text.encode('utf-8')):
        logging.warning(f"Подпись к альбому обрезана до 1024 байт.")
    for idx, media in enumerate(media_files[:MAX_MEDIA_PER_ALBUM]):
        with open(media, 'rb') as media_file:
            album.append(
                InputMediaPhoto(
                    media_file,
                    caption=(caption if idx == 0 else "")
                )
            )
    lock_path = os.path.join(post_path, 'sending.lock') if post_path else None
    sent_path = os.path.join(post_path, 'sent.txt') if post_path else None
    logging.info(f"[SEND_MEDIA] chat_id={chat_id}, post_path={post_path}, sent_path={sent_path}, lock_path={lock_path}, media_count={len(album)}")
    if channel_type == 'open':
        sent_flag = os.path.join(post_path, 'send_open.txt')
    elif channel_type == 'close':
        sent_flag = os.path.join(post_path, 'send_close.txt')
    else:
        sent_flag = None
    if sent_flag and os.path.exists(sent_flag):
        logging.info(f"[SEND_MEDIA] SKIP: Альбом уже отправлен в канал {channel_type}: {post_path}")
        return 'already_sent'
    if lock_path and os.path.exists(lock_path):
        logging.info(f"[SEND_MEDIA] LOCK: Альбом уже обрабатывается: {post_path}")
        return 'locked'
    if lock_path:
        with open(lock_path, 'w') as f:
            f.write('lock')
        logging.info(f"[SEND_MEDIA] LOCK-файл создан: {lock_path}")
    try:
        max_attempts = 3
        for attempt in range(max_attempts):
            try:
                logging.info(f"[SEND_MEDIA] Попытка {attempt+1}/{max_attempts} отправки альбома...")
                if len(album) > 1:
                    result = await bot.send_media_group(chat_id=chat_id, media=album)
                    logging.info(f"[SEND_MEDIA] send_media_group result: {result}")
                    if result and hasattr(result[0], 'media_group_id'):
                        media_group_id = result[0].media_group_id
                        if media_group_id_path:
                            with open(media_group_id_path, 'w') as f:
                                f.write(str(media_group_id))
                        logging.info(f"[SEND_MEDIA] Сохранён media_group_id: {media_group_id}")
                    if sent_path:
                        with open(sent_path, 'w') as f:
                            f.write('ok')
                        logging.info(f"[SEND_MEDIA] Создан sent.txt: {sent_path}")
                    log_msg = f"Сообщение отправлено в канал {chat_id} с медиафайлами: {len(album)} шт."
                    if log_channel_name:
                        log_msg = f"[{log_channel_name}] {log_msg}"
                    print(log_msg)
                    logging.info(log_msg)
                    if sent_flag:
                        with open(sent_flag, 'w') as f:
                            f.write('ok')
                        logging.info(f"[SEND_MEDIA] Создан флаг-файл: {sent_flag}")
                    return 'sent'
                elif len(album) == 1:
                    result = await bot.send_photo(chat_id=chat_id, photo=album[0].media, caption=caption)
                    logging.info(f"[SEND_MEDIA] send_photo result: {result}")
                    if sent_path:
                        with open(sent_path, 'w') as f:
                            f.write('ok')
                        logging.info(f"[SEND_MEDIA] Создан sent.txt: {sent_path}")
                    log_msg = f"Сообщение отправлено в канал {chat_id} с медиафайлами: 1 шт."
                    if log_channel_name:
                        log_msg = f"[{log_channel_name}] {log_msg}"
                    print(log_msg)
                    logging.info(log_msg)
                    if sent_flag:
                        with open(sent_flag, 'w') as f:
                            f.write('ok')
                        logging.info(f"[SEND_MEDIA] Создан флаг-файл: {sent_flag}")
                    return 'sent'
                else:
                    logging.warning(f"[SEND_MEDIA] Нет медиа для отправки!")
                    return 'no_media'
            except Exception as e:
                logging.warning(f"[SEND_MEDIA] Ошибка отправки ({attempt+1}/{max_attempts}): {e}")
                await asyncio.sleep(5)
                if media_group_id_path and os.path.exists(media_group_id_path):
                    media_group_id = open(media_group_id_path).read().strip()
                    try:
                        updates = await bot.get_chat_history(chat_id, limit=10)
                        for msg in updates:
                            if hasattr(msg, 'media_group_id') and str(msg.media_group_id) == media_group_id:
                                if sent_path:
                                    with open(sent_path, 'w') as f:
                                        f.write('ok')
                                    logging.info(f"[SEND_MEDIA] Создан sent.txt по дубликату: {sent_path}")
                                logging.info(f"[SEND_MEDIA] DUPLICATE: Альбом уже есть в канале {chat_id}, media_group_id={media_group_id}")
                                return 'sent_duplicate'
                    except Exception as e2:
                        logging.warning(f"[SEND_MEDIA] Ошибка проверки наличия альбома в канале: {e2}")
                continue
        if error_path:
            with open(error_path, 'w') as f:
                f.write('error')
            logging.error(f"[SEND_MEDIA] Создан error.txt: {error_path}")
        logging.error(f"[SEND_MEDIA] FAIL: Не удалось отправить альбом после {max_attempts} попыток: {post_path}")
        return 'error'
    finally:
        if lock_path and os.path.exists(lock_path):
            os.remove(lock_path)
            logging.info(f"[SEND_MEDIA] LOCK-файл удалён: {lock_path}")

async def process_post(post_path, bot):
    """
    Основная функция для отправки поста на модерацию
    """
    # Проверяем наличие файлов, указывающих на то, что пост уже отправлен
    media_group_id_path = os.path.join(post_path, 'mod_media_group_id.txt')
    message_id_path = os.path.join(post_path, 'mod_message_id.txt')
    moderated_path = os.path.join(post_path, 'moderated.txt')
    sent_path = os.path.join(post_path, 'sent.txt')

    # Проверяем все возможные флаги отправки
    if (os.path.exists(media_group_id_path) and os.path.exists(message_id_path)) or \
       os.path.exists(moderated_path) or \
       os.path.exists(sent_path):
        logging.info(f"[MODERATION] Пост уже был отправлен на модерацию ранее, пропускаем: {post_path}")
        return

    # Проверяем наличие lock-файла
    lock_path = os.path.join(post_path, 'sending.lock')
    if os.path.exists(lock_path):
        logging.info(f"[MODERATION] Пост уже обрабатывается (есть lock-файл): {post_path}")
        return

    try:
        # Создаем lock-файл перед отправкой
        with open(lock_path, 'w') as f:
            f.write('lock')

        message_text = ""
        message_file = os.path.join(post_path, 'text_close.txt')
        if not os.path.exists(message_file):
            message_file = os.path.join(post_path, 'text.txt')
        if os.path.exists(message_file):
            with open(message_file, 'r', encoding='utf-8') as f:
                message_text = f.read()

        # Оригинальный текст для закрытого канала
        original_file = os.path.join(post_path, 'text_close.txt')
        if not os.path.exists(original_file):
            original_file = os.path.join(post_path, 'text.txt')
        if os.path.exists(original_file):
            with open(original_file, 'r', encoding='utf-8') as f:
                original_text = f.read()
        else:
            original_text = message_text

        media_files = []
        for f in os.listdir(post_path):
            if f.startswith('photo') and (f.endswith('.jpg') or f.endswith('.jpeg') or f.endswith('.png')):
                media_files.append(os.path.join(post_path, f))

        post_message_id = None
        if media_files:
            sent_msgs = await safe_send(
                bot.send_media_group,
                chat_id=MODERATOR_GROUP_ID,
                media=[InputMediaPhoto(open(m, 'rb'), caption=(message_text if i == 0 else "")) 
                      for i, m in enumerate(media_files[:MAX_MEDIA_PER_ALBUM])]
            )
            
            if sent_msgs:
                post_message_id = sent_msgs[0].message_id
                # Сохраняем информацию об отправке
                with open(message_id_path, 'w') as f:
                    f.write(str(post_message_id))
                if hasattr(sent_msgs[0], 'media_group_id'):
                    with open(media_group_id_path, 'w') as f:
                        f.write(str(sent_msgs[0].media_group_id))
                
                # Создаем moderated.txt
                with open(moderated_path, 'w') as f:
                    f.write('ok')
                
                logging.info(f"[MODERATION] Пост успешно отправлен на модерацию: {post_path}")
            else:
                logging.error(f"[MODERATION] Не удалось отправить пост: {post_path}")
                return
        else:
            # Обработка текстового поста
            msg = await safe_send(
                bot.send_message,
                chat_id=MODERATOR_GROUP_ID,
                text=truncate_text(message_text),
                parse_mode="Markdown"
            )
            if msg:
                post_message_id = msg.message_id
                with open(message_id_path, 'w') as f:
                    f.write(str(post_message_id))
                with open(moderated_path, 'w') as f:
                    f.write('ok')
                logging.info(f"[MODERATION] Текстовый пост успешно отправлен на модерацию: {post_path}")
            else:
                logging.error(f"[MODERATION] Не удалось отправить текстовый пост: {post_path}")
                return

        # Создаем сообщение с кнопками управления
        if post_message_id:
            await asyncio.sleep(1)  # Пауза для Telegram после отправки
            control_msg = await safe_send(
                bot.send_message,
                chat_id=MODERATOR_GROUP_ID,
                text="Управление этим постом:",
                reply_markup=None,
                reply_to_message_id=post_message_id
            )
            
            if control_msg:
                keyboard = create_inline_keyboard(message_id=control_msg.message_id)
                await asyncio.sleep(0.7)  # Пауза перед обновлением клавиатуры
                await safe_send(control_msg.edit_reply_markup, reply_markup=keyboard)
                
                # Сохраняем данные в контекст модерации
                moderator_context[control_msg.message_id] = {
                    "text": message_text,
                    "original_text": original_text,
                    "open_text": message_text,
                    "media": media_files,
                    "post_path": post_path,
                    "post_message_id": post_message_id,
                    "control_message_id": control_msg.message_id,
                    "was_edited": False
                }
                logging.info(f"[DEBUG] Добавлен post_data в moderator_context[{control_msg.message_id}]")
                processed_posts.add(post_path)
            else:
                logging.error(f"[MODERATION] Не удалось создать сообщение с кнопками: {post_path}")

    except Exception as e:
        logging.error(f"[MODERATION] Ошибка при отправке поста: {e}")
    finally:
        # Удаляем lock-файл в любом случае
        if os.path.exists(lock_path):
            os.remove(lock_path)

async def main_loop(bot):
    """
    Главный цикл: ищет новые посты для модерации и отправляет их.
    """
    while True:
        posts = get_posts()
        for post_path in posts:
            if post_path not in processed_posts:
                await process_post(post_path, bot)
                processed_posts.add(post_path)
        await asyncio.sleep(10)

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обработчик команды /start. Приветствует пользователя и сообщает его ID.
    """
    user_id = update.message.from_user.id
    await update.message.reply_text(f"Бот запущен. Ваш ID: {user_id}.")
    logging.info(f"Команда /start от пользователя {user_id}")

def is_stale_lock(lock_path, sent_path, max_age_sec=120):
    """
    Проверяет, устарел ли lock-файл (например, если отправка зависла).
    """
    if os.path.exists(lock_path) and not os.path.exists(sent_path):
        mtime = os.path.getmtime(lock_path)
        if time.time() - mtime > max_age_sec:
            return True
    return False

async def global_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Глобальный обработчик callback-запросов от кнопок модерации.
    Реализует логику публикации, отклонения, редактирования поста и т.д.
    """
    query = update.callback_query
    data = query.data
    user_id = query.from_user.id
    message_id = query.message.message_id  # Это теперь message_id сообщения с кнопками
    chat_id = query.message.chat_id
    logging.info(f"[BUTTONS] Получен callback: data={data}, user_id={user_id}, message_id={message_id}")

    # Парсим post_message_id из callback_data
    orig_message_id = None
    if ':' in data:
        action, mid = data.split(':', 1)
        try:
            orig_message_id = int(mid)
        except Exception:
            orig_message_id = None
        data = action
    else:
        orig_message_id = None

    lookup_id = orig_message_id if orig_message_id is not None else message_id

    # --- ДОБАВЛЯЮ ЗАЩИТУ ОТ ПОВТОРНОГО НАЖАТИЯ ---
    post_data = moderator_context.get(lookup_id)
    if not post_data:
        await query.answer("Пост не найден в контексте.", show_alert=True)
        return
    post_path = post_data["post_path"]
    lock_path = os.path.join(post_path, 'sending.lock')
    if os.path.exists(os.path.join(post_path, 'send_open.txt')) and os.path.exists(os.path.join(post_path, 'send_close.txt')):
        await query.answer("Пост уже был отправлен.", show_alert=True)
        return
    if os.path.exists(lock_path):
        await query.answer("Пост уже обрабатывается.", show_alert=True)
        return

    logging.error(f"[DEBUG] CALLBACK: user_id={user_id}, message_id={message_id}, orig_message_id={orig_message_id}, lookup_id={lookup_id}, callback_data={data}, state={context.user_data.get('state')}, post_data_keys={list(post_data.keys()) if post_data else None}")
    logging.error(f"[DEBUG] moderator_context: {moderator_context}")

    # Теперь работаем только по message_id сообщения с кнопками
    lookup_id = orig_message_id if orig_message_id is not None else message_id
    post_data = moderator_context.get(lookup_id)
    if not post_data:
        await query.answer("Ошибка: данные для этого поста не найдены.", show_alert=True)
        context.user_data['state'] = STATE_IDLE
        return
    # Проверяем, был ли пост уже обработан
    if lookup_id in processed_group_posts:
        await query.answer("Пост уже обработан другим модератором.", show_alert=True)
        return
    if data == "send_to_channel":
        logging.info(f"[BUTTONS] Нажата кнопка 'Отправить' для message_id={message_id}")
        lock_path = os.path.join(post_data["post_path"], 'sending.lock')
        sent_path = os.path.join(post_data["post_path"], 'sent.txt')
        # Анти-залипание lock-файла
        if is_stale_lock(lock_path, sent_path):
            logging.warning(f"[LOCK] Удаляю устаревший lock-файл: {lock_path}")
            try:
                os.remove(lock_path)
                logging.info(f"[LOCK] Удалён устаревший lock-файл: {lock_path}")
                await asyncio.sleep(0.5)
            except Exception as e:
                logging.error(f"[LOCK] Не удалось удалить устаревший lock-файл: {e}")
        # АТОМАРНАЯ ФАЙЛОВАЯ БЛОКИРОВКА
        if not acquire_lock(post_data["post_path"]):
            logging.warning(f"[LOCK] Пост уже обрабатывается другим процессом: {post_data['post_path']}")
            await query.answer("Пост уже обрабатывается.", show_alert=True)
            return
        try:
            logging.info(f"[MODERATION] Начало отправки поста: lookup_id={lookup_id}, post_path={post_data['post_path']}, media={post_data['media']}, was_edited={post_data.get('was_edited')}")
            if is_sent_file(post_data["post_path"]) or is_sent(post_data["post_path"]):
                logging.warning(f"[SKIP] Повторная попытка отправки поста (уже отправлен): {post_data['post_path']}")
                await query.answer("Пост уже был отправлен.", show_alert=True)
                return
            send_ok = True
            media_success = True
            try:
                logging.info(f"[MODERATION] Тексты для каналов: open_channel_text={post_data.get('open_text')}, close_channel_text={post_data.get('original_text')}")
                if post_data.get('was_edited'):
                    close_channel_text = ensure_source_signature(post_data["text"], post_data["post_path"])
                    open_channel_text = ensure_contact_signature(clean_text_for_open(post_data["text"]))
                else:
                    close_channel_text = ensure_source_signature(post_data["original_text"], post_data["post_path"])
                    open_channel_text = ensure_contact_signature(clean_text_for_open(post_data["open_text"]))
                logging.info(f"[SEND] Публикация поста: post_path={post_data['post_path']}, media={post_data['media']}")
                logging.info(f"[SEND] Отправка альбома в открытый канал...")
                res1 = await send_media_with_text(OPEN_CHANNEL_ID, post_data["media"], open_channel_text, context.bot, "ОТКРЫТЫЙ КАНАЛ", post_data["post_path"])
                logging.info(f"[SEND] Результат отправки в открытый канал: {res1}")
                await asyncio.sleep(1.5)  # Увеличенная задержка между каналами
                logging.info(f"[SEND] Отправка альбома в закрытый канал...")
                res2 = await send_media_with_text(CLOSED_CHANNEL_ID, post_data["media"], close_channel_text, context.bot, "ЗАКРЫТЫЙ КАНАЛ", post_data["post_path"])
                logging.info(f"[SEND] Результат отправки в закрытый канал: {res2}")
                if res1 in ('sent', 'sent_duplicate') and res2 in ('sent', 'sent_duplicate'):
                    logging.info(f"[SEND] Создаю sent.txt и обновляю статус...")
                    set_sent_file(post_data["post_path"])
                    # --- Удаляем moderated.txt ---
                    moderated_path = os.path.join(post_data["post_path"], 'moderated.txt')
                    if os.path.exists(moderated_path):
                        os.remove(moderated_path)
                    await query.message.delete()  # Удаляем сообщение с кнопками
                    logging.info(f"[SEND] Сообщение с кнопками удалено.")
                    await context.bot.send_message(chat_id=chat_id, text=truncate_text(f"Пост обработан модератором @{query.from_user.username}"))
                    mark_post(post_data["post_path"], 'sent')
                    logging.info(f"[SUCCESS] Пост успешно отправлен и помечен как sent: {post_data['post_path']}")
                    moderator_context.pop(lookup_id, None)
                    context.user_data['edit_message_id'] = None  # ОЧИСТКА edit_message_id
                    logging.info(f"[DEBUG] Удалён post_data из moderator_context[{lookup_id}]")
                    context.user_data['state'] = STATE_IDLE
                    if lookup_id in edit_locks:
                        del edit_locks[lookup_id]
                    processed_group_posts.add(lookup_id)  # Только после успеха!
                    logging.info(f"[SUCCESS] lookup_id={lookup_id} добавлен в processed_group_posts")
                else:
                    logging.warning(f"[SEND] Не удалось отправить пост в оба канала, sent.txt НЕ создаётся! res1={res1}, res2={res2}")
                    # Если оба результата locked — удаляем lock-файл и пробуем ещё раз
                    if res1 == 'locked' and res2 == 'locked':
                        lock_path = os.path.join(post_data["post_path"], 'sending.lock')
                        if os.path.exists(lock_path):
                            os.remove(lock_path)
                            logging.info(f"[LOCK] Удалён lock-файл после двойного locked: {lock_path}")
                            await asyncio.sleep(1.0)  # Увеличенная задержка перед повторной попыткой
                        logging.info("[SEND] Повторная попытка отправки после удаления lock-файла...")
                        res1 = await send_media_with_text(OPEN_CHANNEL_ID, post_data["media"], open_channel_text, context.bot, "ОТКРЫТЫЙ КАНАЛ", post_data["post_path"])
                        logging.info(f"[SEND] Результат повторной отправки в открытый канал: {res1}")
                        res2 = await send_media_with_text(CLOSED_CHANNEL_ID, post_data["media"], close_channel_text, context.bot, "ЗАКРЫТЫЙ КАНАЛ", post_data["post_path"])
                        logging.info(f"[SEND] Результат повторной отправки в закрытый канал: {res2}")
                        if res1 in ('sent', 'sent_duplicate') and res2 in ('sent', 'sent_duplicate'):
                            logging.info(f"[SEND] Создаю sent.txt и обновляю статус...")
                            set_sent_file(post_data["post_path"])
                            # --- Удаляем moderated.txt ---
                            moderated_path = os.path.join(post_data["post_path"], 'moderated.txt')
                            if os.path.exists(moderated_path):
                                os.remove(moderated_path)
                            await query.message.delete()  # Удаляем сообщение с кнопками
                            logging.info(f"[SEND] Сообщение с кнопками удалено.")
                            await context.bot.send_message(chat_id=chat_id, text=truncate_text(f"Пост обработан модератором @{query.from_user.username}"))
                            mark_post(post_data["post_path"], 'sent')
                            logging.info(f"[SUCCESS] Пост успешно отправлен и помечен как sent: {post_data['post_path']}")
                            moderator_context.pop(lookup_id, None)
                            context.user_data['edit_message_id'] = None  # ОЧИСТКА edit_message_id
                            logging.info(f"[DEBUG] Удалён post_data из moderator_context[{lookup_id}]")
                            context.user_data['state'] = STATE_IDLE
                            if lookup_id in edit_locks:
                                del edit_locks[lookup_id]
                            processed_group_posts.add(lookup_id)  # Только после успеха!
                            logging.info(f"[SUCCESS] lookup_id={lookup_id} добавлен в processed_group_posts")
                            return
                    # Если и повторная попытка не удалась — только тогда показываем ошибку
                    await query.answer("Ошибка отправки. Попробуйте ещё раз.", show_alert=True)
                    return
            except Exception as e:
                logging.error(f"[SEND ERROR] Ошибка отправки поста: {e}", exc_info=True)
                send_ok = False
            if not send_ok or not media_success:
                logging.warning(f"[RETRY] Отправка не удалась: {post_data['post_path']}")
                await query.answer("Ошибка отправки. Попробуйте ещё раз.", show_alert=True)
                return
        finally:
            release_lock(post_data["post_path"])
            logging.info(f"[LOCK] release_lock вызван для {post_data['post_path']}")
    elif data == "reject_post":
        logging.info(f"[BUTTONS] Нажата кнопка 'Отклонить' для message_id={message_id}")
        processed_group_posts.add(lookup_id)
        await query.message.delete()  # Удаляем сообщение с кнопками
        logging.info(f"[BUTTONS] Сообщение с кнопками удалено (отклонение)")
        await context.bot.send_message(chat_id=chat_id, text=truncate_text(f"Пост отклонён модератором @{query.from_user.username}."))
        moderator_context.pop(lookup_id, None)
        logging.info(f"[DEBUG] Удалён post_data из moderator_context[{lookup_id}]")
        context.user_data['state'] = STATE_IDLE
        if lookup_id in edit_locks:
            del edit_locks[lookup_id]
    elif data == "edit_post":
        logging.info(f"[BUTTONS] Нажата кнопка 'Редактировать' для message_id={message_id}")
        if lookup_id in edit_locks and edit_locks[lookup_id] != user_id:
            current_editor_id = edit_locks.get(lookup_id)
            current_editor_username = None
            for ctx in moderator_context.values():
                if ctx.get('control_message_id') == lookup_id and 'editor_username' in ctx:
                    current_editor_username = ctx['editor_username']
                    break
            msg = "Сейчас редактирует другой модератор."
            if current_editor_username:
                msg = f"Сейчас редактирует модератор @{current_editor_username}."
            await query.answer(msg, show_alert=True)
            return
        edit_locks[lookup_id] = user_id
        post_data['editor_username'] = query.from_user.username
        moderator_context[lookup_id] = post_data
        logging.info(f"[EDIT] Начато редактирование: message_id={lookup_id}, user_id={user_id}")
        context.user_data['state'] = STATE_CHOOSE_EDIT
        context.user_data['post_data'] = post_data
        context.user_data['edit_message_id'] = lookup_id
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Редактирование поста начато модератором @{query.from_user.username}"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text="Что вы хотите изменить?",
            reply_markup=create_edit_choice_keyboard(post_data['control_message_id'])
        )
    elif data == "edit_text":
        logging.info(f"[BUTTONS] Нажата кнопка 'Править текст' для message_id={message_id}")
        await query.message.delete()  # Удаляем сообщение с выбором типа редактирования
        logging.info(f"[BUTTONS] Сообщение с кнопками удалено (выбор типа редактирования)")
        if lookup_id in edit_locks and edit_locks[lookup_id] != user_id:
            current_editor_id = edit_locks.get(lookup_id)
            current_editor_username = None
            for ctx in moderator_context.values():
                if ctx.get('control_message_id') == lookup_id and 'editor_username' in ctx:
                    current_editor_username = ctx['editor_username']
                    break
            msg = "Сейчас редактирует другой модератор."
            if current_editor_username:
                msg = f"Сейчас редактирует модератор @{current_editor_username}."
            await query.answer(msg, show_alert=True)
            return
        edit_locks[lookup_id] = user_id
        post_data['editor_username'] = query.from_user.username
        moderator_context[lookup_id] = post_data
        logging.info(f"[EDIT] Начато редактирование текста: message_id={lookup_id}, user_id={user_id}")
        context.user_data['state'] = STATE_EDIT_TEXT
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Редактирование текста начато модератором @{query.from_user.username}"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text="Введите новый текст для поста:",
            reply_markup=None
        )
    elif data == "edit_photo":
        logging.info(f"[BUTTONS] Нажата кнопка 'Править фото' для message_id={message_id}")
        await query.message.delete()  # Удаляем сообщение с выбором типа редактирования
        logging.info(f"[BUTTONS] Сообщение с кнопками удалено (выбор типа редактирования)")
        if lookup_id in edit_locks and edit_locks[lookup_id] != user_id:
            current_editor_id = edit_locks.get(lookup_id)
            current_editor_username = None
            for ctx in moderator_context.values():
                if ctx.get('control_message_id') == lookup_id and 'editor_username' in ctx:
                    current_editor_username = ctx['editor_username']
                    break
            msg = "Сейчас редактирует другой модератор."
            if current_editor_username:
                msg = f"Сейчас редактирует модератор @{current_editor_username}."
            await query.answer(msg, show_alert=True)
            return
        edit_locks[lookup_id] = user_id
        post_data['editor_username'] = query.from_user.username
        moderator_context[lookup_id] = post_data
        logging.info(f"[EDIT] Начато редактирование фото: message_id={lookup_id}, user_id={user_id}")
        if user_id in media_group_temp:
            media_group_temp[user_id] = {}
        if user_id in media_group_tasks:
            for t in media_group_tasks[user_id].values():
                try:
                    t.cancel()
                except Exception as e:
                    print(f"[LOG] Ошибка при отмене таймера: {e}")
            media_group_tasks[user_id] = {}
        context.user_data['state'] = STATE_EDIT_PHOTO
        context.user_data['edit_message_id'] = lookup_id
        await context.bot.send_message(
            chat_id=chat_id,
            text=f"Редактирование фото начато модератором @{query.from_user.username}"
        )
        await context.bot.send_message(
            chat_id=chat_id,
            text="Отправьте новое фото (можно несколько). Старые фото будут заменены.",
            reply_markup=None
        )
    elif data == "confirm_open":
        logging.info(f"[BUTTONS] Нажата кнопка 'Отправить в открытый канал' для message_id={message_id}")
        open_channel_text = context.user_data.get('pending_open_text')
        close_channel_text = context.user_data.get('pending_close_text')
        media = context.user_data.get('pending_media')
        post_path = context.user_data.get('pending_post_path')
        lookup_id = context.user_data.get('pending_lookup_id')
        try:
            if media:
                await send_media_with_text(OPEN_CHANNEL_ID, media, open_channel_text, context.bot, log_channel_name="ОТКРЫТЫЙ КАНАЛ", post_path=post_path, channel_type='open')
                await send_media_with_text(CLOSED_CHANNEL_ID, media, close_channel_text, context.bot, log_channel_name="ЗАКРЫТЫЙ КАНАЛ", post_path=post_path, channel_type='close')
            else:
                await context.bot.send_message(chat_id=OPEN_CHANNEL_ID, text=truncate_text(open_channel_text), parse_mode="Markdown")
                await context.bot.send_message(chat_id=CLOSED_CHANNEL_ID, text=truncate_text(close_channel_text), parse_mode="Markdown")
            moderator_context.pop(lookup_id, None)
            context.user_data['state'] = STATE_IDLE
            processed_group_posts.add(lookup_id)
            if lookup_id in edit_locks:
                del edit_locks[lookup_id]
            await query.message.delete()
            await context.bot.send_message(chat_id=MODERATOR_GROUP_ID, text=truncate_text("Пост отправлен в оба канала по подтверждению модератора."))
        except TelegramError as e:
            logging.error(f"Ошибка при отправке по подтверждению: {e}", exc_info=True)
            await query.answer("Ошибка при отправке по подтверждению.", show_alert=True)
    elif data == "cancel_open":
        logging.info(f"[BUTTONS] Нажата кнопка 'Не отправлять' для message_id={message_id}")
        close_channel_text = context.user_data.get('pending_close_text')
        media = context.user_data.get('pending_media')
        post_path = context.user_data.get('pending_post_path')
        lookup_id = context.user_data.get('pending_lookup_id')
        try:
            if media:
                await send_media_with_text(CLOSED_CHANNEL_ID, media, close_channel_text, context.bot, log_channel_name="ЗАКРЫТЫЙ КАНАЛ", post_path=post_path, channel_type='close')
            else:
                await context.bot.send_message(chat_id=CLOSED_CHANNEL_ID, text=truncate_text(close_channel_text), parse_mode="Markdown")
            moderator_context.pop(lookup_id, None)
            context.user_data['state'] = STATE_IDLE
            processed_group_posts.add(lookup_id)
            if lookup_id in edit_locks:
                del edit_locks[lookup_id]
            await query.message.delete()
            await context.bot.send_message(chat_id=MODERATOR_GROUP_ID, text=truncate_text("Пост отправлен только в закрытый канал по решению модератора."))
        except TelegramError as e:
            logging.error(f"Ошибка при отправке по отказу: {e}", exc_info=True)
            await query.answer("Ошибка при отправке по отказу.", show_alert=True)
    elif data == "edit_open_text":
        logging.info(f"[BUTTONS] Нажата кнопка 'Редактировать текст для открытого канала' для message_id={message_id}")
        open_channel_text = context.user_data.get('pending_open_text')
        context.user_data['state'] = STATE_EDIT_TEXT
        context.user_data['edit_message_id'] = lookup_id
        context.user_data['edit_open_text_mode'] = True  # специальный режим
        await query.message.reply_text(
            f"Введите новый текст для открытого канала (сейчас будет предложен очищенный вариант):\n\n{escape_markdown(open_channel_text)}",
            reply_markup=None,
            parse_mode=None
        )
        await query.answer("Редактирование текста для открытого канала.", show_alert=True)
        return
    else:
        logging.info(f"[BUTTONS] Callback с неизвестным действием: data={data}, message_id={message_id}")
        await query.answer()

async def global_text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Глобальный обработчик текстовых сообщений (редактирование текста поста).
    """
    logging.info(f"[DEBUG] global_text_handler вызван: user_id={getattr(update.effective_user, 'id', None)}, chat_id={getattr(update.effective_chat, 'id', None)}, text={getattr(update.message, 'text', None)}, state={context.user_data.get('state')}, edit_message_id={context.user_data.get('edit_message_id')}")
    user_id = update.message.from_user.id
    state = context.user_data.get('state', STATE_IDLE)
    message_id = context.user_data.get('edit_message_id')
    post_data = moderator_context.get(message_id)
    logging.info(f"[DEBUG] post_data для редактирования текста: {post_data}")
    # --- Новый режим: редактирование очищенного текста для открытого канала ---
    if state == STATE_EDIT_TEXT and context.user_data.get('edit_open_text_mode'):
        new_text = update.message.text
        if new_text and new_text.strip():
            # Сохраняем новый текст для открытого канала и возвращаемся к подтверждению
            context.user_data['pending_open_text'] = new_text.strip()
            context.user_data['edit_open_text_mode'] = False
            context.user_data['state'] = STATE_IDLE
            await update.message.reply_text(
                f"Текст для открытого канала обновлён. Теперь вы можете снова подтвердить отправку.",
                reply_markup=create_confirm_keyboard(message_id)
            )
        else:
            await update.message.reply_text("Ошибка: введите непустой текст.")
        return
    # --- Обычный режим редактирования текста поста ---
    if state == STATE_EDIT_TEXT:
        if not message_id:
            await update.message.reply_text("Ошибка: не найдено сообщение с кнопками.")
            return
        if message_id not in edit_locks or edit_locks[message_id] != user_id:
            await update.message.reply_text("Сейчас редактирует другой модератор.")
            return
        new_text = update.message.text
        if new_text and new_text.strip():
            if not post_data:
                await update.message.reply_text("Ошибка: данные поста не найдены.")
                context.user_data['state'] = STATE_IDLE
                return
            post_data['text'] = new_text
            post_data['was_edited'] = True
            moderator_context[message_id] = post_data
            context.user_data['state'] = STATE_IDLE
            try:
                # Удаляем старое сообщение с кнопками
                await update.get_bot().delete_message(chat_id=MODERATOR_GROUP_ID, message_id=message_id)
                # 1. Отправляем новое сообщение без клавиатуры
                control_msg = await update.get_bot().send_message(
                    chat_id=MODERATOR_GROUP_ID,
                    text="Управление этим постом:",
                    reply_markup=None
                )
                # 2. Создаём клавиатуру с новым message_id
                keyboard = create_inline_keyboard(message_id=control_msg.message_id)
                # 3. Обновляем reply_markup
                await control_msg.edit_reply_markup(reply_markup=keyboard)
                # 4. Обновляем все ссылки
                post_data['control_message_id'] = control_msg.message_id
                moderator_context[control_msg.message_id] = post_data
                context.user_data['edit_message_id'] = control_msg.message_id  # ОБНОВЛЕНИЕ edit_message_id
                logging.info(f"[EDIT] Обновлён moderator_context и edit_message_id после редактирования текста: message_id={control_msg.message_id}")
                if message_id in edit_locks:
                    del edit_locks[message_id]
                edit_locks[control_msg.message_id] = user_id
                await update.get_bot().send_message(
                    chat_id=MODERATOR_GROUP_ID,
                    text=f"Текст обновлён модератором @{update.effective_user.username}"
                )
            except Exception as e:
                logging.error(f"Ошибка при восстановлении кнопок после редактирования текста: {e}")
        else:
            await update.message.reply_text("Ошибка: введите непустой текст.")
        return
    # --- Остальной код ---
    await update.message.reply_text("Ошибка: сейчас нельзя отправлять текст. Используйте кнопки.")

async def global_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Глобальный обработчик фото (редактирование фото поста).
    """
    user_id = update.message.from_user.id
    state = context.user_data.get('state', STATE_IDLE)
    message_id = context.user_data.get('edit_message_id')
    post_data = moderator_context.get(message_id)
    logging.info(f"[DEBUG] global_photo_handler: user_id={user_id}, state={state}, edit_message_id={message_id}, post_data={post_data}")
    if state == STATE_EDIT_PHOTO:
        # Если это альбом (media_group_id), не сбрасываем state сразу
        if update.message.media_group_id:
            await receive_edited_photo(update, context)
            # state будет сброшен в finish_media_group
        else:
            await receive_edited_photo(update, context)
            context.user_data['state'] = STATE_IDLE
    else:
        await update.message.reply_text("Ошибка: сейчас нельзя отправлять фото. Используйте кнопки.")

async def finish_media_group(user_id, media_group_id, post_data, context, update):
    """
    Завершает приём альбома новых фото при редактировании, сохраняет их и обновляет post_data.
    """
    album_photos = media_group_temp[user_id][media_group_id]
    new_media_files = []
    for i, photo in enumerate(album_photos):
        file = await photo.get_file()
        file_path = os.path.join(post_data["post_path"], f"edited_photo_{i}.jpg")
        await file.download_to_drive(file_path)
        new_media_files.append(file_path)
    message_id = context.user_data.get('edit_message_id')
    post_data["media"] = new_media_files
    moderator_context[message_id] = post_data
    logging.info(f"[EDIT] Получено новое фото (альбом): user_id={user_id}, ожидается user_id={edit_locks.get(message_id)}, message_id={message_id}")
    del media_group_temp[user_id][media_group_id]
    del media_group_tasks[user_id][media_group_id]
    if message_id not in edit_locks or edit_locks[message_id] != user_id:
        logging.warning(f"[EDIT] Попытка редактирования фото (альбом) другим модератором: user_id={user_id}, ожидается user_id={edit_locks.get(message_id)}, message_id={message_id}")
        await context.bot.send_message(
            chat_id=user_id,
            text="Сейчас редактирует другой модератор.",
            reply_markup=None
        )
        return
    try:
        # Удаляем старое сообщение с кнопками
        await context.bot.delete_message(chat_id=MODERATOR_GROUP_ID, message_id=message_id)
        # 1. Отправляем новое сообщение без клавиатуры
        control_msg = await context.bot.send_message(
            chat_id=MODERATOR_GROUP_ID,
            text="Управление этим постом:",
            reply_markup=None
        )
        # 2. Создаём клавиатуру с новым message_id
        keyboard = create_inline_keyboard(message_id=control_msg.message_id)
        # 3. Обновляем reply_markup
        await control_msg.edit_reply_markup(reply_markup=keyboard)
        # 4. Обновляем все ссылки
        post_data['control_message_id'] = control_msg.message_id
        moderator_context[control_msg.message_id] = post_data
        context.user_data['edit_message_id'] = control_msg.message_id
        if message_id in edit_locks:
            del edit_locks[message_id]
        edit_locks[control_msg.message_id] = user_id
        await context.bot.send_message(
            chat_id=MODERATOR_GROUP_ID,
            text=f"Фото обновлены модератором @{update.effective_user.username}"
        )
    except Exception as e:
        logging.error(f"Ошибка при восстановлении кнопок после редактирования фото: {e}")
    context.user_data['state'] = STATE_IDLE

async def receive_edited_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Обрабатывает получение новых фото при редактировании поста.
    """
    user_id = update.message.from_user.id
    message_id = None
    for mid, pdata in moderator_context.items():
        if context.user_data.get('edit_message_id') == mid:
            message_id = mid
            break
    if not message_id:
        if moderator_context:
            message_id = list(moderator_context.keys())[-1]
    post_data = moderator_context.get(message_id)
    if not post_data:
        await update.message.reply_text("Ошибка: данные поста не найдены.")
        return
    photos = update.message.photo
    if not photos:
        await update.message.reply_text("Ошибка: отправьте фото.")
        return
    media_group_id = update.message.media_group_id
    if media_group_id:
        # Инициализация структур
        if user_id not in media_group_temp:
            media_group_temp[user_id] = {}
        if user_id not in media_group_tasks:
            media_group_tasks[user_id] = {}
        if media_group_id not in media_group_temp[user_id]:
            media_group_temp[user_id][media_group_id] = []
        media_group_temp[user_id][media_group_id].append(photos[-1])
        if media_group_id in media_group_tasks[user_id]:
            try:
                media_group_tasks[user_id][media_group_id].cancel()
            except Exception as e:
                print(f"[LOG] Ошибка при отмене таймера: {e}")
        async def timer():
            try:
                await asyncio.sleep(MEDIA_GROUP_TIMEOUT)
                await finish_media_group(user_id, media_group_id, post_data, context, update)
            except asyncio.CancelledError:
                pass
        media_group_tasks[user_id][media_group_id] = asyncio.create_task(timer())
    else:
        # Одиночное фото
        photo = photos[-1]
        file = await photo.get_file()
        file_path = os.path.join(post_data["post_path"], f"edited_photo_0.jpg")
        await file.download_to_drive(file_path)
        post_data["media"] = [file_path]
        moderator_context[message_id] = post_data
        logging.info(f"[EDIT] Получено новое фото (одиночное): user_id={user_id}, ожидается user_id={edit_locks.get(message_id)}, message_id={message_id}")
        if message_id not in edit_locks or edit_locks[message_id] != user_id:
            logging.warning(f"[EDIT] Попытка редактирования фото (одиночное) другим модератором: user_id={user_id}, ожидается user_id={edit_locks.get(message_id)}, message_id={message_id}")
            await context.bot.send_message(
                chat_id=user_id,
                text="Сейчас редактирует другой модератор.",
                reply_markup=None
            )
            return
        try:
            # Удаляем старое сообщение с кнопками
            await context.bot.delete_message(chat_id=MODERATOR_GROUP_ID, message_id=message_id)
            # 1. Отправляем новое сообщение без клавиатуры
            control_msg = await context.bot.send_message(
                chat_id=MODERATOR_GROUP_ID,
                text="Управление этим постом:",
                reply_markup=None
            )
            # 2. Создаём клавиатуру с новым message_id
            keyboard = create_inline_keyboard(message_id=control_msg.message_id)
            # 3. Обновляем reply_markup
            await control_msg.edit_reply_markup(reply_markup=keyboard)
            # 4. Обновляем все ссылки
            post_data['control_message_id'] = control_msg.message_id
            moderator_context[control_msg.message_id] = post_data
            context.user_data['edit_message_id'] = control_msg.message_id
            if message_id in edit_locks:
                del edit_locks[message_id]
            edit_locks[control_msg.message_id] = user_id
            await context.bot.send_message(
                chat_id=MODERATOR_GROUP_ID,
                text=f"Фото обновлены модератором @{update.effective_user.username}"
            )
        except Exception as e:
            logging.error(f"Ошибка при восстановлении кнопок после редактирования фото: {e}")
        context.user_data['state'] = STATE_IDLE

def ensure_contact_signature(text):
    """
    Добавляет контактную подпись к тексту для открытого канала, если её ещё нет.
    """
    if CONTACT_SIGNATURE.strip() in text:
        return text
    # Удаляем все возможные дублирующиеся подписи в конце
    text = text.rstrip()
    if text.endswith("Наш контакт: @Anastasiya_Sochneva"):
        text = text[:-(len("Наш контакт: @Anastasiya_Sochneva")).rstrip()]
    return text + CONTACT_SIGNATURE

def ensure_source_signature(text, post_path):
    """
    Добавляет подпись-источник к тексту для закрытого канала, если её ещё нет.
    """
    source_file = os.path.join(post_path, 'source.txt')
    signature = ""
    if os.path.exists(source_file):
        with open(source_file, 'r', encoding='utf-8') as f:
            source = f.read().strip()
            if source:
                if source.startswith('@'):
                    signature = f"\n\nИсточник: [{source}](https://t.me/{source[1:]})"
                else:
                    signature = f"\n\nИсточник: {source}"
    if signature.strip() and signature.strip() in text:
        return text
    return text + signature

def clean_text_for_open(text: str) -> str:
    """
    Очищает текст для публикации в открытом канале (удаляет контакты, ссылки и т.д.).
    """
    contact_keywords = [
        'тел', 'телефон', 'тлф', 'моб', 'mobile', 'phone', 'номер', 'контакт', 'контакты',
        'whatsapp', 'ватсап', 'вацап', 'viber', 'вайбер', 'signal', 'сигнал', 'tg', 'тг',
        'telegram', 'телега', 'direct', 'директ', 'личка', 'лс', 'личные сообщения', 'dm',
        'email', 'почта', 'mail', 'e-mail', 'gmail', 'yandex', 'mail.ru', 'bk.ru', 'inbox.ru',
        'outlook', 'icloud', 'protonmail', 'mailbox', 'mailcom', 'mail com', 'mail com',
        'call', 'звонить', 'звонок', 'write', 'писать', 'write me', 'contact me', 'message me',
        'write to', 'message to', 'contact to', 'связаться', 'связь', 'обращаться', 'обращайтесь',
        '📞', '☎️', '📱', '✆', '📲', '📧', '✉️', '📩', '📤', '📥', '🖂', '🖃', '🖄', '🖅', '🖆', '🖇', '🖈', '🖉', '🖊', '🖋', '🖌', '🖍', '🖎', '🖏', '🖐', '🖑', '🖒', '🖓', '🖔', '🖕', '🖖', '🖗', '🖘', '🖙', '🖚', '🖛', '🖜', '🖝', '🖞', '🖟', '🖠', '🖡', '🖢', '🖣', '🖤', '🖥', '🖦', '🖧', '🖨', '🖩', '🖪', '🖫', '🖬', '🖭', '🖮', '🖯', '🖰', '🖱', '🖲', '🖳', '🖴', '🖵', '🖶', '🖷', '🖸', '🖹', '🖺', '🖻', '🖼', '🖽', '🖾', '🖿', '🗀', '🗁', '🗂', '🗃', '🗄', '🗑', '🗒', '🗓', '🗔', '🗕', '🗖', '🗗', '🗘', '🗙', '🗚', '🗛', '🗜', '🗝', '🗞', '🗟', '🗠', '🗡', '🗢', '🗣', '🗤', '🗥', '🗦', '🗧', '🗨', '🗩', '🗪', '🗫', '🗬', '🗭', '🗮', '🗯', '🗰', '🗱', '🗲', '🗳', '🗴', '🗵', '🗶', '🗷', '🗸', '🗹', '🗺', '🗻', '🗼', '🗽', '🗾', '🗿'
    ]
    phone_regex = re.compile(r'(?:\+7|8)?[\s\-\(\)]*\d{3}[\s\-\)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}')
    intl_phone_regex = re.compile(r'\+\d{1,3}[\s\-\(\)]*\d{1,4}[\s\-\)]*\d{2,4}[\s\-]*\d{2,4}[\s\-]*\d{2,4}')
    email_regex = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
    username_regex = re.compile(r'@[a-zA-Z0-9_]{5,32}')
    url_regex = re.compile(r'(https?://\S+|www\.\S+|\S+\.(ru|com|net|org|info|biz|io|me|su|ua|by|kz|uz|pl|cz|de|fr|es|it|co|us|uk|site|store|shop|pro|online|top|xyz|club|app|dev|ai|cloud|digital|media|news|tv|fm|am|ca|jp|kr|cn|in|tr|ir|il|gr|fi|se|no|dk|ee|lv|lt|sk|hu|ro|bg|rs|hr|si|mk|al|ge|az|md|kg|tj|tm|mn|vn|th|my|sg|ph|id|au|nz|za|ng|eg|ma|tn|dz|sa|ae|qa|kw|bh|om|ye|jo|lb|sy|iq|pk|af|bd|lk|np|mm|kh|la|bt|mv|bn|tl|pg|sb|vu|fj|ws|to|tv|ck|nu|tk|pw|fm|mh|nr|ki|wf|tf|gl|aq|bv|hm|sj|sh|gs|io|ax|bl|bq|cw|gf|gp|mf|mq|re|yt|pm|tf|wf|eh|ps|ss|sx|tc|vg|vi|um|wf|yt|zm|zw))')
    lines = text.splitlines()
    clean_lines = []
    for line in lines:
        l = line.lower()
        if any(kw in l for kw in contact_keywords):
            continue
        if phone_regex.search(line) or intl_phone_regex.search(line) or email_regex.search(line):
            continue
        if username_regex.search(line):
            continue
        if url_regex.search(line):
            continue
        clean_lines.append(line)
    return '\n'.join(clean_lines).strip()

def check_forbidden_content(text: str) -> str:
    """
    Проверяет текст на наличие запрещённых элементов. Возвращает строку с описанием найденного нарушения или пустую строку, если всё чисто.
    """
    contact_keywords = [
        'тел', 'телефон', 'тлф', 'моб', 'mobile', 'phone', 'номер', 'контакт', 'контакты',
        'whatsapp', 'ватсап', 'вацап', 'viber', 'вайбер', 'signal', 'сигнал', 'tg', 'тг',
        'telegram', 'телега', 'direct', 'директ', 'личка', 'лс', 'личные сообщения', 'dm',
        'email', 'почта', 'mail', 'e-mail', 'gmail', 'yandex', 'mail.ru', 'bk.ru', 'inbox.ru',
        'outlook', 'icloud', 'protonmail', 'mailbox', 'mailcom', 'mail com', 'mail com',
        'call', 'звонить', 'звонок', 'write', 'писать', 'write me', 'contact me', 'message me',
        'write to', 'message to', 'contact to', 'связаться', 'связь', 'обращаться', 'обращайтесь',
        '📞', '☎️', '📱', '✆', '📲', '📧', '✉️', '📩', '📤', '📥'
    ]
    phone_regex = re.compile(r'(?:\+7|8)?[\s\-\(\)]*\d{3}[\s\-\)]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}')
    intl_phone_regex = re.compile(r'\+\d{1,3}[\s\-\(\)]*\d{1,4}[\s\-\)]*\d{2,4}[\s\-]*\d{2,4}[\s\-]*\d{2,4}')
    email_regex = re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+')
    username_regex = re.compile(r'@[a-zA-Z0-9_]{5,32}')
    url_regex = re.compile(r'(https?://\S+|www\.\S+|\S+\.(ru|com|net|org|info|biz|io|me|su|ua|by|kz|uz|pl|cz|de|fr|es|it|co|us|uk|site|store|shop|pro|online|top|xyz|club|app|dev|ai|cloud|digital|media|news|tv|fm|am|ca|jp|kr|cn|in|tr|ir|il|gr|fi|se|no|dk|ee|lv|lt|sk|hu|ro|bg|rs|hr|si|mk|al|ge|az|md|kg|tj|tm|mn|vn|th|my|sg|ph|id|au|nz|za|ng|eg|ma|tn|dz|sa|ae|qa|kw|bh|om|ye|jo|lb|sy|iq|pk|af|bd|lk|np|mm|kh|la|bt|mv|bn|tl|pg|sb|vu|fj|ws|to|tv|ck|nu|tk|pw|fm|mh|nr|ki|wf|tf|gl|aq|bv|hm|sj|sh|gs|io|ax|bl|bq|cw|gf|gp|mf|mq|re|yt|pm|tf|wf|eh|ps|ss|sx|tc|vg|vi|um|wf|yt|zm|zw))')
    lines = text.splitlines()
    for line in lines:
        l = line.lower()
        if any(kw in l for kw in contact_keywords):
            return 'Обнаружены запрещённые ключевые слова или контакты.'
        if phone_regex.search(line) or intl_phone_regex.search(line):
            return 'Обнаружен номер телефона.'
        if email_regex.search(line):
            return 'Обнаружен email.'
        if username_regex.search(line):
            return 'Обнаружен Telegram username.'
        if url_regex.search(line):
            return 'Обнаружена ссылка или сайт.'
    return ''

def escape_markdown(text: str) -> str:
    """
    Экранирует спецсимволы Markdown для безопасной отправки в Telegram.
    """
    escape_chars = r'_*[]()~`>#+-=|{}.!'
    return ''.join(['\\' + c if c in escape_chars else c for c in text])

async def restore_post_buttons(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """
    Восстанавливает inline-кнопки для управления постом, если они были случайно удалены.
    """
    user_id = update.effective_user.id
    if user_id not in MODERATOR_IDS:
        await update.message.reply_text("Нет доступа.")
        return
    args = context.args if hasattr(context, 'args') else []
    message_id = None
    if args and args[0].isdigit():
        message_id = int(args[0])
    else:
        if moderator_context:
            message_id = list(moderator_context.keys())[-1]
    post_data = moderator_context.get(message_id)
    if not post_data:
        await update.message.reply_text("Пост не найден или уже обработан.")
        return
    try:
        logging.info(f"[BUTTONS] Восстановление кнопок для post_id={message_id}")
        control_msg = await context.bot.send_message(
            chat_id=MODERATOR_GROUP_ID,
            text="Управление этим постом:",
            reply_markup=None
        )
        keyboard = create_inline_keyboard(message_id=control_msg.message_id)
        await control_msg.edit_reply_markup(reply_markup=keyboard)
        logging.info(f"[BUTTONS] Кнопки восстановлены для post_id={message_id}, новый message_id={control_msg.message_id}")
        post_data['control_message_id'] = control_msg.message_id
        moderator_context[control_msg.message_id] = post_data
        context.user_data['edit_message_id'] = control_msg.message_id
        await update.message.reply_text(f"Кнопки восстановлены для post_id={message_id} (новый message_id={control_msg.message_id})")
        logging.info(f"[RESTORE] Восстановлены кнопки для post_id={message_id}, новый message_id={control_msg.message_id}")
    except Exception as e:
        logging.error(f"[RESTORE] Ошибка при восстановлении кнопок: {e}")
        await update.message.reply_text(f"Ошибка при восстановлении кнопок: {e}")

def set_sent_file(post_folder):
    """
    Создаёт файл sent.txt, помечая пост как отправленный.
    """
    with open(os.path.join(post_folder, 'sent.txt'), 'w') as f:
        f.write('ok')

def unset_sent_file(post_folder):
    """
    Удаляет файл sent.txt, если он есть.
    """
    sent_path = os.path.join(post_folder, 'sent.txt')
    if os.path.exists(sent_path):
        os.remove(sent_path)

def acquire_lock(post_folder, max_age_sec=30):
    """
    Захватывает файловую блокировку для предотвращения одновременной отправки поста.
    """
    lock_path = os.path.join(post_folder, 'sending.lock')
    logging.info(f"[LOCK] Попытка захвата lock-файла: {lock_path}")
    if os.path.exists(lock_path):
        mtime = os.path.getmtime(lock_path)
        age = time.time() - mtime
        logging.warning(f"[LOCK] lock-файл уже существует: {lock_path}, age={age:.2f} сек, mtime={mtime}")
        if age > max_age_sec:
            try:
                os.remove(lock_path)
                logging.warning(f"[LOCK] Удалён устаревший lock-файл: {lock_path}")
                time.sleep(0.5)  # Дать ОС время обновить состояние
            except Exception as e:
                logging.error(f"[LOCK] Не удалось удалить устаревший lock-файл: {e}")
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        with os.fdopen(fd, 'w') as f:
            f.write(f"pid={os.getpid()} time={time.time()}\n")
        logging.info(f"[LOCK] Lock-файл создан: {lock_path} PID={os.getpid()}")
        time.sleep(0.5)  # Дать ОС время обновить состояние
        return True
    except FileExistsError:
        logging.warning(f"[LOCK] Не удалось захватить lock-файл (уже существует): {lock_path}")
        return False
    except Exception as e:
        logging.error(f"[LOCK] Ошибка при создании lock-файла: {e}")
        return False

def release_lock(post_folder):
    """
    Освобождает файловую блокировку после отправки поста.
    """
    lock_path = os.path.join(post_folder, 'sending.lock')
    if os.path.exists(lock_path):
        try:
            os.remove(lock_path)
            logging.info(f"[LOCK] Lock-файл освобождён: {lock_path}")
            time.sleep(0.5)  # Дать ОС время обновить состояние
        except Exception as e:
            logging.error(f"[LOCK] Не удалось удалить lock-файл при release: {e}")
    else:
        logging.info(f"[LOCK] Lock-файл уже отсутствует при release: {lock_path}")

def is_sent_open(post_folder):
    """
    Проверяет наличие файла send_open.txt (отправлен в открытый канал).
    """
    return os.path.exists(os.path.join(post_folder, 'send_open.txt'))
def is_sent_close(post_folder):
    """
    Проверяет наличие файла send_close.txt (отправлен в закрытый канал).
    """
    return os.path.exists(os.path.join(post_folder, 'send_close.txt'))
def set_sent_open(post_folder):
    """
    Создаёт файл send_open.txt, помечая пост как отправленный в открытый канал.
    """
    with open(os.path.join(post_folder, 'send_open.txt'), 'w') as f:
        f.write('ok')
def set_sent_close(post_folder):
    """
    Создаёт файл send_close.txt, помечая пост как отправленный в закрытый канал.
    """
    with open(os.path.join(post_folder, 'send_close.txt'), 'w') as f:
        f.write('ok')

if __name__ == "__main__":
    while True:
        try:
            application = Application.builder().token(BOT_TOKEN).read_timeout(30).write_timeout(30).build()
            application.add_handler(CommandHandler("start", start))
            application.add_handler(CommandHandler("restore_buttons", restore_post_buttons))
            application.add_handler(CallbackQueryHandler(global_callback_handler))
            application.add_handler(MessageHandler(filters.TEXT, global_text_handler))
            application.add_handler(MessageHandler(filters.PHOTO, global_photo_handler))
            application.add_handler(CallbackQueryHandler(log_all_callbacks))
            loop = asyncio.get_event_loop()
            loop.create_task(main_loop(application.bot))
            application.run_polling(drop_pending_updates=True)
        except Exception as e:
            logging.error(f"Ошибка polling: {e}. Перезапуск через 10 секунд...")
            time.sleep(10) 