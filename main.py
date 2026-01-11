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
        # ШАГ 1: ГОРОД ВЫЛЕТА (Mouse Clicker Logic)
        # ==========================================
        # Применяем ту же логику, что сработала для Страны
        try:
            depart_btn = page.locator(".SearchPanel-departCity, .search-panel-depart-city").first
            current_text = depart_btn.inner_text()
            
            # Если город не совпадает - меняем ЖЕСТКО
            if city not in current_text:
                print(f"   🛫 Меняю город: {current_text} -> {city}...")
                depart_btn.click(force=True)
                
                # Ищем поле ввода (оно может быть внутри виджета)
                # Иногда нужно кликнуть еще раз или просто начать печатать
                page.keyboard.type(city, delay=100)
                time.sleep(1.5)
                
                # Ждем список z-50
                try:
                    page.wait_for_selector("div.z-50", state="visible", timeout=3000)
                    # Клик по первой подсказке
                    page.locator("div.z-50 div.cursor-pointer").first.click()
                    print("      🖱️ Кликнул по городу в списке.")
                except:
                    print("      ⚠️ Список городов не выпал, жму Enter.")
                    page.keyboard.press("Enter")
                
                time.sleep(1)
            else:
                print(f"   ✅ Город {city} уже стоит.")
        except Exception as e:
            print(f"   ⚠️ Ошибка смены города: {e}")

        # ==========================================
        # ШАГ 2: СТРАНА (Mouse Clicker Logic)
        # ==========================================
        try:
            print(f"   🌴 Ввожу страну: {country}...")
            dest_input = page.locator("input[placeholder*='Страна']")
            dest_input.click(force=True)
            
            dest_input.press("Control+A")
            dest_input.press("Backspace")
            dest_input.type(country, delay=150)
            
            # Ждем список
            try:
                page.wait_for_selector("div.z-50", state="visible", timeout=5000)
            except:
                pass

            # Клик по подсказке
            item = page.locator("div.z-50 div.cursor-pointer").first
            if item.is_visible():
                item.click(force=True)
                # print("      🖱️ Страна выбрана.")
            else:
                print("      ⚠️ Элемент списка стран не найден! (Пробую Enter)")
                page.keyboard.press("Enter")

            time.sleep(1)
            
            # Клик в пустоту (закрыть меню)
            page.mouse.click(100, 10)

        except Exception as e:
            print(f"   ❌ Ошибка ввода страны: {e}")
            return

        # ==========================================
        # ШАГ 3: КАЛЕНДАРЬ
        # ==========================================
        print("   📅 Открываю календарь...")
        calendar_opened = False
        
        # Пробуем кликнуть по тексту "Дата"
        try:
            page.get_by_text("Дата вылета").first.click(force=True)
            calendar_opened = True
        except:
            # Если не вышло, пробуем старый класс
            try:
                page.locator(".SearchPanel-date").first.click(force=True)
                calendar_opened = True
            except:
                pass
        
        # Если совсем всё плохо - кликаем справа от поля ввода
        if not calendar_opened:
            print("      ⚠️ Клик по дате через координаты (План Б).")
            box = page.locator("input[placeholder*='Страна']").bounding_box()
            if box:
                page.mouse.click(box['x'] + box['width'] + 20, box['y'] + 20)

        # ==========================================
        # ШАГ 4: ЦЕНЫ + ФОТО-ДОКАЗАТЕЛЬСТВО
        # ==========================================
        print("   ⏳ Жду зеленые ценники...")
        try:
            page.wait_for_selector(".text-emerald-600", timeout=15000)
        except:
            print("   ⚠️ Цены не появились.")
            page.screenshot(path=f"FAIL_{city}_{country}.png")
            return

        # --- ДЕЛАЕМ СКРИНШОТ УСПЕХА ---
        # Чтобы ты увидел глазами, что там происходит
        screenshot_name = f"OK_{city}_{country}.png"
        page.screenshot(path=screenshot_name)
        print(f"   📸 Скриншот сохранен: {screenshot_name}")

        # Парсинг
        prices_elements = page.locator(".text-emerald-600").all_inner_texts()
        valid_prices = []
        for p in prices_elements:
            clean = re.sub(r'[^0-9]', '', p)
            if clean:
                val = int(clean)
                if val > 10000: valid_prices.append(val) # Фильтр 10к (защита от мусора)
        
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
    print(f"🚀 VOLAGO DEBUG & FIX: {datetime.now()}")
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
