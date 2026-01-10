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
DURATIONS = [6, 7, 9, 10]

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

def get_last_price(city, country, duration):
    if not supabase: return None
    try:
        response = supabase.table("tour_prices") \
            .select("min_price") \
            .eq("origin_city", city) \
            .eq("destination", country) \
            .eq("duration", duration) \
            .order("created_at", desc=True) \
            .limit(1) \
            .execute()
        if response.data: return response.data[0]['min_price']
    except: pass
    return None

def save_price(city, country, duration, price):
    if not supabase: return
    try:
        data = {
            "origin_city": city, "destination": country, "duration": duration,
            "min_price": price, "departure_date_found": datetime.now().strftime("%d.%m.%Y")
        }
        supabase.table("tour_prices").insert(data).execute()
        print(f"   💾 Saved to DB: {price}")
    except Exception as e:
        print(f"   ❌ DB Error: {e}")

def run_search(page, city, country, duration):
    print(f"🔄 Поиск: {city} -> {country} [{duration} ночей]")
    
    try:
        # 1. Заходим на главную
        page.goto("https://www.onlinetours.ru/", timeout=60000)
        
        # Клик в пустоту, чтобы закрыть возможные приветственные баннеры
        try:
            page.mouse.click(10, 10)
        except: pass

        # --- ШАГ 1: ГОРОД ВЫЛЕТА ---
        try:
            # Ищем кнопку вылета
            depart_btn = page.locator("div[class*='departCity'], div[class*='DepartCity']").first
            # FORCE CLICK!
            depart_btn.click(force=True) 
            
            # Выбираем город (здесь force не обязателен, список обычно сверху, но добавим)
            city_option = page.get_by_text(city, exact=True).first
            if city_option.is_visible():
                city_option.click(force=True)
            else:
                # Если города нет в быстром списке, пропускаем смену (значит он уже стоит или список другой)
                pass
        except:
            pass # Иногда город уже выбран верно

        # --- ШАГ 2: КУДА (СТРАНА) ---
        # Ищем инпут "Куда"
        dest_input = page.locator("input[placeholder*='Страна'], input[placeholder*='курорт']")
        
        # FORCE CLICK! Игнорируем перекрытия
        dest_input.click(force=True)
        
        dest_input.fill("") # Очищаем
        time.sleep(0.5)
        dest_input.fill(country)
        time.sleep(1.5) # Ждем подсказку
        
        # Жмем Enter
        page.keyboard.press("Enter")
        time.sleep(1)

        # --- ШАГ 3: НОЧЕЙ ---
        print(f"   🌙 Выставляю длительность: {duration}...")
        
        # Находим кнопку ночей. Ищем блок, содержащий текст "ноч"
        nights_btn = page.locator("div").filter(has_text=re.compile(r"\d+\s*-\s*\d+\s*ноч")).last
        if not nights_btn.is_visible():
             nights_btn = page.locator(".SearchPanel-nights, .search-panel-nights").first
        
        # FORCE CLICK!
        nights_btn.click(force=True)
        time.sleep(1)

        # Вписываем цифры
        input_from = page.locator("input[class*='min'], input[class*='Min']").first
        input_from.click(force=True)
        input_from.fill(str(duration))
        
        input_to = page.locator("input[class*='max'], input[class*='Max']").first
        input_to.click(force=True)
        input_to.fill(str(duration))
        
        # Закрываем попап (клик в шапку сайта)
        page.mouse.click(200, 10)
        time.sleep(1)

        # --- ШАГ 4: ОТКРЫВАЕМ КАЛЕНДАРЬ ---
        print("   📅 Открываю календарь...")
        date_btn = page.locator(".SearchPanel-date, .search-panel-date").first
        
        # FORCE CLICK!
        date_btn.click(force=True)
        
        # Ждем загрузки зеленых ценников
        try:
            page.wait_for_selector(".text-emerald-600", timeout=12000)
        except:
            print("   ⚠️ Ценники не прогрузились (таймаут).")
            return

        # --- ШАГ 5: ПАРСИНГ ---
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

        # --- ШАГ 6: БД И ТЕЛЕГРАМ ---
        last_price = get_last_price(city, country, duration)
        save_price(city, country, duration, min_price)
        current_url = page.url
        
        if last_price:
            if min_price < last_price:
                diff = last_price - min_price
                msg = (
                    f"📉 <b>ЦЕНА УПАЛА!</b>\n"
                    f"✈️ {city} -> {country}\n"
                    f"🌙 {duration} ночей\n"
                    f"💰 <b>{min_price:,} руб.</b> (было {last_price:,})\n"
                    f"📉 Скидка: {diff} руб.\n"
                    f"🔗 <a href='{current_url}'>Перейти на сайт</a>"
                )
                send_telegram_message(msg)
        else:
            msg = (
                f"🆕 <b>Найдена цена</b>\n"
                f"✈️ {city} -> {country}\n"
                f"🌙 {duration} ночей\n"
                f"💰 <b>{min_price:,} руб.</b>\n"
                f"🔗 <a href='{current_url}'>Перейти на сайт</a>"
            )
            send_telegram_message(msg)

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")

def main():
    print(f"🚀 VOLAGO BOT STARTED (FORCE MODE): {datetime.now()}")
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
                for duration in DURATIONS:
                    run_search(page, city, country, duration)
                    time.sleep(2)

        browser.close()

if __name__ == "__main__":
    main()
