"""
Настройки бота.
"""
import os
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field
from dotenv import load_dotenv

# Загружаем переменные окружения из .env файла
load_dotenv()

class Settings(BaseSettings):
    """Настройки бота."""
    BOT_TOKEN: str = Field(..., description="Токен бота Telegram")
    MODERATOR_GROUP_ID: str = Field(..., description="ID группы модераторов")
    MODERATOR_IDS: str = Field(..., description="ID модераторов через запятую или в кавычках")
    OPEN_CHANNEL_ID: str = Field(..., description="ID открытого канала")
    CLOSED_CHANNEL_ID: str = Field(..., description="ID закрытого канала")
    MAX_POSTS: int = Field(100, description="Максимальное количество постов")
    MEDIA_GROUP_TIMEOUT: float = Field(9.0, description="Таймаут для медиагрупп")
    CHANNELS: str = Field(default="", description="Список каналов через запятую")
    MEDIA_DIR: str = Field(default="media", description="Директория для медиафайлов")
    LOG_DIR: str = Field(default="logs", description="Директория для логов")
    LOG_LEVEL: str = Field(default="INFO", description="Уровень логирования")
    LOG_FORMAT: str = Field(
        default="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
        description="Формат логов"
    )

    @property
    def moderator_ids(self) -> List[int]:
        # Убираем кавычки и пробелы, разбиваем по запятой
        return [int(x.strip().replace('"', '')) for x in self.MODERATOR_IDS.split(',') if x.strip()]

    @property
    def channels(self) -> List[str]:
        return [x.strip() for x in self.CHANNELS.split(",") if x.strip()]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"

# Создаем экземпляр настроек
settings = Settings()

# Создаем необходимые директории
os.makedirs(settings.MEDIA_DIR, exist_ok=True)
os.makedirs(settings.LOG_DIR, exist_ok=True) 