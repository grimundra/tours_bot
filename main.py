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

CITIES_FROM = ["Москва", "Санкт-Петербург"]
COUNTRIES_TO = ["Турция", "Египет", "ОАЭ", "Таиланд"] 

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
    if not supabase: return None
    try:
        response = supabase.table("tour_prices") \
            .select("min_price") \
            .eq("origin_city", city) \
            .eq("destination", country) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        if response.data: return response.data[0]['min_price']
    except: pass
    return None

def save_price(city, country, price):
    if not supabase: return
    try:
        data = {
            "origin_city": city, "destination": country, "duration": 7,
            "min_price": price, "departure_date_found": datetime.now().strftime("%d.%m.%Y")
        }
        supabase.table("tour_prices").insert(data).execute()
        print(f"   💾 Saved: {price}")
    except Exception as e:
        print(f"   ❌ DB Error: {e}")

def run_search(page, city, country):
    print(f"🔄 Поиск: {city} -> {country}")
    
    try:
        # 1. Загрузка
        page.goto("https://www.onlinetours.ru/", timeout=60000)
        
        # Сброс фокуса
        try: page.mouse.click(0, 0)
        except: pass

        # --- ШАГ 1: ГОРОД ВЫЛЕТА ---
        try:
            # Проверяем, какой город сейчас стоит
            # Ищем блок с классом departCity или просто текст в шапке поиска
            header_text = page.locator(".SearchPanel-departCity, .search-panel-depart-city").first.inner_text()
            
            if city not in header_text:
                print(f"   🛫 Меняю город на {city}...")
                page.locator(".SearchPanel-departCity, .search-panel-depart-city").first.click()
                
                # Пишем город
                page.keyboard.type(city, delay=100)
                time.sleep(1)
                
                # КЛИКАЕМ ПО ПОДСКАЗКЕ (Важно!)
                # Ищем выпадающий элемент
                page.locator(".Suggest-suggestion").first.click()
                time.sleep(1)
            else:
                print(f"   ✅ Город {city} уже выбран.")

        except Exception as e:
            print(f"   ⚠️ Нюанс с городом: {e}")

        # --- ШАГ 2: СТРАНА (КУДА) ---
        try:
            print(f"   🌴 Ввожу страну: {country}...")
            dest_input = page.locator("input[placeholder*='Страна']")
            dest_input.click(force=True)
            dest_input.fill("") # Очистка
            time.sleep(0.5)
            
            # Печатаем по буквам
            dest_input.type(country, delay=100)
            time.sleep(2) # Ждем выпадения списка
            
            # КЛИКАЕМ ПО ПЕРВОЙ ПОДСКАЗКЕ МЫШКОЙ
            # Это самое главное изменение. Не Enter, а клик.
            suggestion = page.locator(".Suggest-suggestion").first
            if suggestion.is_visible():
                suggestion.click()
                print("      ✅ Кликнул по подсказке.")
            else:
                print("      ⚠️ Подсказка не появилась, жму Enter.")
                page.keyboard.press("Enter")
            
            time.sleep(1)
            
            # Клик в пустоту, чтобы закрыть любые перекрытия
            page.mouse.click(100, 10)
            
        except Exception as e:
            print(f"   ❌ Ошибка ввода страны: {e}")
            return

        # --- ШАГ 3: ОТКРЫТИЕ КАЛЕНДАРЯ ---
        print("   📅 Открываю календарь...")
        
        # Попытка 1: По точному классу (самый частый)
        try:
            page.locator(".SearchPanel-date, .search-panel-date").first.click(force=True)
        except:
            # Попытка 2: Если класс сменили, ищем поле, следующее СРАЗУ за полем страны.
            # Мы не используем большие координаты. Мы берем границу поля страны.
            print("   ⚠️ Класс не найден, пробую кликнуть рядом с полем Страны.")
            box = page.locator("input[placeholder*='Страна']").bounding_box()
            if box:
                # Кликаем всего на 10 пикселей правее конца поля страны.
                # Это гарантированно начало поля "Дата".
                click_x = box['x'] + box['width'] + 10
                click_y = box['y'] + (box['height'] / 2)
                page.mouse.click(click_x, click_y)

        # --- ШАГ 4: ЖДЕМ ЗЕЛЕНЫЕ ЦЕНЫ ---
        print("   ⏳ Жду цены...")
        try:
            # Ждем появления класса .text-emerald-600
            page.wait_for_selector(".text-emerald-600", timeout=15000)
        except:
            print("   ⚠️ Цены не появились.")
            page.screenshot(path=f"debug_{city}_{country}.png")
            return

        # --- ШАГ 5: ПАРСИНГ ---
        prices_elements = page.locator(".text-emerald-600").all_inner_texts()
        
        valid_prices = []
        for p in prices_elements:
            clean = re.sub(r'[^0-9]', '', p)
            if clean:
                val = int(clean)
                if val > 15000: valid_prices.append(val)
        
        if not valid_prices:
            print(f"   ⚠️ Цены пусты.")
            return

        min_price = min(valid_prices)
        print(f"   ✅ НАЙДЕНО: {min_price} руб.")

        # --- ШАГ 6: СОХРАНЕНИЕ ---
        last_price = get_last_price(city, country)
        
        if min_price < 12000:
             print(f"   ⚠️ Цена подозрительно низкая, скип.")
             return

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
                    f"🔗 <a href='{current_url}'>На сайт</a>"
                )
                send_telegram_message(msg)
            else:
                 print(f"   ℹ️ Стабильно.")
        else:
            msg = (
                f"🆕 <b>Найдена цена</b>\n"
                f"✈️ {city} -> {country}\n"
                f"💰 <b>{min_price:,} руб.</b>\n"
                f"🔗 <a href='{current_url}'>На сайт</a>"
            )
            send_telegram_message(msg)

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        try: page.screenshot(path=f"crash_{city}.png")
        except: pass

def main():
    print(f"🚀 VOLAGO FINAL-UI-FIX: {datetime.now()}")
    
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
                time.sleep(2)

        browser.close()

if __name__ == "__main__":
    main()
