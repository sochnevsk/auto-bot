"""
Модуль для работы с хранилищем данных.
"""
import os
import json
import asyncio
import logging
from typing import Dict, Any
from datetime import datetime

logger = logging.getLogger(__name__)


class AsyncFileManager:
    """
    Асинхронный файловый менеджер с блокировкой для работы с storage.json
    """
    
    def __init__(self, path: str):
        self.path = path
        self.lock_path = f"{path}.lock"
        self._lock = None

    async def __aenter__(self):
        await self.acquire_lock()
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.release_lock()

    async def acquire_lock(self):
        """Асинхронно получает блокировку файла."""
        while True:
            try:
                if not os.path.exists(self.lock_path):
                    with open(self.lock_path, 'w') as f:
                        f.write(str(os.getpid()))
                    self._lock = True
                    break
                await asyncio.sleep(0.1)
            except Exception as e:
                logger.error(f"Error acquiring lock: {e}")
                await asyncio.sleep(0.1)

    async def release_lock(self):
        """Асинхронно освобождает блокировку файла."""
        try:
            if os.path.exists(self.lock_path):
                os.remove(self.lock_path)
            self._lock = None
        except Exception as e:
            logger.error(f"Error releasing lock: {e}")

    async def read(self) -> Dict[str, Any]:
        """Асинхронно читает данные из файла."""
        try:
            if not os.path.exists(self.path):
                return {}
            with open(self.path, 'r', encoding='utf-8') as f:
                content = f.read()
                if not content.strip():
                    return {}
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e:
                    logger.error(f"Error decoding JSON: {e}")
                    # Если файл поврежден, создаем новый
                    await self.write({})
                    return {}
        except Exception as e:
            logger.error(f"Error reading file: {e}")
            return {}

    async def write(self, data: Dict[str, Any]):
        """Асинхронно записывает данные в файл."""
        try:
            # Создаем временный файл
            temp_path = f"{self.path}.tmp"
            with open(temp_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            # Атомарно заменяем старый файл новым
            os.replace(temp_path, self.path)
        except Exception as e:
            logger.error(f"Error writing file: {e}")
            if os.path.exists(temp_path):
                os.remove(temp_path)


class SentPostsCache:
    """Кэш для хранения информации об отправленных постах."""
    def __init__(self, cache_file: str = "sent_posts_cache.json"):
        self.cache_file = cache_file
        self._cache: Dict[str, Any] = {
            "last_check": datetime.now().isoformat(),
            "sent_posts": {}
        }
        self._load_cache()

    def _load_cache(self) -> None:
        """Загрузка кэша из файла."""
        try:
            if os.path.exists(self.cache_file):
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
                logger.info(f"Cache loaded from {self.cache_file}")
        except Exception as e:
            logger.error(f"Error loading cache: {e}")
            self._cache = {
                "last_check": datetime.now().isoformat(),
                "sent_posts": {}
            }

    def _save_cache(self) -> None:
        """Сохранение кэша в файл."""
        try:
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, ensure_ascii=False, indent=2)
            logger.info(f"Cache saved to {self.cache_file}")
        except Exception as e:
            logger.error(f"Error saving cache: {e}")

    def is_post_sent(self, post_id: str) -> bool:
        """Проверяет, был ли пост уже отправлен."""
        return post_id in self._cache["sent_posts"] and self._cache["sent_posts"][post_id]["status"] == "sent"

    def add_sent_post(self, post_id: str) -> None:
        """Добавляет пост в кэш отправленных."""
        self._cache["sent_posts"][post_id] = {
            "timestamp": datetime.now().isoformat(),
            "status": "sent"
        }
        self._save_cache()

    def add_post(self, post_id: str) -> None:
        """Алиас для add_sent_post для обратной совместимости."""
        self.add_sent_post(post_id)

    def remove_post(self, post_id: str) -> None:
        """Удаляет пост из кэша."""
        if post_id in self._cache["sent_posts"]:
            del self._cache["sent_posts"][post_id]
            self._save_cache()

    def update_last_check(self) -> None:
        """Обновляет timestamp последней проверки."""
        self._cache["last_check"] = datetime.now().isoformat()
        self._save_cache()

    def get_last_check(self) -> str:
        """Возвращает timestamp последней проверки."""
        return self._cache["last_check"]

    def clear_cache(self) -> None:
        """Очищает кэш."""
        self._cache = {
            "last_check": datetime.now().isoformat(),
            "sent_posts": {}
        }
        self._save_cache()

    async def sync_with_storage(self, storage_path: str = "storage.json") -> None:
        """Синхронизирует кэш с storage.json."""
        try:
            if os.path.exists(storage_path):
                with open(storage_path, 'r', encoding='utf-8') as f:
                    storage_data = json.load(f)
                
                # Добавляем все посты из storage в кэш
                for post_id, post_info in storage_data.items():
                    if post_info.get('status') == 'sent':
                        self._cache["sent_posts"][post_id] = {
                            "timestamp": post_info.get('datetime', datetime.now().isoformat()),
                            "status": "sent"
                        }
                
                self._save_cache()
                logger.info(f"Cache synchronized with {storage_path}")
        except Exception as e:
            logger.error(f"Error synchronizing cache with storage: {e}") 