import os
import time
import re
import requests
from playwright.sync_api import sync_playwright
from datetime import datetime

# --- КОНФИГУРАЦИЯ ---

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

# Проверка ключей
if not TELEGRAM_BOT_TOKEN or not TELEGRAM_CHANNEL_ID:
    print("⚠️ Внимание: Ключи Telegram не найдены. Сообщения не будут отправлены.")

# Словари для Onlinetours (нужны их названия для URL)
# Ключ: Наше название -> Значение: slug в URL onlinetours
# Пример: https://www.onlinetours.ru/tours/turkey
COUNTRIES = {
    "Турция": "turkey",
    "Египет": "egypt",
    "ОАЭ": "united-arab-emirates",
    "Таиланд": "thailand",
    "Куба": "cuba"
}

# Города вылета (Onlinetours понимает по-русски или по ID, пробуем названия)
DEPARTURE_CITIES = [
    "Москва",
    "Санкт-Петербург"
    # Пока ограничим список, чтобы скрипт успел отработать на бесплатном GitHub
]

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"Ошибка телеграма: {e}")

def get_cheapest_tour(page, country_slug, departure_city):
    """
    Заходит на страницу, фильтрует и ищет цену.
    """
    # Формируем URL. Пример: https://www.onlinetours.ru/tours/turkey?start_from=Москва
    # Onlinetours умный, он обычно подхватывает start_from=Название
    url = f"https://www.onlinetours.ru/tours/{country_slug}?start_from={departure_city}"
    
    print(f"   🌐 Переход: {url}")
    
    try:
        page.goto(url, timeout=60000) # Даем 60 сек на загрузку
        
        # Ждем появления ценников (селектор может меняться, ищем класс цены)
        # Обычно цена лежит в блоке, содержащем '₽'
        # Ждем 10 секунд полной прогрузки JS
        page.wait_for_timeout(5000) 
        
        # Скроллим вниз, чтобы подгрузились туры (lazy load)
        page.mouse.wheel(0, 1000)
        page.wait_for_timeout(3000)

        # Пытаемся найти элементы с ценой. 
        # На Onlinetours цены часто имеют класс .price-box__price или похожий
        # Мы будем искать текст, содержащий "₽" и чистить его
        
        # Ищем все элементы, похожие на цену тура
        price_elements = page.locator("span:text-matches('^[0-9 ]+₽$')").all()
        
        if not price_elements:
            # Запасной вариант селектора (специфичный для Onlinetours)
            price_elements = page.locator(".tour-preview-price").all()

        min_price = 1000000
        found_link = url
        
        print(f"   🔎 Найдено ценников на странице: {len(price_elements)}")

        for el in price_elements[:5]: # Проверяем первые 5
            text = el.inner_text()
            # Чистим текст: "45 000 ₽" -> 45000
            clean_price = re.sub(r'[^0-9]', '', text)
            if clean_price:
                price = int(clean_price)
                if price < min_price and price > 5000: # Фильтр от багов (0 руб)
                    min_price = price
        
        if min_price < 1000000:
            return min_price, found_link
        
    except Exception as e:
        print(f"   ❌ Ошибка парсинга {country_slug}: {e}")
    
    return None, None

def main():
    print(f"🚀 Запуск браузера Playwright: {datetime.now()}")
    
    with sync_playwright() as p:
        # Запускаем браузер (headless=True для сервера)
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
        )
        page = context.new_page()

        for city in DEPARTURE_CITIES:
            for country_name, country_slug in COUNTRIES.items():
                print(f"🔍 Ищем: {city} -> {country_name}...")
                
                price, link = get_cheapest_tour(page, country_slug, city)
                
                if price:
                    print(f"   ✅ Найдена цена: {price}")
                    
                    # Логика отправки: отправляем, если цена "вкусная" (тут пока просто отправляем всё для теста)
                    msg = (
                        f"🔥 <b>Найдено на Onlinetours!</b>\n"
                        f"✈️ {city} -> {country_name}\n"
                        f"💰 <b>от {price:,} руб.</b>\n"
                        f"🔗 <a href='{link}'>Смотреть туры</a>"
                    )
                    send_telegram_message(msg)
                else:
                    print("   ⚠️ Цены не найдены.")
                
                # Пауза между запросами
                time.sleep(3)

        browser.close()

if __name__ == "__main__":
    main()
