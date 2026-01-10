import os
import time
import re
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright

# --- НАСТРОЙКИ ---

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

# Города вылета (текст должен точно совпадать с тем, что в меню Onlinetours)
CITIES_FROM = ["Москва", "Санкт-Петербург"] 

# Куда летим
COUNTRIES_TO = ["Турция", "Египет", "ОАЭ", "Таиланд"]

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN:
        print("⚠️ Токен телеграма не задан, сообщение не отправлено.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")

def check_prices_on_homepage(page, city_from, country_to):
    print(f"🔄 Проверка: {city_from} -> {country_to}")
    
    try:
        # 1. Заходим на главную
        page.goto("https://www.onlinetours.ru/", timeout=60000)
        
        # Ждем загрузки основного поиска
        # Ищем поле "Откуда" (обычно там написано "Москва" или другой город)
        page.wait_for_selector(".SearchPanel-departCity", state="visible", timeout=15000)

        # --- ШАГ 1: ВЫБОР ГОРОДА ВЫЛЕТА ---
        depart_btn = page.locator(".SearchPanel-departCity")
        current_city = depart_btn.inner_text().strip()
        
        if city_from not in current_city:
            print(f"   📍 Меняю город с {current_city} на {city_from}")
            depart_btn.click()
            # Ждем появления списка городов
            page.wait_for_selector(".DepartCityPicker-item", state="visible")
            # Кликаем на нужный город по тексту
            page.get_by_text(city_from, exact=True).first.click()
            time.sleep(1) # Даем интерфейсу продуматься

        # --- ШАГ 2: ВЫБОР "КУДА" ---
        # Кликаем в поле ввода направления
        dest_input = page.locator("input[placeholder='Страна, курорт или отель']")
        dest_input.click()
        # Очищаем и пишем страну
        dest_input.fill("")
        time.sleep(0.5)
        dest_input.type(country_to, delay=100) # Печатаем по буквам, как человек
        
        # Ждем подсказок (Suggest)
        page.wait_for_selector(".Suggest-group", state="visible", timeout=5000)
        time.sleep(1)
        # Жмем Enter, чтобы выбрать первый вариант (обычно это сама страна)
        page.keyboard.press("Enter")
        
        # --- ШАГ 3: ОТКРЫТИЕ КАЛЕНДАРЯ И ПОИСК ЦЕН ---
        print("   📅 Открываю календарь...")
        # Кликаем на поле даты
        page.locator(".SearchPanel-date").click()
        
        # Ждем появления цен в календаре. 
        # У Onlinetours цены в календаре появляются не сразу, крутится лоадер.
        # Ищем элементы с ценой (обычно класс содержит 'price' или просто текст с '₽')
        
        # Даем 10 секунд на прогрузку цен в ячейках
        page.wait_for_timeout(4000) 
        
        # Собираем цены. В календаре Onlinetours цена обычно внутри <div class="Day-price">
        # Но классы могут меняться, попробуем универсальный селектор по тексту
        prices_text = page.locator("div[class*='price']").all_inner_texts()
        
        # Фильтруем мусор, оставляем только цифры
        valid_prices = []
        for p in prices_text:
            clean = re.sub(r'[^0-9]', '', p)
            if clean:
                val = int(clean)
                if val > 5000: # Отсекаем явно ошибочные мелкие цифры
                    valid_prices.append(val)
        
        if valid_prices:
            min_price = min(valid_prices)
            print(f"   ✅ Найдена минимальная цена: {min_price} руб.")
            return min_price
        else:
            print("   ⚠️ Цены в календаре не прогрузились.")
            return None

    except Exception as e:
        print(f"   ❌ Ошибка в процессе: {e}")
        # Делаем скриншот ошибки для отладки (сохранится в GitHub Actions Artifacts, если настроить, но пока просто чтобы скрипт не падал)
        return None

def main():
    print(f"🚀 Запуск Smart-парсера Onlinetours: {datetime.now()}")
    
    with sync_playwright() as p:
        # Запуск браузера
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            viewport={'width': 1920, 'height': 1080}, # Притворяемся большим монитором
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/110.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        for city in CITIES_FROM:
            for country in COUNTRIES_TO:
                
                price = check_prices_on_homepage(page, city, country)
                
                if price:
                    msg = (
                        f"🔥 <b>Onlinetours (Календарь):</b>\n"
                        f"✈️ {city} -> {country}\n"
                        f"💰 <b>от {price:,} руб.</b>\n"
                        f"📅 Цена найдена в календаре низких цен."
                    )
                    send_telegram_message(msg)
                
                # Пауза, чтобы не забанили и сайт "отдохнул"
                time.sleep(3) 

        browser.close()

if __name__ == "__main__":
    main()
