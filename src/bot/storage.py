"""
Модуль для работы с хранилищем данных.
"""
import os
import json
import asyncio
import logging
from typing import Dict, Any

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