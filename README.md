# Auto Bot Sber

Бот для форматирования текстов автомобильных объявлений с использованием Sber GigaChat API.

## Структура проекта

```
auto-bot-sber/
├── src/
│   ├── bot/
│   │   └── formatter.py
│   └── utils/
│       ├── api.py
│       └── token_tracker.py
├── config/
│   └── settings.py
├── logs/
├── tests/
├── .env.example
├── requirements.txt
└── README.md
```

## Установка

1. Клонируйте репозиторий:
```bash
git clone <repository-url>
cd auto-bot-sber
```

2. Создайте виртуальное окружение и активируйте его:
```bash
python -m venv venv
source venv/bin/activate  # для Linux/Mac
# или
venv\Scripts\activate  # для Windows
```

3. Установите зависимости:
```bash
pip install -r requirements.txt
```

4. Создайте файл .env на основе .env.example и заполните его своими данными:
```bash
cp .env.example .env
```

## Использование

1. Убедитесь, что у вас есть доступ к Sber GigaChat API и необходимые учетные данные.

2. Запустите скрипт:
```bash
python src/bot/formatter.py
```

## Функциональность

- Форматирование текстов автомобильных объявлений
- Отслеживание использования токенов
- Автоматическое сброс счетчиков токенов
- Логирование всех операций

## Лимиты токенов

- Месячный лимит: 100,000 токенов
- Дневной лимит: 10,000 токенов
- Лимит на один запрос: 2,000 токенов

## Логирование

Логи сохраняются в директории `logs/` в файле `formatter.log`.
