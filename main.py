import os
import time
import re
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright
from supabase import create_client, Client

# --- НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = os.getenv('TG_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TG_CHAT_ID')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

CITIES_FROM = ["Москва", "Санкт-Петербург", "Екатеринбург", "Казань", "Новосибирск", "Сочи", "Уфа", "Самара"]
COUNTRIES_TO = ["Турция", "Египет", "ОАЭ", "Таиланд", "Куба", "Мальдивы", "Шри-Ланка"]

# Инициализация БД
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY and "http" in SUPABASE_URL:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"❌ Ошибка Supabase: {e}")

# --- ФУНКЦИИ ---

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except: pass

def get_last_price(city, country):
    # Берем последнюю цену для этого направления (duration ставим 7 как условный дефолт)
    if not supabase: return None
    try:
        response = supabase.table("tour_prices") \
            .select("min_price") \
            .eq("origin_city", city) \
            .eq("destination", country) \
            .eq("duration", 7) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        if response.data: return response.data[0]['min_price']
    except: pass
    return None

def save_price(city, country, price):
    if not supabase: return
    try:
        # Пишем duration = 7, так как это стандартный поиск (7-14 ночей)
        data = {
            "origin_city": city, "destination": country, "duration": 7,
            "min_price": price, "departure_date_found": datetime.now().strftime("%d.%m.%Y")
        }
        supabase.table("tour_prices").insert(data).execute()
        print(f"   💾 Сохранено в БД: {price}")
    except Exception as e:
        print(f"   ❌ Ошибка БД: {e}")

def run_search(page, city, country):
    print(f"🔄 Поиск: {city} -> {country} (Стандарт)")
    
    try:
        # 1. Заходим на главную
        page.goto("https://www.onlinetours.ru/", timeout=60000)
        
        # Сброс фокуса
        try: page.mouse.click(0, 0)
        except: pass

        # --- ШАГ 1: ГОРОД ---
        try:
            # Пытаемся кликнуть на текущий город
            depart_btn = page.locator(".SearchPanel-departCity, .search-panel-depart-city").first
            if depart_btn.is_visible():
                depart_btn.click(force=True)
                # Выбираем новый
                page.get_by_text(city, exact=True).first.click(force=True)
        except: 
            # Если не вышло кликнуть (иногда там просто текст), надеемся что город верный или оставляем как есть
            pass

        # --- ШАГ 2: СТРАНА ---
        dest_input = page.locator("input[placeholder*='Страна'], input[placeholder*='курорт']")
        dest_input.click(force=True)
        dest_input.fill("")
        time.sleep(0.5)
        dest_input.fill(country)
        time.sleep(1.5) # Ждем подсказку
        page.keyboard.press("Enter")
        time.sleep(1)

        # --- ШАГ 3: НОЧЕЙ (ПРОПУСКАЕМ!) ---
        # Оставляем настройки сайта по умолчанию (обычно 7-14)

        # --- ШАГ 4: КАЛЕНДАРЬ ---
        print("   📅 Открываю календарь...")
        date_btn = page.locator(".SearchPanel-date, .search-panel-date").first
        date_btn.click(force=True)
        
        # Ждем твои зеленые ценники
        try:
            page.wait_for_selector(".text-emerald-600", timeout=15000)
        except:
            print("   ⚠️ Ценники не прогрузились.")
            return

        # --- ШАГ 5: СБОР ЦЕН ---
        prices_elements = page.locator(".text-emerald-600").all_inner_texts()
        
        valid_prices = []
        for p in prices_elements:
            clean = re.sub(r'[^0-9]', '', p)
            if clean:
                val = int(clean)
                if val > 10000: valid_prices.append(val)
        
        if not valid_prices:
            print("   ⚠️ Цены не найдены.")
            return

        min_price = min(valid_prices)
        print(f"   ✅ НАЙДЕНО: {min_price} руб.")

        # --- ШАГ 6: ЛОГИКА ---
        last_price = get_last_price(city, country)
        save_price(city, country, min_price)
        current_url = page.url
        
        if last_price:
            if min_price < last_price:
                diff = last_price - min_price
                msg = (
                    f"📉 <b>ЦЕНА УПАЛА!</b>\n"
                    f"✈️ {city} -> {country}\n"
                    f"💰 <b>{min_price:,} руб.</b> (было {last_price:,})\n"
                    f"📉 Скидка: {diff} руб.\n"
                    f"🔗 <a href='{current_url}'>Проверить на сайте</a>"
                )
                send_telegram_message(msg)
        else:
            # Первое обнаружение
            msg = (
                f"🆕 <b>Найдена цена</b>\n"
                f"✈️ {city} -> {country}\n"
                f"💰 <b>{min_price:,} руб.</b>\n"
                f"🔗 <a href='{current_url}'>Проверить на сайте</a>"
            )
            send_telegram_message(msg)

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")

def main():
    print(f"🚀 VOLAGO FAST BOT: {datetime.now()}")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-setuid-sandbox']
        )
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = context.new_page()

        for city in CITIES_FROM:
            for country in COUNTRIES_TO:
                run_search(page, city, country)
                time.sleep(2) # Пауза чтобы не забанили

        browser.close()

if __name__ == "__main__":
    main()
