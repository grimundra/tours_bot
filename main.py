import os
import time
import re
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright

# --- НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = os.getenv('TG_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TG_CHAT_ID')

CITIES_FROM = ["Москва", "Санкт-Петербург"]
COUNTRIES_TO = ["Турция", "Египет", "ОАЭ", "Таиланд"] 

# --- ФУНКЦИИ ---

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except: pass

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
        try:
            # Находим кнопку текущего города
            depart_btn = page.locator(".SearchPanel-departCity, .search-panel-depart-city").first
            current_text = depart_btn.inner_text()
            
            # Если город уже стоит верный - не трогаем
            if city in current_text:
                 print(f"   ✅ Город {city} уже стоит.")
            else:
                print(f"   🛫 Меняю город: {current_text} -> {city}...")
                depart_btn.click(force=True)
                
                # ВАЖНО: После клика фокус падает в поле ввода.
                # Чистим старое (Ctrl+A -> Backspace) и пишем новое
                page.keyboard.press("Control+A")
                page.keyboard.press("Backspace")
                time.sleep(0.1)
                
                # Медленная печать (чтобы React успел понять)
                page.keyboard.type(city, delay=150)
                time.sleep(1.5) # Ждем список
                
                # Ждем список z-50
                try:
                    # Ищем контейнер списка
                    page.wait_for_selector("div.z-50", state="visible", timeout=5000)
                    
                    # Ищем кликабельный элемент внутри
                    item = page.locator("div.z-50 div.cursor-pointer").first
                    if item.is_visible():
                        item.click(force=True)
                        print("      🖱️ Кликнул по городу в списке.")
                    else:
                        print("      ⚠️ Элемент списка города не виден. Жму Enter.")
                        page.keyboard.press("Enter")
                except:
                    print("      ⚠️ Список городов (z-50) не появился. Жму Enter.")
                    page.keyboard.press("Enter")
                
                time.sleep(1)

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
                
                item = page.locator("div.z-50 div.cursor-pointer").first
                if item.is_visible():
                    item.click(force=True)
                    # print("      🖱️ Страна выбрана.")
                else:
                    print("      ⚠️ Элемент списка стран не найден! (Пробую Enter)")
                    page.keyboard.press("Enter")
            except:
                pass

            time.sleep(1)
            # Клик в пустоту (закрыть меню наверняка)
            page.mouse.click(100, 10)

        except Exception as e:
            print(f"   ❌ Ошибка ввода страны: {e}")
            return

        # ==========================================
        # ШАГ 3: КАЛЕНДАРЬ
        # ==========================================
        print("   📅 Открываю календарь...")
        calendar_opened = False
        
        # 1. Пробуем по тексту
        try:
            page.get_by_text("Дата вылета").first.click(force=True)
            calendar_opened = True
        except: pass
            
        # 2. Пробуем по классу
        if not calendar_opened:
            try:
                page.locator(".SearchPanel-date, .search-panel-date").first.click(force=True)
                calendar_opened = True
            except: pass
        
        # 3. План Б (координаты)
        if not calendar_opened:
            print("      ⚠️ Клик по дате через координаты (План Б).")
            box = page.locator("input[placeholder*='Страна']").bounding_box()
            if box:
                page.mouse.click(box['x'] + box['width'] + 20, box['y'] + 20)

        # ==========================================
        # ШАГ 4: ЦЕНЫ + ФОТО
        # ==========================================
        print("   ⏳ Жду цены...")
        try:
            page.wait_for_selector(".text-emerald-600", timeout=15000)
        except:
            print("   ⚠️ Цены не появились.")
            # Делаем скриншот ошибки
            page.screenshot(path=f"FAIL_{city}_{country}.png")
            return

        # Делаем скриншот УСПЕХА (чтобы проверить город)
        screenshot_name = f"OK_{city}_{country}.png"
        page.screenshot(path=screenshot_name)
        
        # Парсинг
        prices_elements = page.locator(".text-emerald-600").all_inner_texts()
        valid_prices = []
        for p in prices_elements:
            clean = re.sub(r'[^0-9]', '', p)
            if clean:
                val = int(clean)
                if val > 10000: valid_prices.append(val) # Фильтр мусора
        
        if not valid_prices:
            print(f"   ⚠️ Цены пусты.")
            return

        min_price = min(valid_prices)
        print(f"   ✅ НАЙДЕНО: {min_price} руб.")

        # ==========================================
        # ШАГ 5: ОТПРАВКА В TELEGRAM (ВСЕГДА)
        # ==========================================
        # Теперь мы не сравниваем с БД, а просто шлем самое дешевое
        current_url = page.url
        msg = (
            f"🔥 <b>Минимальная цена</b>\n"
            f"✈️ {city} -> {country}\n"
            f"💰 <b>{min_price:,} руб.</b>\n"
            f"📅 Скриншот: {screenshot_name}\n"
            f"🔗 <a href='{current_url}'>Проверить на сайте</a>"
        )
        send_telegram_message(msg)
        print("   📩 Отправлено в Telegram")

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        try: page.screenshot(path=f"crash_{city}.png")
        except: pass

def main():
    print(f"🚀 VOLAGO NO-DB BOT: {datetime.now()}")
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
                # Пауза между запросами
                time.sleep(3)

        browser.close()

if __name__ == "__main__":
    main()
