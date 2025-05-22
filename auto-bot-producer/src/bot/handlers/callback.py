import os
import logging
from telegram import Update
from telegram.ext import ContextTypes

async def handle_media_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """
    Обработчик callback-запросов для подтверждения сохранения медиа.
    """
    query = update.callback_query
    await query.answer()
    
    data = query.data
    if data == "cancelmedia":
        await query.message.edit_text("Сохранение медиа отменено")
        return
        
    if data.startswith("confirmmedia:"):
        try:
            # Получаем пути к файлам
            paths = data.split(":", 1)[1].split(",")
            
            # Проверяем существование файлов
            valid_paths = [p for p in paths if os.path.exists(p)]
            
            if not valid_paths:
                await query.message.edit_text("Ошибка: файлы не найдены")
                return
                
            # Здесь можно добавить логику сохранения путей в базу данных
            # или другую обработку подтвержденных файлов
            
            await query.message.edit_text(
                f"Сохранено {len(valid_paths)} файлов:\n" + 
                "\n".join(f"- {os.path.basename(p)}" for p in valid_paths)
            )
            
        except Exception as e:
            logging.error(f"Ошибка при обработке подтверждения медиа: {e}")
            await query.message.edit_text("Произошла ошибка при сохранении медиа") 