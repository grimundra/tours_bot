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
        try: page.mouse.click(0, 0)
        except: pass

        # ==========================================
        # ШАГ 1: ГОРОД ВЫЛЕТА (Попытка смены)
        # ==========================================
        # Пробуем сменить, если не выходит - работаем с тем что есть
        try:
            current_city_el = page.locator(".SearchPanel-departCity").first
            if current_city_el.is_visible() and city not in current_city_el.inner_text():
                print(f"   🛫 Пробую сменить город на {city}...")
                current_city_el.click()
                time.sleep(0.5)
                page.keyboard.type(city, delay=100)
                time.sleep(1.5)
                
                # Клик по выпадающему списку (z-50)
                dropdown = page.locator("div.absolute.z-50 div.cursor-pointer").first
                if dropdown.is_visible():
                    dropdown.click()
                else:
                    # Если списка нет, просто кликаем Enter и надеемся на лучшее
                    page.keyboard.press("Enter")
                
                time.sleep(1)
            else:
                print(f"   ✅ Город {city} (или дефолтный) оставлен.")
        except:
            print("   ⚠️ Не удалось найти виджет города, пропускаю.")

        # ==========================================
        # ШАГ 2: СТРАНА (МЫШКОЙ ПО СПИСКУ)
        # ==========================================
        try:
            print(f"   🌴 Ввожу страну: {country}...")
            
            dest_input = page.locator("input[placeholder*='Страна']")
            dest_input.click(force=True)
            
            # Очистка и ввод
            dest_input.press("Control+A")
            dest_input.press("Backspace")
            dest_input.type(country, delay=150) # Медленный ввод
            
            # Ждем появления контейнера с классом z-50
            print("      ⏳ Жду список...")
            try:
                # Ищем элемент, который ты прислал в HTML: div.z-50
                page.wait_for_selector("div.z-50", state="visible", timeout=5000)
            except:
                print("      ⚠️ Список z-50 не появился.")

            # КЛИК ПО ЭЛЕМЕНТУ СПИСКА
            # Ищем внутри z-50 элемент с cursor-pointer
            item = page.locator("div.z-50 div.cursor-pointer").first
            
            if item.is_visible():
                print("      🖱️ Кликаю мышкой по первой подсказке...")
                item.click(force=True)
                time.sleep(1)
            else:
                print("      ❌ Элемент списка не найден!")
                page.screenshot(path=f"debug_list_{country}.png")
                return

            # Проверка: поле не должно быть пустым
            if not dest_input.input_value():
                print("   ❌ Поле очистилось после клика!")
                return

        except Exception as e:
            print(f"   ❌ Ошибка ввода страны: {e}")
            return

        # ==========================================
        # ШАГ 3: ОТКРЫТИЕ КАЛЕНДАРЯ
        # ==========================================
        print("   📅 Открываю календарь...")
        time.sleep(1) # Даем интерфейсу "остыть" после выбора страны
        
        calendar_opened = False
        
        # Попытка 1: По тексту "Дата" (универсально)
        try:
            page.get_by_text("Дата вылета").first.click(force=True)
            calendar_opened = True
        except:
            pass
            
        # Попытка 2: По классу (если текст не найден)
        if not calendar_opened:
            try:
                page.locator(".SearchPanel-date, .search-panel-date").first.click(force=True)
                calendar_opened = True
            except:
                pass
        
        # Попытка 3: Клик рядом с полем страны (аккуратно)
        if not calendar_opened:
            print("      ⚠️ Клик по тексту не прошел. Кликаю аккуратно справа.")
            box = dest_input.bounding_box()
            if box:
                # Клик +20px от правого края поля страны
                page.mouse.click(box['x'] + box['width'] + 20, box['y'] + 20)

        # ==========================================
        # ШАГ 4: ЦЕНЫ
        # ==========================================
        print("   ⏳ Жду цены...")
        try:
            page.wait_for_selector(".text-emerald-600", timeout=15000)
        except:
            print("   ⚠️ Цены не появились.")
            page.screenshot(path=f"fail_prices_{country}.png")
            return

        # Парсинг
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

        # ==========================================
        # ШАГ 5: СОХРАНЕНИЕ
        # ==========================================
        last_price = get_last_price(city, country)
        save_price(city, country, min_price)
        
        if min_price < 10000: return # Защита от багов

        if last_price:
            if min_price < last_price:
                diff = last_price - min_price
                msg = (
                    f"📉 <b>ЦЕНА УПАЛА!</b>\n"
                    f"✈️ {city} -> {country}\n"
                    f"💰 <b>{min_price:,} руб.</b> (было {last_price:,})\n"
                    f"📉 Скидка: {diff} руб."
                )
                send_telegram_message(msg)
            else:
                 print(f"   ℹ️ Стабильно.")
        else:
            msg = (
                f"🆕 <b>Найдена цена</b>\n"
                f"✈️ {city} -> {country}\n"
                f"💰 <b>{min_price:,} руб.</b>"
            )
            send_telegram_message(msg)

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        try: page.screenshot(path=f"crash_{city}.png")
        except: pass

def main():
    print(f"🚀 VOLAGO MOUSE-CLICKER: {datetime.now()}")
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-setuid-sandbox']
        )
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        for city in CITIES_FROM:
            for country in COUNTRIES_TO:
                run_search(page, city, country)
                time.sleep(2)

        browser.close()

if __name__ == "__main__":
    main()
