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

CITIES_FROM = ["Москва", "Санкт-Петербург", "Екатеринбург", "Сочи", "Самара", "Нижний Новгород", "Тюмень", "Новосибирск", "Казань", "Уфа"]
COUNTRIES_TO = ["Турция", "Египет", "ОАЭ", "Таиланд", "Дубай", "Китай", "Вьетнам", "Мальдивы", "Шри-Ланка"] 

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
        
        # Сброс кликом в угол
        try: page.mouse.click(0, 0)
        except: pass

        # --- ШАГ 1: ВВОДИМ "КУДА" ---
        try:
            # Ищем поле назначения
            dest_input = page.locator("input[placeholder*='Страна']")
            dest_input.click(force=True)
            dest_input.fill("")
            time.sleep(0.5)
            dest_input.type(country, delay=100)
            time.sleep(2) # Ждем подсказку
            page.keyboard.press("Enter")
            time.sleep(1)
        except:
            print("   ❌ Не удалось ввести страну")
            return

        # --- ШАГ 2: ОТКРЫВАЕМ КАЛЕНДАРЬ ---
        print("   📅 Жму на календарь...")
        
        # Строго ищем кнопку даты
        try:
            page.locator(".SearchPanel-date, .search-panel-date").first.click(force=True, timeout=5000)
        except:
            # Запасной вариант: клик по координатам, ЕСЛИ кнопка не сработала
            print("   ⚠️ Клик по классу не прошел, пробую координаты...")
            box = page.locator("input[placeholder*='Страна']").bounding_box()
            if box:
                page.mouse.click(box['x'] + box['width'] + 300, box['y'] + 10)

        # --- ШАГ 3: ЖДЕМ ИМЕННО ЗЕЛЕНЫЕ ЦЕНЫ ---
        # Мы НЕ ищем "любые цифры". Мы ждем только класс .text-emerald-600
        print("   ⏳ Жду загрузки цен (до 15 сек)...")
        
        try:
            # Ждем появления хотя бы одного зеленого ценника
            page.wait_for_selector(".text-emerald-600", timeout=15000)
        except:
            print("   ⚠️ Ценники не появились. Возможно, календарь не открылся.")
            # Делаем скриншот для отладки (сохранится в Artifacts)
            page.screenshot(path=f"error_{city}_{country}.png")
            return

        # --- ШАГ 4: ЧИТАЕМ ТОЛЬКО ЗЕЛЕНЫЕ ЦЕНЫ ---
        # Берем текст только из элементов с нужным классом
        price_elements = page.locator(".text-emerald-600").all_inner_texts()
        
        valid_prices = []
        for p in price_elements:
            # p = "45 000 ₽"
            clean = re.sub(r'[^0-9]', '', p)
            if clean:
                val = int(clean)
                # Фильтр: Цена должна быть больше 15 000 (чтобы точно убрать рассрочки)
                if val > 15000: 
                    valid_prices.append(val)
        
        if not valid_prices:
            print(f"   ⚠️ Найдены элементы цен, но они пустые или < 15к: {price_elements[:3]}")
            return

        min_price = min(valid_prices)
        print(f"   ✅ НАЙДЕНО: {min_price} руб.")

        # --- ШАГ 5: БД И ТЕЛЕГРАМ ---
        last_price = get_last_price(city, country)
        
        # ВАЖНО: Если цена странная (слишком маленькая), лучше проигнорировать
        if min_price < 12000:
             print(f"   ⚠️ Цена подозрительно низкая ({min_price}), пропускаю.")
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
                 print(f"   ℹ️ Цена стабильна (было {last_price})")
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
    print(f"🚀 VOLAGO STRICT BOT: {datetime.now()}")
    
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
