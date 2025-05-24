import os
from pathlib import Path
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()

# Базовые пути
BASE_DIR = Path(__file__).resolve().parent.parent
LOGS_DIR = BASE_DIR / 'logs'
CONFIG_DIR = BASE_DIR / 'config'

# Создаем директории если их нет
LOGS_DIR.mkdir(exist_ok=True)
CONFIG_DIR.mkdir(exist_ok=True)

# Конфигурация API
SBER_API_URL = os.getenv('SBER_API_URL')
SBER_AUTH_URL = os.getenv('SBER_AUTH_URL')
CLIENT_ID = os.getenv('SBER_CLIENT_ID')
CLIENT_SECRET = os.getenv('SBER_CLIENT_SECRET')

# Путь к директории с постами
SAVE_DIR = os.getenv('SAVE_DIR')

# Лимиты токенов
MONTHLY_TOKEN_LIMIT = int(os.getenv('MONTHLY_TOKEN_LIMIT', 100_000))
DAILY_TOKEN_LIMIT = int(os.getenv('DAILY_TOKEN_LIMIT', 10_000))
SINGLE_REQUEST_LIMIT = int(os.getenv('SINGLE_REQUEST_LIMIT', 2_000))

# Пороги предупреждений (в процентах)
WARNING_THRESHOLD = int(os.getenv('WARNING_THRESHOLD', 80))
CRITICAL_THRESHOLD = int(os.getenv('CRITICAL_THRESHOLD', 90))

# Файл для хранения статистики
TOKEN_STATS_FILE = CONFIG_DIR / 'token_stats.json'

# Настройки логирования
LOG_FILE = LOGS_DIR / 'formatter.log'
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

# Промпт для форматирования
FORMAT_PROMPT = """Ты автомобильный эксперт и хорошо знаешь марки и модели машин. 
Возьми из текста необходимую информацию и преобразуй его в вид: (
    1. Марка машины: (сохраняй точное написание, например: Mercedes-Benz, BMW, Audi)
    2. Модель: (указывай полное название модели, включая все буквы и цифры, например: X3 30i, M5 Competition и т.д.)  
    3. VIN-код: (указывай только цифры и буквы, без пробелов)
    4. Пробег:  
    5. Год:  
    6. Цена:  
    7. Контакт для связи:  )
Важно:
- Сохраняй точное написание названия марки (например, Mercedes-Benz, а не Mercedes-Benx)
- Сохраняй все буквы и цифры в названии модели (например, X3 30i, а не просто X3)
- Если в тексте есть несколько ссылок, указывай их все
- Если есть несколько контактов, указывай их все
- Если нет нужных данных ставь прочерк (-)
- Не добавляй от себя никакой информации
- Не меняй формат вывода"""

# Проверка обязательных переменных окружения
required_env_vars = [
    'SBER_API_URL',
    'SBER_AUTH_URL',
    'SBER_CLIENT_ID',
    'SBER_CLIENT_SECRET',
    'SAVE_DIR'
]

missing_vars = [var for var in required_env_vars if not os.getenv(var)]
if missing_vars:
    raise ValueError(f"Отсутствуют обязательные переменные окружения: {', '.join(missing_vars)}") 