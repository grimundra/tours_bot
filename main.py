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
    if not supabase: return None
    try:
        # Берем последнюю цену (duration=0 или 7, неважно, главное сравнить с предыдущим запуском)
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
            "origin_city": city, "destination": country, "duration": 7, # Ставим 7 как дефолт
            "min_price": price, "departure_date_found": datetime.now().strftime("%d.%m.%Y")
        }
        supabase.table("tour_prices").insert(data).execute()
        print(f"   💾 Saved: {price}")
    except Exception as e:
        print(f"   ❌ DB Error: {e}")

def check_prices_smart(page, city_from, country_to):
    print(f"🔄 Проверка: {city_from} -> {country_to}")
    
    try:
        # 1. Заходим на главную
        page.goto("https://www.onlinetours.ru/", timeout=60000)
        
        # Сброс фокуса (иногда помогает)
        try: page.mouse.click(0, 0)
        except: pass

        # --- ШАГ 1: ВВОДИМ "КУДА" ---
        try:
            dest_input = page.locator("input[placeholder*='Страна']")
            # FORCE CLICK!
            dest_input.click(force=True)
            dest_input.fill("")
            time.sleep(0.5)
            dest_input.type(country_to, delay=100)
            time.sleep(2)
            page.keyboard.press("Enter")
            time.sleep(1)
        except Exception as e:
            print(f"   ⚠️ Ошибка ввода страны: {e}")
            return None

        # --- ШАГ 2: КЛИКАЕМ НА ДАТУ/КАЛЕНДАРЬ ---
        print("   📅 Пытаюсь открыть календарь...")
        
        # Тот самый надежный блок из старого кода
        try:
            page.locator(".SearchPanel-date, .search-panel-date").first.click(force=True, timeout=3000)
        except:
            print("   ⚠️ Клик по классу не прошел, пробую по координатам...")
            try:
                # Берем координаты поля ввода страны и кликаем правее
                box = page.locator("input[placeholder*='Страна']").bounding_box()
                if box:
                    # Смещаемся на 400px вправо (там дата)
                    page.mouse.click(box['x'] + box['width'] + 300, box['y'] + 10)
            except:
                print("   ❌ Не смог кликнуть даже по координатам")

        time.sleep(4) # Ждем прогрузки (побольше)

        # --- ШАГ 3: ЧИТАЕМ ЦЕНЫ (СТАРЫЙ НАДЕЖНЫЙ МЕТОД) ---
        
        content = page.content() # Берем ВЕСЬ HTML код страницы
        
        # Ищем любые цифры перед знаком рубля ( > 45 000 ₽ < )
        # Это найдет и зеленые цены, и черные, любые.
        found_prices = re.findall(r'(\d[\d\s]*)\s?₽', content)
        
        valid_prices = []
        for p in found_prices:
            clean = int(re.sub(r'\s+', '', p))
            # Фильтр: от 10к до 800к
            if clean > 10000 and clean < 800000:
                valid_prices.append(clean)
        
        if valid_prices:
            min_price = min(valid_prices)
            print(f"   ✅ Нашел цены: {len(valid_prices)} шт. Мин: {min_price}")
            
            # --- ЛОГИКА БД И ТЕЛЕГРАМА ---
            last_price = get_last_price(city_from, country_to)
            save_price(city_from, country_to, min_price)
            
            if last_price:
                if min_price < last_price:
                    diff = last_price - min_price
                    msg = (
                        f"📉 <b>ЦЕНА УПАЛА!</b>\n"
                        f"✈️ {city_from} -> {country_to}\n"
                        f"💰 <b>{min_price:,} руб.</b> (было {last_price:,})\n"
                        f"📉 Скидка: {diff} руб."
                    )
                    send_telegram_message(msg)
            else:
                # Первая запись в базе
                msg = (
                    f"🆕 <b>Найдена цена</b>\n"
                    f"✈️ {city_from} -> {country_to}\n"
                    f"💰 <b>{min_price:,} руб.</b>"
                )
                send_telegram_message(msg)

            return min_price
        else:
            print(f"   ⚠️ Цены не найдены. (Найдено совпадений в тексте: {len(found_prices)})")
            return None

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return None

def main():
    print(f"🚀 VOLAGO OLD-SCHOOL BOT: {datetime.now()}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-setuid-sandbox']
        )
        
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/112.0.0.0 Safari/537.36",
            viewport={'width': 1920, 'height': 1080},
            locale='ru-RU',
            timezone_id='Europe/Moscow'
        )
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        page = context.new_page()

        for city in CITIES_FROM:
            # Тут мы пропускаем "смену города" на сайте, так как это часто глючит.
            # Мы просто верим, что Onlinetours сам определит город или покажет цены из Москвы.
            # (Чтобы менять город надежно, нужна отдельная сложная логика, пока давай запустим так).
            
            for country in COUNTRIES_TO:
                check_prices_smart(page, city, country)
                time.sleep(3) 

        browser.close()

if __name__ == "__main__":
    main()
