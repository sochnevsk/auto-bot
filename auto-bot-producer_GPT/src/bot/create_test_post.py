import asyncio
from telegram import Bot, InlineKeyboardMarkup, InlineKeyboardButton

async def create_test_post():
    # Создаем бота
    bot = Bot(token='YOUR_BOT_TOKEN')
    
    # ID тестового чата
    chat_id = 'YOUR_CHAT_ID'
    
    # Создаем клавиатуру
    keyboard = [
        [
            InlineKeyboardButton("✅ Модерировать", callback_data="moderate_test_post"),
            InlineKeyboardButton("❌ Удалить", callback_data="quick_delete_test_post")
        ]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    
    # Отправляем тестовый пост
    await bot.send_message(
        chat_id=chat_id,
        text="Тестовый пост для проверки FSM\n\nЭтот пост содержит кнопки модерации.",
        reply_markup=reply_markup
    )
    
    # Закрываем бота
    await bot.close()

if __name__ == '__main__':
    asyncio.run(create_test_post()) 