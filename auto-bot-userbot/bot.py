import os
import asyncio
import logging
import signal
from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto
from telethon.tl.types import PeerChannel
from telethon.tl.types import Message
from telethon.tl.functions.messages import GetDialogsRequest
from telethon.tl.types import InputPeerEmpty, Dialog, Channel
from dotenv import load_dotenv
from datetime import datetime, timedelta
from helpers import clean_text_for_open
from telethon.errors import RPCError
import time
import shutil
import json
from collections import OrderedDict, deque
import uuid

load_dotenv()

API_ID = int(os.getenv('API_ID', '26521480'))
API_HASH = os.getenv('API_HASH', '858b8e9363acd79e1122748c621c08e1')
SESSION = os.getenv('SESSION', 'anon')
SAVED_DIR = os.getenv('SAVE_DIR', os.path.join(os.getcwd(), 'saved'))

if not os.path.exists(SAVED_DIR):
    os.makedirs(SAVED_DIR)

client = TelegramClient(
    SESSION, API_ID, API_HASH,
    device_model='MacBook Pro',
    system_version='macOS 12.6',
    app_version='Telegram Desktop 4.15',
    lang_code='ru',
    system_lang_code='ru-RU'
)

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

class LimitedSet:
    """
    Класс для хранения ограниченного количества уникальных элементов.
    При превышении лимита удаляет самые старые элементы.
    Поддерживает сохранение и загрузку из файла.
    """
    def __init__(self, max_size=500, cache_file=None):
        self.max_size = max_size
        self._set = set()
        self._queue = deque(maxlen=max_size)
        self.cache_file = cache_file
        self._load_from_file()

    def add(self, item):
        """Добавляет элемент в набор"""
        if item in self._set:
            return False
        if len(self._set) >= self.max_size:
            # Удаляем самый старый элемент
            old_item = self._queue.popleft()
            self._set.remove(old_item)
        self._set.add(item)
        self._queue.append(item)
        self._save_to_file()
        return True

    def __contains__(self, item):
        """Проверяет наличие элемента в наборе"""
        return item in self._set

    def __len__(self):
        """Возвращает текущий размер набора"""
        return len(self._set)

    def _save_to_file(self):
        """Сохраняет текущее состояние в файл"""
        if not self.cache_file:
            return
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(list(self._set), f)
        except Exception as e:
            logging.error(f"Ошибка при сохранении кэша в файл {self.cache_file}: {e}")

    def _load_from_file(self):
        """Загружает состояние из файла"""
        if not self.cache_file or not os.path.exists(self.cache_file):
            return
        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                items = json.load(f)
                for item in items:
                    if len(self._set) < self.max_size:
                        self._set.add(item)
                        self._queue.append(item)
            logging.info(f"Загружено {len(self._set)} элементов из {self.cache_file}")
        except Exception as e:
            logging.error(f"Ошибка при загрузке кэша из файла {self.cache_file}: {e}")

# Создаем директорию для кэша, если её нет
CACHE_DIR = os.path.join(os.getcwd(), 'cache')
if not os.path.exists(CACHE_DIR):
    os.makedirs(CACHE_DIR)

# Инициализируем наборы с ограничением размера и файлами кэша
processed_media = LimitedSet(
    max_size=500,
    cache_file=os.path.join(CACHE_DIR, 'processed_media.json')
)
processed_albums = LimitedSet(
    max_size=500,
    cache_file=os.path.join(CACHE_DIR, 'processed_albums.json')
)
processed_documents = LimitedSet(
    max_size=500,
    cache_file=os.path.join(CACHE_DIR, 'processed_documents.json')
)

def maintain_saved_limit():
    """Поддерживает лимит сохраненных постов"""
    folder = SAVED_DIR
    max_posts = 100  # Максимальное количество постов
    posts = []
    
    # Собираем все посты
    for root, dirs, files in os.walk(folder, topdown=False):
        for dir_name in dirs:
            if dir_name.startswith('post_'):
                post_path = os.path.join(root, dir_name)
                posts.append((post_path, os.path.getctime(post_path)))
    
    # Сортируем по дате создания (старые первые)
    posts.sort(key=lambda x: x[1])
    
    # Удаляем лишние посты
    while len(posts) > max_posts:
        post_path, _ = posts.pop(0)
        try:
            shutil.rmtree(post_path)
            logging.info(f"Удален старый пост: {post_path}")
        except Exception as e:
            logging.error(f"Ошибка при удалении поста {post_path}: {e}")

def save_text_and_source(post_dir, text, source_name, log_prefix=""):
    """
    Сохраняет текст поста и источник (название канала) в соответствующие файлы в папке поста.
    Args:
        post_dir (str): Путь к папке поста
        text (str): Текст поста
        source_name (str): Название источника (канала)
        log_prefix (str): Префикс для логирования
    """
    if text:
        with open(os.path.join(post_dir, 'text_close.txt'), 'w', encoding='utf-8') as f:
            f.write(text.strip())
        with open(os.path.join(post_dir, 'source.txt'), 'w', encoding='utf-8') as f:
            f.write(source_name)
        logging.info(f"{log_prefix}Сохранил текст: {text}")

def save_ready_flag(post_dir):
    """
    Создаёт файл-флаг ready.txt, сигнализирующий о готовности поста к дальнейшей обработке.
    Args:
        post_dir (str): Путь к папке поста
    """
    with open(os.path.join(post_dir, 'ready.txt'), 'w') as f:
        f.write('ok')


# --- Сохранение медиа из каналов ---
@client.on(events.NewMessage(incoming=True, func=lambda e: e.is_channel))
async def save_channel_message(event):
    """
    Основной обработчик новых сообщений из каналов.
    Сохраняет альбомы, одиночные фото, фото-документы и текстовые посты в отдельные папки.
    Для альбомов собирает все сообщения с одинаковым grouped_id.
    Для каждого поста сохраняет текст, источник, медиа и файл ready.txt.
    """
    post_folder = None
    try:
        # Проверяем, что папка saved существует
        if not os.path.exists(SAVED_DIR):
            os.makedirs(SAVED_DIR)
            logging.info(f"Создана директория {SAVED_DIR}")

        # Проверяем, не был ли пост уже обработан
        if event.media:
            # Для альбомов используем только grouped_id
            if event.grouped_id:
                album_key = f"{event.chat_id}_{event.grouped_id}"
                if album_key in processed_albums or not processed_albums.add(album_key):
                    logging.info(f"⏭️ Альбом {album_key} уже был обработан")
                    return
            # Для одиночных медиа используем id
            else:
                media_key = f"{event.chat_id}_{event.id}"
                if media_key in processed_media or not processed_media.add(media_key):
                    logging.info(f"⏭️ Медиа {media_key} уже было обработано")
                    return
            
        # Для фото-документов проверяем, не был ли он уже обработан
        if event.media and hasattr(event.media, 'document'):
            if event.media.document.mime_type.startswith('image/'):
                doc_key = f"{event.chat_id}_{event.id}"
                if doc_key in processed_documents or not processed_documents.add(doc_key):
                    logging.info(f"⏭️ Фото-документ {doc_key} уже был обработан")
                    return

        # Создаем папку для поста с ID сообщения
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        message_id = event.id
        post_folder = os.path.join(SAVED_DIR, f"post_{timestamp}_{message_id}")
        os.makedirs(post_folder, exist_ok=True)

        # Определяем тип сообщения и сохраняем соответствующим способом
        if event.grouped_id:
            logging.info(f"📦 Обработка альбома из канала {event.chat.title}")
            await save_album(event, post_folder)
        elif event.media and isinstance(event.media, MessageMediaPhoto):
            if not event.text:
                logging.info(f"⏭️ Пропуск фото без текста из канала {event.chat.title}")
                if os.path.exists(post_folder):
                    shutil.rmtree(post_folder)
                return
            logging.info(f"📸 Обработка одиночного фото из канала {event.chat.title}")
            await save_single_photo(event, post_folder)
        elif event.media and hasattr(event.media, 'document'):
            if event.media.document.mime_type.startswith('image/'):
                if not event.text:
                    logging.info(f"⏭️ Пропуск фото-документа без текста из канала {event.chat.title}")
                    if os.path.exists(post_folder):
                        shutil.rmtree(post_folder)
                    return
                logging.info(f"📄 Обработка фото-документа из канала {event.chat.title}")
                await save_photo_document(event, post_folder)
            else:
                logging.info(f"⏭️ Пропуск не фото документа из канала {event.chat.title}")
                if os.path.exists(post_folder):
                    shutil.rmtree(post_folder)
                return
        else:
            logging.info(f"⏭️ Пропуск поста без фото из канала {event.chat.title}")
            if os.path.exists(post_folder):
                shutil.rmtree(post_folder)
            return

        # Сохраняем информацию об источнике только если пост был успешно сохранен
        if os.path.exists(post_folder):
            source_info = f"Канал: @{event.chat.username}\nДата: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\nID сообщения: {message_id}"
            source_path = os.path.join(post_folder, "source.txt")
            with open(source_path, "w", encoding="utf-8") as f:
                f.write(source_info)

            # Создаем файл ready.txt
            save_ready_flag(post_folder)
            logging.info(f"✅ Пост успешно сохранен в {post_folder}")

    except Exception as e:
        if post_folder and os.path.exists(post_folder):
            logging.error(f"❌ Ошибка при сохранении поста: {e}")
            try:
                error_info = f"Ошибка: {str(e)}\nВремя: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
                error_path = os.path.join(post_folder, "error.txt")
                with open(error_path, "w", encoding="utf-8") as f:
                    f.write(error_info)
            except Exception as inner_e:
                logging.error(f"❌ Не удалось сохранить информацию об ошибке: {inner_e}")
            shutil.rmtree(post_folder)

async def save_album(event, post_folder):
    """Сохранение альбома с фото"""
    try:
        # Получаем все сообщения альбома
        album_messages = []
        async for message in client.iter_messages(event.chat_id, min_id=event.id - 10, max_id=event.id + 10):
            if message.grouped_id == event.grouped_id:
                album_messages.append(message)

        # Сортируем по ID для правильного порядка
        album_messages.sort(key=lambda x: x.id)
        total_photos = len(album_messages)

        # Проверяем наличие текста хотя бы в одном сообщении альбома
        has_text = False
        album_text = None
        for msg in album_messages:
            if msg.text:
                has_text = True
                album_text = msg.text
                break

        if not has_text:
            logging.info(f"⏭️ Пропуск альбома без текста")
            if os.path.exists(post_folder):
                shutil.rmtree(post_folder)
            return

        # Сохраняем только фото из альбома
        saved_files = []
        photo_count = 0
        for msg in album_messages:
            if msg.media and isinstance(msg.media, MessageMediaPhoto):
                photo_count += 1
                logging.info(f"📥 Скачивание фото {photo_count} из альбома...")
                file = await msg.download_media(file=os.path.join(post_folder, f"photo_{photo_count}.jpg"))
                if file:
                    saved_files.append(file)
            elif msg.media and hasattr(msg.media, 'document') and msg.media.document.mime_type.startswith('image/'):
                photo_count += 1
                logging.info(f"📥 Скачивание фото-документа {photo_count} из альбома...")
                file = await msg.download_media(file=os.path.join(post_folder, f"photo_{photo_count}.jpg"))
                if file:
                    saved_files.append(file)
            else:
                pass

        # Сохраняем текст из сообщения, где он был найден
        if album_text:
            original_text = album_text
            cleaned_text = clean_text_for_open(original_text)
            
            with open(os.path.join(post_folder, "text.txt"), "w", encoding="utf-8") as f:
                f.write(cleaned_text)

            with open(os.path.join(post_folder, "text_close.txt"), "w", encoding="utf-8") as f:
                f.write(original_text)
        
        logging.info(f"✅ Альбом сохранен: {len(saved_files)} фото")

    except Exception as e:
        logging.error(f"❌ Ошибка при сохранении альбома: {e}")
        if os.path.exists(post_folder):
            shutil.rmtree(post_folder)

async def save_single_photo(event, post_folder):
    """Сохранение одиночного фото"""
    try:
        # Проверяем наличие текста
        if not event.text:
            logging.info(f"⏭️ Пропуск фото без текста")
            if os.path.exists(post_folder):
                shutil.rmtree(post_folder)
            return

        # Сохраняем фото
        logging.info(f"📥 Скачивание фото...")
        saved_file = await event.download_media(file=os.path.join(post_folder, "photo_1.jpg"))
        if saved_file:
            pass
        
        # Сохраняем текст
        with open(os.path.join(post_folder, "text.txt"), "w", encoding="utf-8") as f:
            f.write(clean_text_for_open(event.text))
        with open(os.path.join(post_folder, "text_close.txt"), "w", encoding="utf-8") as f:
            f.write(event.text)
        logging.info(f"✅ Фото сохранено")

    except Exception as e:
        logging.error(f"❌ Ошибка при сохранении фото: {e}")
        if os.path.exists(post_folder):
            shutil.rmtree(post_folder)

async def save_photo_document(event, post_folder):
    """Сохранение фото-документа"""
    try:
        # Проверяем наличие текста
        if not event.text:
            logging.info(f"⏭️ Пропуск фото-документа без текста")
            if os.path.exists(post_folder):
                shutil.rmtree(post_folder)
            return

        # Сохраняем фото-документ
        logging.info(f"📥 Скачивание фото-документа...")
        saved_file = await event.download_media(file=os.path.join(post_folder, "photo_1.jpg"))
        if saved_file:
            pass
        
        # Сохраняем текст
        with open(os.path.join(post_folder, "text.txt"), "w", encoding="utf-8") as f:
            f.write(clean_text_for_open(event.text))
        with open(os.path.join(post_folder, "text_close.txt"), "w", encoding="utf-8") as f:
            f.write(event.text)
        logging.info(f"✅ Фото-документ сохранен")

    except Exception as e:
        logging.error(f"❌ Ошибка при сохранении фото-документа: {e}")
        if os.path.exists(post_folder):
            shutil.rmtree(post_folder)

async def save_text_post(event, post_folder):
    """Сохранение текстового поста"""
    try:
        # Сохраняем текст
        if event.text:
            #logging.info(f"Получен текст для сохранения: {event.text[:100]}...")  # Логируем первые 100 символов
            cleaned_text = clean_text_for_open(event.text)
            #logging.info(f"Очищенный текст: {cleaned_text[:100]}...")  # Логируем первые 100 символов очищенного текста
            
            with open(os.path.join(post_folder, "text.txt"), "w", encoding="utf-8") as f:
                f.write(cleaned_text)  # Сохраняем очищенный текст
            with open(os.path.join(post_folder, "text_close.txt"), "w", encoding="utf-8") as f:
                f.write(event.text)  # Сохраняем оригинальный текст
            logging.info(f"Текст сохранен в text.txt и text_close.txt")

    except Exception as e:
        logging.error(f"Ошибка при сохранении текстового поста: {e}")

@client.on(events.NewMessage(pattern='/channels'))
async def channels_command(event):
    """
    Обработчик команды /channels.
    Выводит список всех каналов, на которые подписан бот.
    """
    try:
        channels = await get_channels_list()
        if not channels:
            await event.respond("Бот не подписан ни на один канал.")
            return

        response = "📋 Список каналов:\n\n"
        for i, channel in enumerate(channels, 1):
            username = f"@{channel['username']}" if channel['username'] else "Нет username"
            response += f"{i}. {channel['title']}\n"
            response += f"   ID: {channel['id']}\n"
            response += f"   Username: {username}\n"
            response += f"   Участников: {channel['participants_count']}\n\n"

        # Разбиваем сообщение на части, если оно слишком длинное
        max_length = 4096
        for i in range(0, len(response), max_length):
            await event.respond(response[i:i + max_length])
            
    except Exception as e:
        logging.error(f"Ошибка при получении списка каналов: {e}")
        await event.respond("Произошла ошибка при получении списка каналов.")

class BotState:
    def __init__(self):
        self.is_shutting_down = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 10  # начальная задержка в секундах

if __name__ == '__main__':
    logging.info('Запуск юзербота...')
    
    # Получаем текущий event loop
    loop = asyncio.get_event_loop()
    
    # Создаем объект для управления состоянием
    state = BotState()
    
    async def shutdown(signal_name, loop):
        """Корректное завершение работы бота"""
        if state.is_shutting_down:
            return
            
        state.is_shutting_down = True
        logging.info(f"Получен сигнал {signal_name}...")
        
        try:
            # Отключаем клиента
            try:
                if hasattr(client, 'is_connected') and client.is_connected():
                    logging.info("Отключаем клиента Telegram...")
                    # Отключаем клиента
                    await client.disconnect()
                    # Ждем завершения всех операций отключения
                    await asyncio.sleep(1)
                    logging.info("Клиент Telegram отключен")
            except Exception as e:
                logging.warning(f"Ошибка при отключении клиента: {e}")
            
            # Отменяем все задачи
            tasks = [t for t in asyncio.all_tasks() if t is not asyncio.current_task()]
            for task in tasks:
                task.cancel()
            
            logging.info(f"Отменено {len(tasks)} задач")
            # Ждем завершения всех задач
            await asyncio.gather(*tasks, return_exceptions=True)
            
            # Даем время на завершение всех операций
            await asyncio.sleep(1)
            
        except Exception as e:
            logging.error(f"Ошибка при завершении работы: {e}")
        finally:
            try:
                loop.stop()
                logging.info("Бот остановлен")
            except Exception as e:
                logging.error(f"Ошибка при остановке loop: {e}")
    
    def handle_signal(sig, frame):
        """Обработчик сигналов"""
        signal_name = signal.Signals(sig).name
        logging.info(f"Получен сигнал {signal_name}")
        # Запускаем shutdown в отдельном потоке
        asyncio.run_coroutine_threadsafe(shutdown(signal_name, loop), loop)
    
    # Регистрируем обработчики сигналов
    signals = (signal.SIGTERM, signal.SIGINT)
    for s in signals:
        signal.signal(s, handle_signal)
    
    while not state.is_shutting_down:
        try:
            with client:
                # Сбрасываем счетчик попыток при успешном подключении
                state.reconnect_attempts = 0
                state.reconnect_delay = 10
                logging.info("Бот успешно подключен к Telegram")
                try:
                    client.run_until_disconnected()
                except asyncio.CancelledError:
                    logging.info("Получен сигнал отмены, завершаем работу...")
                    break
                
        except (OSError, RPCError) as e:
            if state.is_shutting_down:
                break
                
            state.reconnect_attempts += 1
            if state.reconnect_attempts > state.max_reconnect_attempts:
                logging.error(f"Превышено максимальное количество попыток переподключения ({state.max_reconnect_attempts}). Бот остановлен.")
                break
                
            # Экспоненциальная задержка между попытками
            delay = min(state.reconnect_delay * (2 ** (state.reconnect_attempts - 1)), 300)  # максимум 5 минут
            logging.error(f'Ошибка соединения с Telegram API: {e}. Попытка {state.reconnect_attempts} из {state.max_reconnect_attempts}. Переподключение через {delay} секунд...')
            time.sleep(delay)
            
        except Exception as e:
            if state.is_shutting_down:
                break
                
            logging.error(f'Неизвестная ошибка: {e}. Перезапуск через 30 секунд...')
            time.sleep(30)
            
        finally:
            if not state.is_shutting_down and state.reconnect_attempts > state.max_reconnect_attempts:
                # Очищаем все задачи
                pending = asyncio.all_tasks(loop)
                for task in pending:
                    task.cancel()
                
                # Запускаем loop до завершения всех задач
                loop.run_until_complete(asyncio.gather(*pending, return_exceptions=True))
    
    # Закрываем loop
    try:
        loop.close()
        logging.info("Бот полностью остановлен")
    except Exception as e:
        logging.error(f"Ошибка при закрытии loop: {e}")
        
    # Принудительное завершение процесса
    os._exit(0) 