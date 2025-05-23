class BotState:
    """
    Класс для управления состоянием бота.
    Хранит информацию о текущем состоянии и настройках переподключения.
    """
    def __init__(self):
        self.is_shutting_down = False
        self.reconnect_attempts = 0
        self.max_reconnect_attempts = 5
        self.reconnect_delay = 10  # Начальная задержка в секундах 