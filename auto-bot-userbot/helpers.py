import re
import logging

def clean_text_for_open(text: str) -> str:
    """
    Очищает текст для публикации в открытом канале (удаляет контакты, ссылки и т.д.).
    """
    # Расширенный список ключевых слов для контактов
    contact_keywords = [
        'тел', 'телефон', 'тлф', 'моб', 'mobile', 'phone', 'номер', 'контакт', 'контакты',
        'whatsapp', 'ватсап', 'вацап', 'viber', 'вайбер', 'signal', 'сигнал', 'tg', 'тг',
        'telegram', 'телега', 'direct', 'директ', 'личка', 'лс', 'личные сообщения', 'dm',
        'email', 'почта', 'mail', 'e-mail', 'gmail', 'yandex', 'mail.ru', 'bk.ru', 'inbox.ru',
        'outlook', 'icloud', 'protonmail', 'mailbox', 'mailcom', 'mail com', 'mail com',
        'call', 'звонить', 'звонок', 'write', 'писать', 'write me', 'contact me', 'message me',
        'write to', 'message to', 'contact to', 'связаться', 'связь', 'обращаться', 'обращайтесь',
        'нажми', 'клик', 'click', 'press', 'ссылка', 'link', 'профиль', 'profile'
    ]
    
    # Эмодзи, связанные с контактами
    contact_emojis = [
        '📞', '☎️', '📱', '✆', '📲', '📧', '✉️', '📩', '📤', '📥', '🖂', '🖃', '🖄', '🖅', '🖆', '🖇', '🖈', '🖉', '🖊', '🖋', '🖌', '🖍', '🖎', '🖏', '🖐', '🖑', '🖒', '🖓', '🖔', '🖕', '🖖', '🖗', '🖘', '🖙', '🖚', '🖛', '🖜', '🖝', '🖞', '🖟', '🖠', '🖡', '🖢', '🖣', '🖤', '🖥', '🖦', '🖧', '🖨', '🖩', '🖪', '🖫', '🖬', '🖭', '🖮', '🖯', '🖰', '🖱', '🖲', '🖳', '🖴', '🖵', '🖶', '🖷', '🖸', '🖹', '🖺', '🖻', '🖼', '🖽', '🖾', '🖿', '🗀', '🗁', '🗂', '🗃', '🗄', '🗑', '🗒', '🗓', '🗔', '🗕', '🗖', '🗗', '🗘', '🗙', '🗚', '🗛', '🗜', '🗝', '🗞', '🗟', '🗠', '🗡', '🗢', '🗣', '🗤', '🗥', '🗦', '🗧', '🗨', '🗩', '🗪', '🗫', '🗬', '🗭', '🗮', '🗯', '🗰', '🗱', '🗲', '🗳', '🗴', '🗵', '🗶', '🗷', '🗸', '🗹', '🗺', '🗻', '🗼', '🗽', '🗾', '🗿'
    ]
    
    # Телефоны в различных форматах
    phone_patterns = [
        # Российские номера с именами
        r'(?:\+7|8)[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{2}[\s\-\(\)]*\d{2}\s*[-–—]?\s*[а-яА-Яa-zA-Z\s]+',  # +7(921)123-45-67 - Иван
        r'(?:\+7|8)[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{2}[\s\-\(\)]*\d{2}',  # +7(921)123-45-67
        r'8[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{2}[\s\-\(\)]*\d{2}',  # 89211234567
        r'\+7[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{2}[\s\-\(\)]*\d{2}',  # +79211234567
        
        # Номера с дефисами
        r'\+?\d{1,3}[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{2}[\s\-\(\)]*\d{2}\s*[-–—]?\s*[а-яА-Яa-zA-Z\s]+',  # +7921-223-44-42 - Николай
        r'\+?\d{1,3}[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{2}[\s\-\(\)]*\d{2}',  # +7921-223-44-42
        
        # Номера с эмодзи
        r'[📞☎️📱✆📲]?\s*(?:\+7|8)[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{2}[\s\-\(\)]*\d{2}',  # ☎️+79211234567
        r'[📞☎️📱✆📲]?\s*(?:\+7|8)[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{3}[\s\-\(\)]*\d{2}[\s\-\(\)]*\d{2}\s*[-–—]?\s*[а-яА-Яa-zA-Z\s]+',  # ☎️+79211234567 - Иван
    ]
    
    # Email адреса
    email_patterns = [
        r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+',  # Стандартные email
        r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+(?:\s*[-–—]\s*[а-яА-Яa-zA-Z\s]+)?',  # Email с именами
    ]
    
    # Username и ссылки
    username_patterns = [
        r'@[a-zA-Z0-9_]{5,32}',  # Telegram usernames
        r'(?:https?://)?(?:www\.)?(?:t\.me|telegram\.me)/[a-zA-Z0-9_]{5,32}',  # Telegram links
        r'(?:https?://)?(?:www\.)?(?:wa\.me|whatsapp\.com)/[0-9]{10,15}',  # WhatsApp links
        r'(?:https?://)?(?:www\.)?(?:instagram\.com|instagr\.am)/[a-zA-Z0-9_\.]{1,30}',  # Instagram
        r'(?:https?://)?(?:www\.)?(?:facebook\.com|fb\.com)/[a-zA-Z0-9\.]{5,50}',  # Facebook
        r'(?:https?://)?(?:www\.)?(?:vk\.com|vk\.ru)/[a-zA-Z0-9_\.]{1,32}',  # VK
    ]
    
    # URL и ссылки
    url_patterns = [
        # Сначала удаляем все Markdown ссылки (включая текст в квадратных скобках)
        r'\[[^\]]*\]\([^)]*\)',  # Любые Markdown ссылки
        # Затем удаляем оставшиеся URL
        r'https?://[^\s\)]+',  # Direct URLs
        r'www\.[^\s\)]+',  # URLs without protocol
        r'\S+\.(ru|com|net|org|info|biz|io|me|su|ua|by|kz|uz|pl|cz|de|fr|es|it|co|us|uk|site|store|shop|pro|online|top|xyz|club|app|dev|ai|cloud|digital|media|news|tv|fm|am|ca|jp|kr|cn|in|tr|ir|il|gr|fi|se|no|dk|ee|lv|lt|sk|hu|ro|bg|rs|hr|si|mk|al|ge|az|md|kg|tj|tm|mn|vn|th|my|sg|ph|id|au|nz|za|ng|eg|ma|tn|dz|sa|ae|qa|kw|bh|om|ye|jo|lb|sy|iq|pk|af|bd|lk|np|mm|kh|la|bt|mv|bn|tl|pg|sb|vu|fj|ws|to|tv|ck|nu|tk|pw|fm|mh|nr|ki|wf|tf|gl|aq|bv|hm|sj|sh|gs|io|ax|bl|bq|cw|gf|gp|mf|mq|re|yt|pm|tf|wf|eh|ps|ss|sx|tc|vg|vi|um|wf|yt|zm|zw)',  # Various TLDs
    ]
    
    # Добавляем паттерны для защиты важной информации
    year_pattern = re.compile(r'(?<!\d)(?:19|20)\d{2}(?!\d)')  # Годы с 1900 по 2099
    price_pattern = re.compile(r'\d+(?:[.,]\d+)?\s*(?:₽|руб|рублей|т\.р|тыс|тысяч|млн|миллионов)')  # Цены
    model_pattern = re.compile(r'(?i)(?:дизель|бензин|гибрид|электро|авто|модель|комплектация)\s*[а-яА-Яa-zA-Z0-9\s\-]+')  # Модели и комплектации
    vin_pattern = re.compile(r'(?i)(?:VIN\s*(?:код)?\s*)?[A-HJ-NPR-Z0-9]{17}')  # VIN-коды
    
    # Компилируем все регулярные выражения
    patterns = []
    for pattern_list in [phone_patterns, email_patterns, username_patterns, url_patterns]:
        patterns.extend([re.compile(pattern, re.IGNORECASE) for pattern in pattern_list])
    
    # Разбиваем текст на строки
    lines = text.splitlines()
    clean_lines = []
    
    for line in lines:
        # Сохраняем оригинальную строку для сравнения
        original_line = line
        protected_line = line
        
        logging.info(f"\n=== Начало обработки строки ===")
        logging.info(f"Оригинальная строка: {original_line}")
        
        # 1. Сначала находим ВСЕ важные элементы, которые нужно защитить
        # Находим годы
        years = year_pattern.findall(protected_line)
        logging.info(f"Найдены годы: {years}")
        
        # Находим цены
        prices = price_pattern.findall(protected_line)
        logging.info(f"Найдены цены: {prices}")
        
        # Находим модели
        models = model_pattern.findall(protected_line)
        logging.info(f"Найдены модели: {models}")
        
        # Находим VIN-коды
        vins = vin_pattern.findall(protected_line)
        logging.info(f"Найдены VIN: {vins}")
        
        # 2. Защищаем найденные элементы
        # Защищаем годы
        for year in years:
            protected_line = protected_line.replace(year, f"YEAR_{year}_PROTECTED")
            logging.info(f"Защищен год {year}")
            
        # Защищаем цены
        for price in prices:
            protected_line = protected_line.replace(price, f"PRICE_{price}_PROTECTED")
            logging.info(f"Защищена цена {price}")
            
        # Защищаем модели
        for model in models:
            protected_line = protected_line.replace(model, f"MODEL_{model}_PROTECTED")
            logging.info(f"Защищена модель {model}")
            
        # Защищаем VIN-коды
        for vin in vins:
            protected_line = protected_line.replace(vin, f"VIN_{vin}_PROTECTED")
            logging.info(f"Защищен VIN {vin}")
        
        logging.info(f"Строка после защиты: {protected_line}")
        
        # 3. Теперь удаляем все контакты и ссылки
        # Удаляем контактные эмодзи
        for emoji in contact_emojis:
            if emoji in protected_line:
                protected_line = protected_line.replace(emoji, '')
                logging.info(f"Удален эмодзи {emoji}")
        
        # Удаляем все найденные паттерны
        for pattern in patterns:
            # Применяем паттерн несколько раз, пока есть совпадения
            while True:
                new_line = pattern.sub('', protected_line)
                if new_line == protected_line:
                    break
                protected_line = new_line
                logging.info(f"Применен паттерн {pattern.pattern}, результат: {protected_line}")
        
        logging.info(f"Строка после удаления контактов: {protected_line}")
        
        # 4. Восстанавливаем защищенную информацию
        for year in years:
            protected_line = protected_line.replace(f"YEAR_{year}_PROTECTED", year)
            logging.info(f"Восстановлен год {year}")
        for price in prices:
            protected_line = protected_line.replace(f"PRICE_{price}_PROTECTED", price)
            logging.info(f"Восстановлена цена {price}")
        for model in models:
            protected_line = protected_line.replace(f"MODEL_{model}_PROTECTED", model)
            logging.info(f"Восстановлена модель {model}")
        for vin in vins:
            protected_line = protected_line.replace(f"VIN_{vin}_PROTECTED", vin)
            logging.info(f"Восстановлен VIN {vin}")
        
        logging.info(f"Финальная строка: {protected_line}")
        
        # Проверяем, содержит ли строка только контактную информацию
        l = protected_line.lower()
        has_keywords = any(kw in l for kw in contact_keywords)
        has_other_text = any(c.isalnum() for c in l if c not in '0123456789')
        
        # Проверяем, содержит ли строка только цифры и разделители
        only_numbers_and_separators = all(c.isdigit() or c in ' -–—+()' for c in l)
        
        # Проверяем, является ли строка годом
        is_year = bool(year_pattern.match(protected_line.strip()))
        
        # Пропускаем строку только если она содержит ТОЛЬКО контактную информацию
        # и не содержит другого значимого текста, и не является годом
        if (has_keywords or (only_numbers_and_separators and not is_year)) and not has_other_text and protected_line.strip():
            logging.info("Строка пропущена как контактная информация")
            continue
        
        # Всегда добавляем строку, даже если она пустая
        # Это сохраняет структуру текста
        clean_lines.append(protected_line)
        logging.info("Строка добавлена в результат")
    
    # Собираем результат, сохраняя все строки
    result = '\n'.join(clean_lines)
    logging.info(f"\n=== Финальный результат ===\n{result}")
    return result
