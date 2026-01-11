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
        # Клик в пустоту для фокуса
        try: page.mouse.click(0, 0)
        except: pass

        # ==========================================
        # ШАГ 1: ГОРОД ВЫЛЕТА (Откуда)
        # ==========================================
        try:
            # Ищем блок, где написан текущий город (Москва или Вылет из...)
            # Класс .SearchPanel-departCity обычно держит этот текст
            depart_btn = page.locator(".SearchPanel-departCity, .search-panel-depart-city").first
            current_city_text = depart_btn.inner_text()
            
            # Если город не совпадает, меняем его
            if city not in current_text:
                print(f"   🛫 Меняю город на {city}...")
                depart_btn.click(force=True)
                
                # Пишем город
                # Важно: иногда поле ввода появляется внутри попапа, иногда прямо там
                page.keyboard.type(city, delay=100)
                time.sleep(1.5) # Ждем пока сервер ответит подсказками
                
                # --- ВЫБОР ИЗ СПИСКА (ПО ТВОЕМУ HTML) ---
                # Ищем контейнер с классом z-50 (поверх всех)
                # Внутри ищем элементы с cursor-pointer
                dropdown_item = page.locator("div.absolute.z-50 div.cursor-pointer").first
                
                if dropdown_item.is_visible():
                    print("      ✅ Вижу выпадающий список городов. Кликаю первый.")
                    dropdown_item.click()
                else:
                    print("      ⚠️ Список городов не появился. Жму Enter.")
                    page.keyboard.press("Enter")
                
                time.sleep(1)
            else:
                print(f"   ✅ Город {city} уже стоит.")
                
        except Exception as e:
            print(f"   ⚠️ Ошибка смены города: {e}")

        # ==========================================
        # ШАГ 2: СТРАНА (Куда)
        # ==========================================
        try:
            print(f"   🌴 Выбираю страну: {country}...")
            
            # 1. Находим поле и кликаем
            dest_input = page.locator("input[placeholder*='Страна']")
            dest_input.click(force=True)
            
            # 2. Очищаем и пишем
            dest_input.fill("") 
            time.sleep(0.2)
            dest_input.type(country, delay=100)
            time.sleep(2) # Ждем прогрузки списка
            
            # 3. --- ВЫБОР ИЗ СПИСКА (ПО ТВОЕМУ HTML) ---
            # Твой HTML: <div class="absolute ... z-50 ..."> ... <div class="... cursor-pointer ...">
            # Мы ищем первый элемент списка и кликаем.
            
            # Селектор: Найти div с z-50, внутри него найти div с cursor-pointer
            dropdown_item = page.locator("div.absolute.z-50 div.cursor-pointer").first
            
            if dropdown_item.is_visible():
                print(f"      👇 Кликаю по первой подсказке для '{country}'")
                dropdown_item.click(force=True)
            else:
                print("      ⚠️ Список стран не выпал! Пробую Enter.")
                page.keyboard.press("Enter")

            time.sleep(1)
            
            # 4. Сброс фокуса (Клик в шапку сайта), чтобы закрыть меню, если оно вдруг осталось
            page.mouse.click(100, 10)
            
        except Exception as e:
            print(f"   ❌ Ошибка ввода страны: {e}")
            page.screenshot(path=f"err_country_{city}.png")
            return

        # ==========================================
        # ШАГ 3: КАЛЕНДАРЬ
        # ==========================================
        print("   📅 Открываю календарь...")
        
        # Теперь, когда списки закрыты кликом по подсказке, календарь должен быть доступен.
        try:
            # Пробуем по классу
            page.locator(".SearchPanel-date, .search-panel-date").first.click(force=True)
        except:
             # Если класса нет, кликаем аккуратно справа от поля ввода (как мы считали)
             print("   ⚠️ Клик по классу даты не прошел. Кликаю рядом с полем Страны.")
             box = page.locator("input[placeholder*='Страна']").bounding_box()
             if box:
                 # +20 пикселей от правого края поля "Страна" - это начало поля "Дата"
                 page.mouse.click(box['x'] + box['width'] + 20, box['y'] + 20)

        # ==========================================
        # ШАГ 4: ЦЕНЫ
        # ==========================================
        print("   ⏳ Жду зеленые ценники...")
        try:
            # Ждем появления класса .text-emerald-600
            page.wait_for_selector(".text-emerald-600", timeout=15000)
        except:
            print("   ⚠️ Цены не появились.")
            page.screenshot(path=f"err_calendar_{country}.png")
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
    print(f"🚀 VOLAGO DROPDOWN-HUNTER: {datetime.now()}")
    
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
