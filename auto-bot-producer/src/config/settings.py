"""
Настройки бота.
"""
import os
from typing import List
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    """Настройки бота."""
    
    # Токен бота
    BOT_TOKEN: str = os.getenv("BOT_TOKEN", "")
    
    # ID группы модераторов
    MODERATOR_GROUP_ID: int = int(os.getenv("MODERATOR_GROUP_ID", "0"))
    
    # ID открытого канала
    PUBLIC_CHANNEL_ID: int = int(os.getenv("PUBLIC_CHANNEL_ID", "0"))
    
    # ID закрытого канала
    PRIVATE_CHANNEL_ID: int = int(os.getenv("PRIVATE_CHANNEL_ID", "0"))
    
    # ID модератора
    MODERATOR_IDS: int = int(os.getenv("MODERATOR_IDS", "0"))

    # ID модератора
    SAVE_DIR: str = os.getenv('SAVE_DIR', os.path.join(os.getcwd(), 'saved'))
    
    # Настройки логирования
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")
    LOG_FORMAT: str = os.getenv("LOG_FORMAT", "%(asctime)s - %(name)s - %(levelname)s - [%(filename)s:%(lineno)d] - %(message)s")
    LOG_DIR: str = os.getenv("LOG_DIR", "logs")
    
    class Config:
        """Конфигурация настроек."""
        env_file = ".env"
        env_file_encoding = "utf-8"

# Создаем экземпляр настроек
settings = Settings() 