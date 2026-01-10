import os
import time
import re
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright

# --- НАСТРОЙКИ ---

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

CITIES_FROM = ["Москва"] 
# Пока пробуем Турцию и Египет, чтобы проверить стабильность
COUNTRIES_TO = ["Турция", "Египет"]

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")

def check_prices_smart(page, city_from, country_to):
    print(f"🔄 Проверка: {city_from} -> {country_to}")
    
    try:
        # 1. Заходим на главную
        page.goto("https://www.onlinetours.ru/", timeout=60000)
        
        # ДИАГНОСТИКА
        print(f"   👀 Заголовок: '{page.title()}'")
        
        # Ждем поле поиска
        try:
            # Ищем input с placeholder, содержащим "Страна"
            # state="attached" значит "существует в коде", даже если скрыт
            page.wait_for_selector("input[placeholder*='Страна']", state="attached", timeout=15000)
        except:
            print("   ⚠️ Не нашел поле поиска за 15 сек.")
            return None

        # --- ШАГ 1: ВВОДИМ "КУДА" ---
        dest_input = page.locator("input[placeholder*='Страна']")
        
        # МАГИЯ ЗДЕСЬ: force=True пробивает любые перекрытия
        dest_input.click(force=True)
        
        # Очищаем поле на всякий случай
        dest_input.fill("")
        time.sleep(0.5)
        # Печатаем страну
        dest_input.type(country_to, delay=100)
        time.sleep(2) # Ждем пока всплывет подсказка
        
        # Жмем Enter
        page.keyboard.press("Enter")
        time.sleep(1)

        # --- ШАГ 2: КЛИКАЕМ НА ДАТУ/КАЛЕНДАРЬ ---
        print("   📅 Пытаюсь открыть календарь...")
        
        # Пробуем разные варианты клика по дате, так как там часто сложная верстка
        # Вариант А: По классу
        try:
            page.locator(".SearchPanel-date").click(force=True, timeout=2000)
        except:
            # Вариант Б: Если не вышло, ищем элемент с текстом даты (обычно там сегодняшнее число или месяц)
            # Просто кликаем по координатам правее поля ввода страны (грубый хак)
            print("   ⚠️ Клик по классу не прошел, пробую по координатам...")
            box = dest_input.bounding_box()
            if box:
                # Кликаем на 300 пикселей правее поля ввода страны (там обычно дата)
                page.mouse.click(box['x'] + box['width'] + 50, box['y'] + 10)
        
        time.sleep(3) # Ждем открытия календаря

        # --- ШАГ 3: ЧИТАЕМ ЦЕНЫ ---
        # Сначала проверим, открылся ли календарь. Ищем элемент с ценой (содержит ₽)
        
        content = page.content() # Берем весь HTML
        # Ищем цены регуляркой прямо в HTML, чтобы не зависеть от скрытых элементов
        # Ищем паттерн: >45 000 ₽< или похожие
        
        # Ищем все цифры перед знаком рубля
        found_prices = re.findall(r'(\d[\d\s]*)\s?₽', content)
        
        valid_prices = []
        for p in found_prices:
            # Удаляем пробелы
            clean = int(re.sub(r'\s+', '', p))
            # Фильтр адекватности (цена тура не может быть 500 рублей и вряд ли 5 млн для теста)
            if clean > 10000 and clean < 800000:
                valid_prices.append(clean)
        
        if valid_prices:
            min_price = min(valid_prices)
            print(f"   ✅ Нашел цены: {len(valid_prices)} шт. Мин: {min_price}")
            return min_price
        else:
            print(f"   ⚠️ Цены не найдены. Найдено сырых совпадений: {len(found_prices)}")
            # Если не нашли, выведем кусок текста для отладки
            return None

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return None

def main():
    print(f"🚀 Запуск STEALTH-парсера Onlinetours (FORCE MODE): {datetime.now()}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled',
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--disable-accelerated-2d-canvas',
                '--no-first-run',
                '--no-zygote',
                '--single-process',
                '--disable-gpu'
            ]
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080},
            locale='ru-RU',
            timezone_id='Europe/Moscow'
        )
        
        # Скрипт-невидимка
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        page = context.new_page()

        for city in CITIES_FROM:
            for country in COUNTRIES_TO:
                price = check_prices_smart(page, city, country)
                
                if price:
                    msg = (
                        f"🔥 <b>Onlinetours (Найден тур):</b>\n"
                        f"✈️ {city} -> {country}\n"
                        f"💰 <b>от {price:,} руб.</b>\n"
                        f"📅 Проверьте сайт, цена из календаря!"
                    )
                    send_telegram_message(msg)
                
                time.sleep(5) 

        browser.close()

if __name__ == "__main__":
    main()
