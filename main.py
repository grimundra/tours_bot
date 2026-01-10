import os
import time
import re
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright
from supabase import create_client, Client

# --- КОНФИГУРАЦИЯ ---

# ТЕПЕРЬ ИЩЕМ ПЕРЕМЕННЫЕ ИМЕННО ТАК, КАК ОНИ У ТЕБЯ В GITHUB
TELEGRAM_BOT_TOKEN = os.getenv('TG_TOKEN')       # Было TELEGRAM_BOT_TOKEN
TELEGRAM_CHANNEL_ID = os.getenv('TG_CHAT_ID')    # Было TELEGRAM_CHANNEL_ID
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# Списки городов и стран
CITIES_FROM = [
    "Москва", "Санкт-Петербург", "Екатеринбург", "Казань", 
    "Новосибирск", "Сочи", "Уфа", "Самара"
]

COUNTRIES_TO = {
    "Турция": "turkey",
    "Египет": "egypt",
    "ОАЭ": "united-arab-emirates",
    "Таиланд": "thailand",
    "Шри-Ланка": "sri-lanka",
    "Куба": "cuba",
    "Мальдивы": "maldives",
}

DURATIONS = [6, 7, 9, 10]

# --- ИНИЦИАЛИЗАЦИЯ SUPABASE ---
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"❌ Ошибка инициализации Supabase: {e}")
else:
    print("⚠️ Внимание: Ключи Supabase не найдены.")

# --- ФУНКЦИИ ---

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN:
        print("   ⚠️ Нет токена ТГ, сообщение не отправлено.")
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"   ❌ Ошибка отправки Telegram: {e}")

def get_last_price(city, country, duration):
    if not supabase:
        return None
    try:
        response = supabase.table("tour_prices") \
            .select("min_price") \
            .eq("origin_city", city) \
            .eq("destination", country) \
            .eq("duration", duration) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        
        if response.data and len(response.data) > 0:
            return response.data[0]['min_price']
    except Exception as e:
        print(f"   ⚠️ Ошибка чтения БД: {e}")
    return None

def save_price_to_db(city, country, duration, price, date_found):
    if not supabase:
        return
    try:
        data = {
            "origin_city": city,
            "destination": country,
            "duration": duration,
            "min_price": int(price),
            "departure_date_found": date_found
        }
        supabase.table("tour_prices").insert(data).execute()
        print(f"   💾 Сохранено в БД.")
    except Exception as e:
        print(f"   ❌ Ошибка записи в БД: {e}")

def check_route(page, city_from, country_name, country_slug, duration):
    print(f"🔄 {city_from} -> {country_name} ({duration} н.)")

    url = (
        f"https://www.onlinetours.ru/tours/{country_slug}"
        f"?start_from={city_from}"
        f"&nights_from={duration}&nights_to={duration}"
    )

    try:
        page.goto(url, timeout=60000)
        
        try:
            page.locator("body").click(position={"x": 10, "y": 10})
        except:
            pass

        time.sleep(5) 
        
        content = page.content()
        matches = re.findall(r'(\d[\d\s]*)\s?₽', content)
        
        valid_prices = []
        for m in matches:
            clean = int(re.sub(r'\s+', '', m))
            if clean > 10000 and clean < 1000000:
                valid_prices.append(clean)
        
        if not valid_prices:
            print("   ⚠️ Цены не найдены.")
            return

        min_price = min(valid_prices)
        
        # ЛОГИКА
        last_price = get_last_price(city_from, country_name, duration)
        date_found = datetime.now().strftime("%d.%m.%Y")
        
        save_price_to_db(city_from, country_name, duration, min_price, date_found)

        if last_price:
            if min_price < last_price:
                diff = last_price - min_price
                msg = (
                    f"📉 <b>Цена упала!</b> (-{diff} руб.)\n"
                    f"✈️ {city_from} -> {country_name}\n"
                    f"🌙 {duration} ночей\n"
                    f"💰 <b>{min_price:,} руб.</b> (было {last_price:,})\n"
                    f"🔗 <a href='{url}'>Смотреть тур</a>"
                )
                print(f"   🔔 УПАЛА ЦЕНА: {min_price}")
                send_telegram_message(msg)
            else:
                print(f"   ℹ️ Цена стаб: {min_price} (было {last_price})")
        else:
            msg = (
                f"🆕 <b>Новое направление</b>\n"
                f"✈️ {city_from} -> {country_name}\n"
                f"🌙 {duration} ночей\n"
                f"💰 <b>{min_price:,} руб.</b>\n"
                f"🔗 <a href='{url}'>Смотреть тур</a>"
            )
            print(f"   🔔 ПЕРВАЯ ЗАПИСЬ: {min_price}")
            send_telegram_message(msg)

    except Exception as e:
        print(f"   ❌ Ошибка парсинга: {e}")

def main():
    print(f"🚀 Запуск мониторинга VOLAGO: {datetime.now()}")
    
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
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        
        page = context.new_page()

        for city in CITIES_FROM:
            for country_name, country_slug in COUNTRIES_TO.items():
                for duration in DURATIONS:
                    check_route(page, city, country_name, country_slug, duration)
                    time.sleep(2) 

        browser.close()

if __name__ == "__main__":
    main()
