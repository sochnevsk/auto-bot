import json
import logging
from datetime import datetime, date, timedelta
from typing import Dict, List
from pathlib import Path

from config.settings import (
    MONTHLY_TOKEN_LIMIT,
    DAILY_TOKEN_LIMIT,
    WARNING_THRESHOLD,
    CRITICAL_THRESHOLD,
    TOKEN_STATS_FILE
)

class TokenUsageTracker:
    def __init__(self):
        self.stats = self._load_stats()
        self._check_monthly_reset()
    
    def _load_stats(self) -> Dict:
        """Загружает статистику использования токенов из файла."""
        if TOKEN_STATS_FILE.exists():
            try:
                with open(TOKEN_STATS_FILE, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                logging.error(f"Ошибка при чтении файла статистики: {e}")
        
        return {
            'monthly_tokens': 0,
            'daily_tokens': 0,
            'last_reset_date': date.today().isoformat(),
            'monthly_reset_date': date.today().replace(day=1).isoformat(),
            'usage_history': []
        }
    
    def _save_stats(self) -> None:
        """Сохраняет статистику использования токенов в файл."""
        try:
            with open(TOKEN_STATS_FILE, 'w', encoding='utf-8') as f:
                json.dump(self.stats, f, indent=2)
        except Exception as e:
            logging.error(f"Ошибка при сохранении файла статистики: {e}")
    
    def _check_monthly_reset(self) -> None:
        """Проверяет и сбрасывает месячный счетчик при необходимости."""
        today = date.today()
        monthly_reset = date.fromisoformat(self.stats['monthly_reset_date'])
        
        if today.month != monthly_reset.month or today.year != monthly_reset.year:
            self.stats['monthly_tokens'] = 0
            self.stats['monthly_reset_date'] = today.replace(day=1).isoformat()
            self._save_stats()
    
    def _check_daily_reset(self) -> None:
        """Проверяет и сбрасывает дневной счетчик при необходимости."""
        today = date.today()
        last_reset = date.fromisoformat(self.stats['last_reset_date'])
        
        if today != last_reset:
            self.stats['daily_tokens'] = 0
            self.stats['last_reset_date'] = today.isoformat()
            self._save_stats()
    
    def add_usage(self, tokens: int, request_type: str) -> None:
        """Добавляет информацию об использовании токенов."""
        self._check_daily_reset()
        
        # Обновляем счетчики
        self.stats['monthly_tokens'] += tokens
        self.stats['daily_tokens'] += tokens
        
        # Добавляем запись в историю
        self.stats['usage_history'].append({
            'timestamp': datetime.now().isoformat(),
            'tokens': tokens,
            'type': request_type
        })
        
        # Ограничиваем историю последними 1000 записей
        if len(self.stats['usage_history']) > 1000:
            self.stats['usage_history'] = self.stats['usage_history'][-1000:]
        
        self._save_stats()
        self._check_limits()
    
    def _check_limits(self) -> None:
        """Проверяет лимиты и выводит предупреждения."""
        monthly_percent = (self.stats['monthly_tokens'] / MONTHLY_TOKEN_LIMIT) * 100
        daily_percent = (self.stats['daily_tokens'] / DAILY_TOKEN_LIMIT) * 100
        
        # Проверка месячного лимита
        if monthly_percent >= CRITICAL_THRESHOLD:
            logging.warning(f"⚠️ КРИТИЧЕСКОЕ ПРЕДУПРЕЖДЕНИЕ: Достигнут {monthly_percent:.1f}% месячного лимита токенов!")
        elif monthly_percent >= WARNING_THRESHOLD:
            logging.warning(f"⚠️ Предупреждение: Достигнут {monthly_percent:.1f}% месячного лимита токенов")
        
        # Проверка дневного лимита
        if daily_percent >= CRITICAL_THRESHOLD:
            logging.warning(f"⚠️ КРИТИЧЕСКОЕ ПРЕДУПРЕЖДЕНИЕ: Достигнут {daily_percent:.1f}% дневного лимита токенов!")
        elif daily_percent >= WARNING_THRESHOLD:
            logging.warning(f"⚠️ Предупреждение: Достигнут {daily_percent:.1f}% дневного лимита токенов")
    
    def get_usage_stats(self) -> Dict:
        """Возвращает текущую статистику использования токенов."""
        return {
            'monthly': {
                'used': self.stats['monthly_tokens'],
                'limit': MONTHLY_TOKEN_LIMIT,
                'remaining': MONTHLY_TOKEN_LIMIT - self.stats['monthly_tokens'],
                'percent': (self.stats['monthly_tokens'] / MONTHLY_TOKEN_LIMIT) * 100
            },
            'daily': {
                'used': self.stats['daily_tokens'],
                'limit': DAILY_TOKEN_LIMIT,
                'remaining': DAILY_TOKEN_LIMIT - self.stats['daily_tokens'],
                'percent': (self.stats['daily_tokens'] / DAILY_TOKEN_LIMIT) * 100
            }
        }
    
    def get_usage_history(self, days: int = 7) -> List[Dict]:
        """Возвращает историю использования токенов за последние N дней."""
        cutoff_date = datetime.now() - timedelta(days=days)
        return [
            entry for entry in self.stats['usage_history']
            if datetime.fromisoformat(entry['timestamp']) > cutoff_date
        ] 