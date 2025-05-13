"""
Настройка логирования.
"""
import logging
import os
from logging.handlers import RotatingFileHandler
from src.config.settings import settings

def setup_logger(name: str) -> logging.Logger:
    """
    Настройка логгера.
    
    Args:
        name: Имя логгера
        
    Returns:
        logging.Logger: Настроенный логгер
    """
    # Создаем логгер
    logger = logging.getLogger(name)
    logger.setLevel(settings.LOG_LEVEL)
    
    # Создаем форматтер
    formatter = logging.Formatter(settings.LOG_FORMAT)
    
    # Создаем обработчик для файла
    log_file = os.path.join(settings.LOG_DIR, f"{name}.log")
    file_handler = RotatingFileHandler(
        log_file,
        maxBytes=10*1024*1024,  # 10MB
        backupCount=5,
        encoding='utf-8'
    )
    file_handler.setFormatter(formatter)
    
    # Создаем обработчик для консоли
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    
    # Добавляем обработчики к логгеру
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    return logger 