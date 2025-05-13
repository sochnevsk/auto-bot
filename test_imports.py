"""
Тестовый скрипт для проверки импортов.
"""
import sys
import os

# Добавляем корневую директорию в PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Проверяем импорты
try:
    from src.config.settings import settings
    print("✅ settings.py импортирован успешно")
    
    from src.utils.logger import setup_logger
    print("✅ logger.py импортирован успешно")
    
    from src.bot.bot import Bot
    print("✅ bot.py импортирован успешно")
    
    # Проверяем создание логгера
    logger = setup_logger("test")
    print("✅ Логгер создан успешно")
    
    # Проверяем настройки
    print(f"BOT_TOKEN: {'✅' if settings.BOT_TOKEN else '❌'}")
    print(f"MODERATOR_IDS: {'✅' if settings.moderator_ids else '❌'}")
    
except ImportError as e:
    print(f"❌ Ошибка импорта: {e}")
except Exception as e:
    print(f"❌ Ошибка: {e}") 