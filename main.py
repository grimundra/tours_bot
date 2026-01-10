import os
import requests
import time
from datetime import datetime

# --- КОНФИГУРАЦИЯ И СЕКРЕТЫ ---

# Получаем ключи из переменных окружения (GitHub Secrets)
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
PARTNER_API_KEY = os.getenv('PARTNER_API_KEY') # Если используется API партнерки (например, Travelata/Level.Travel)

# Проверка наличия ключей (чтобы не упало тихо)
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
    raise ValueError("❌ Ошибка: Не найдены секретные ключи (TELEGRAM_BOT_TOKEN или TELEGRAM_CHANNEL_ID)")

# --- НАСТРОЙКИ ПОИСКА ---

# Города вылета (Код IATA : Название)
DEPARTURE_CITIES = {
    "MOW": "Москва",
    "LED": "Санкт-Петербург",
    "SVX": "Екатеринбург",
    "KZN": "Казань",
    "OVB": "Новосибирск",
    "AER": "Сочи",
    "UFA": "Уфа",
    "KUF": "Самара"
}

# Страны / Направления назначения
DESTINATIONS = [
    "Турция",
    "Египет",
    "ОАЭ",
    "Таиланд",
    "Шри-Ланка",
    "Россия",     # Можно уточнить (Сочи, Калининград)
    "Абхазия",
    "Куба",
    "Мальдивы"
]

# --- ЛОГИКА ---

def search_tours(departure_code, destination_name):
    """
    Имитация или реальный запрос к API поиска туров.
    Здесь должна быть логика запроса к сайту-донору или API.
    """
    print(f"🔍 Ищу туры: {DEPARTURE_CITIES[departure_code]} -> {destination_name}...")
    
    # ПРИМЕР: Здесь ты подставишь реальный URL и параметры
    # params = {
    #     'from': departure_code,
    #     'to': destination_name,
    #     'key': PARTNER_API_KEY
    # }
    # response = requests.get('URL_ПАРТНЕРКИ', params=params)
    # return response.json()
    
    return [] # Пока возвращаем пустой список

def send_telegram_message(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHANNEL_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    try:
        response = requests.post(url, json=payload)
        if response.status_code != 200:
            print(f"Ошибка отправки в Telegram: {response.text}")
    except Exception as e:
        print(f"Сбой сети: {e}")

def main():
    print(f"🚀 Запуск парсера VOLAGO: {datetime.now()}")
    
    # Перебираем все комбинации городов и стран
    for dep_code, dep_name in DEPARTURE_CITIES.items():
        for dest in DESTINATIONS:
            
            # 1. Поиск
            deals = search_tours(dep_code, dest)
            
            # 2. Обработка найденного (пример)
            if deals:
                for deal in deals:
                    # Тут формируем сообщение
                    msg = f"🔥 <b>Найдена находка!</b>\n\n✈️ {dep_name} -> {dest}\n💰 Цена: {deal['price']} руб."
                    send_telegram_message(msg)
                    time.sleep(2) # Пауза, чтобы не спамить в API телеграма
            
            # Небольшая пауза между запросами к источнику, чтобы не забанили IP
            time.sleep(1) 

if __name__ == "__main__":
    main()
