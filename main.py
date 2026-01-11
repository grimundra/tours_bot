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
        # 1. Открываем сайт
        page.goto("https://www.onlinetours.ru/", timeout=60000)
        
        # Сброс фокуса (клик в левый верхний угол)
        try: page.mouse.click(0, 0)
        except: pass

        # --- ШАГ 1: ГОРОД ВЫЛЕТА (ПО ТЕКСТУ) ---
        try:
            print(f"   🛫 Проверяю город вылета...")
            # Ищем элемент, который содержит название города (например "Москва")
            # Обычно он вверху в панели поиска
            city_btn = page.locator(".SearchPanel-departCity").first
            
            # Если не нашли по классу, ищем по тексту текущего города (обычно Москва стоит по дефолту)
            if not city_btn.is_visible():
                city_btn = page.get_by_text("Москва", exact=True).first
            
            # Если нужно сменить город
            current_text = city_btn.inner_text() if city_btn.is_visible() else ""
            if city not in current_text:
                print(f"   ✏️ Меняю {current_text} на {city}...")
                city_btn.click(force=True)
                page.keyboard.type(city, delay=100)
                time.sleep(1)
                page.keyboard.press("ArrowDown")
                page.keyboard.press("Enter")
                # Закрываем список кликом в пустоту
                page.mouse.click(100, 10)
            else:
                print(f"   ✅ Город уже стоит верный: {city}")

        except Exception as e:
            print(f"   ⚠️ Не удалось сменить город (возможно, уже стоит верный): {e}")

        # --- ШАГ 2: СТРАНА (ПО PLACEHOLDER) ---
        try:
            print(f"   🌴 Ввожу страну: {country}...")
            # Самый надежный селектор - плейсхолдер
            dest_input = page.get_by_placeholder("Страна, курорт, отель")
            
            dest_input.click(force=True)
            dest_input.fill("") 
            time.sleep(0.5)
            dest_input.type(country, delay=100)
            time.sleep(2) # Ждем список
            
            # Выбираем (Стрелка вниз + Enter)
            page.keyboard.press("ArrowDown")
            page.keyboard.press("Enter")
            
            # ЗАКРЫВАЕМ СПИСОК (Важно!)
            page.mouse.click(100, 10)
            time.sleep(1)
            
        except Exception as e:
            print(f"   ❌ Ошибка ввода страны: {e}")
            page.screenshot(path=f"error_country_{city}.png")
            return

        # --- ШАГ 3: КАЛЕНДАРЬ (ПО ТЕКСТУ ИЛИ CSS) ---
        print("   📅 Открываю календарь...")
        
        # Убираем опасный клик по координатам (+250px).
        # Используем список надежных селекторов:
        
        calendar_opened = False
        selectors = [
            ".SearchPanel-date",       # Стандартный класс
            ".search-panel-date",      # Альтернативный класс
            "div[class*='date']"       # Любой див с словом date в классе
        ]
        
        for sel in selectors:
            try:
                el = page.locator(sel).first
                if el.is_visible():
                    el.click(force=True)
                    calendar_opened = True
                    break
            except: pass
            
        if not calendar_opened:
            print("   ⚠️ Не нашел кнопку календаря по классам. Пробую кликнуть рядом с полем Страны (аккуратно).")
            # ОЧЕНЬ АККУРАТНЫЙ КЛИК:
            # Поле "Страна" -> +10 пикселей вправо от его границы. 
            # (Раньше было +250, это был перебор)
            box = page.get_by_placeholder("Страна, курорт, отель").bounding_box()
            if box:
                # Кликаем чуть правее поля ввода страны. Там обычно начинается поле даты.
                # Ширина поля страны большая, так что +20px от правого края - это самое начало Даты.
                page.mouse.click(box['x'] + box['width'] + 20, box['y'] + 20)

        # --- ШАГ 4: ЖДЕМ ЗЕЛЕНЫЕ ЦЕНЫ ---
        print("   ⏳ Жду цены...")
        try:
            # Ждем появления класса .text-emerald-600
            page.wait_for_selector(".text-emerald-600", timeout=12000)
        except:
            print("   ⚠️ Цены не появились.")
            # Снимаем скриншот, чтобы видеть, что открылось на самом деле
            page.screenshot(path=f"debug_calendar_{country}.png")
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

        # --- ШАГ 6: БД ---
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
    print(f"🚀 VOLAGO TEXT-NAVIGATOR: {datetime.now()}")
    
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
