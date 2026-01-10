import os
import time
import re
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright

# --- НАСТРОЙКИ ---

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')

CITIES_FROM = ["Москва"] # Пока оставим один город для теста
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
        
        # ДИАГНОСТИКА: Что видит робот?
        page_title = page.title()
        print(f"   👀 Заголовок страницы: '{page_title}'")
        
        # Если нас забанили, заголовок обычно странный
        if "Just a moment" in page_title or "Access denied" in page_title:
            print("   ⛔️ НАС ЗАБЛОКИРОВАЛИ (Cloudflare/Anti-bot).")
            return None

        # Ждем загрузки любого текста, похожего на интерфейс
        # Ждем поле "Куда" (оно есть всегда)
        try:
            # Ищем input с placeholder "Страна, курорт или отель"
            page.wait_for_selector("input[placeholder*='Страна']", timeout=10000)
        except:
            print("   ⚠️ Не вижу поле поиска. Возможно, мобильная версия или другая верстка.")
            # Делаем скриншот ошибки (виртуально, чтобы понимать логику)
            return None

        # --- ШАГ 1: ВВОДИМ "КУДА" (Это надежнее, чем менять город) ---
        # Сразу кликаем в поле назначения
        dest_input = page.locator("input[placeholder*='Страна']")
        dest_input.click()
        dest_input.fill(country_to)
        time.sleep(1)
        
        # Ждем подсказку и жмем Enter
        page.keyboard.press("Enter")
        time.sleep(1)

        # --- ШАГ 2: ОТКРЫВАЕМ КАЛЕНДАРЬ ---
        # Вместо поиска по классу, ищем по иконке календаря или тексту даты
        # Часто там написано "Дата вылета" или текущая дата.
        # Попробуем кликнуть на блок, который идет ПОСЛЕ поля "Куда".
        
        # Попробуем найти элемент, содержащий цифры (дату) или слово "вылета"
        # Универсальный хак: жмем Tab, пока не попадем на дату? Нет, сложно.
        
        # Попробуем найти календарь по селектору Onlinetours (они редко меняют структуру поиска)
        # Блок с датой обычно имеет класс SearchPanel-date
        try:
            page.locator(".SearchPanel-date").click()
        except:
            print("   ⚠️ Не удалось кликнуть на дату. Пробую альтернативный клик.")
            # Клик по координатам (грубо, но может сработать, если верстка на месте)
            page.mouse.click(500, 300) 

        # --- ШАГ 3: ЧИТАЕМ ЦЕНЫ ---
        print("   📅 Жду цены в календаре...")
        time.sleep(5) # Даем время на подгрузку AJAX
        
        # Ищем любые элементы, похожие на цену (40 000 ₽)
        # Ищем текст, содержащий знак рубля
        prices_text = page.locator("body").inner_text()
        
        # Ищем все вхождения "число + ₽" в тексте страницы
        # Это "грязный" метод, но он работает, даже если классы сменились
        found_prices = re.findall(r'(\d[\d\s]*)\s?₽', prices_text)
        
        clean_prices = []
        for p in found_prices:
            clean = int(re.sub(r'\s+', '', p))
            if clean > 10000 and clean < 500000: # Разумные рамки
                clean_prices.append(clean)
        
        if clean_prices:
            min_price = min(clean_prices)
            print(f"   ✅ Нашел цены: {clean_prices[:3]}... Мин: {min_price}")
            return min_price
        else:
            print("   ⚠️ Ценники с знаком '₽' не найдены.")
            return None

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return None

def main():
    print(f"🚀 Запуск STEALTH-парсера Onlinetours: {datetime.now()}")
    
    with sync_playwright() as p:
        # ЗАПУСК С ХИТРОСТЯМИ (Чтобы не палиться)
        browser = p.chromium.launch(
            headless=True,
            args=[
                '--disable-blink-features=AutomationControlled', # Скрываем, что мы робот
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
        
        # Добавляем скрипт, чтобы скрыть navigator.webdriver (главный палевый флаг)
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
                        f"🔥 <b>Onlinetours (Stealth):</b>\n"
                        f"✈️ {city} -> {country}\n"
                        f"💰 <b>от {price:,} руб.</b>\n"
                    )
                    send_telegram_message(msg)
                
                time.sleep(5) 

        browser.close()

if __name__ == "__main__":
    main()
