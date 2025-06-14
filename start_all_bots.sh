#!/bin/bash
set -e
echo "Запуск Sber бота..."
cd /var/www/u3143422/data/auto_bot/auto-bot-sber
mkdir -p ../logs
source venv_sber/bin/activate
nohup python3 run_formatter.py > ../logs/sber.log 2>&1 &
deactivate || true
echo "Запуск Producer бота..."
cd /var/www/u3143422/data/auto_bot/auto-bot-producer
mkdir -p ../logs
source venv_producer/bin/activate
nohup python3 run.py > ../logs/producer.log 2>&1 &
deactivate || true
echo "Запуск Userbot..."
cd /var/www/u3143422/data/auto_bot/auto-bot-userbot
mkdir -p ../logs
source venv_userbot/bin/activate
nohup python3 bot.py > ../logs/userbot.log 2>&1 &
deactivate || true
echo "Все боты запущены" 