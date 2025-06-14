import asyncio
import logging
from telegram.ext import Application
from handlers.test_handlers import setup_handlers

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('bot.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

async def main():
    # Создаем приложение
    application = Application.builder().token('YOUR_BOT_TOKEN').build()
    
    # Настраиваем обработчики
    setup_handlers(application)
    
    # Запускаем бота
    await application.run_polling()

if __name__ == '__main__':
    asyncio.run(main()) 