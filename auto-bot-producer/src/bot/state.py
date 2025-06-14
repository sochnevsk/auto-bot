class ChatContext:
    def __init__(self, chat_id: int):
        self.chat_id = chat_id
        self.is_moderating = False
        self.pending_posts = set()  # Множество для хранения ID ожидающих постов

    async def start_moderation(self):
        """Начать модерацию в чате"""
        self.is_moderating = True
        logger.info(f"Начата модерация в чате {self.chat_id}")

    async def end_moderation(self):
        """Завершить модерацию в чате"""
        self.is_moderating = False
        self.pending_posts.clear()  # Очищаем список ожидающих постов
        logger.info(f"Завершена модерация в чате {self.chat_id}") 