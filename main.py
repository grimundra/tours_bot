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

FLAGS = {
    "Турция": "🇹🇷", "Египет": "🇪🇬", "ОАЭ": "🇦🇪", "Таиланд": "🇹🇭",
    "Куба": "🇨🇺", "Мальдивы": "🇲🇻", "Шри-Ланка": "🇱🇰"
}

# --- ФУНКЦИИ ---

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except: pass

def run_search(page, target_city, target_country):
    print(f"🔄 Поиск: {target_city} -> {target_country}")
    
    try:
        # 1. Загрузка
        page.goto("https://www.onlinetours.ru/", timeout=60000)
        try: page.mouse.click(0, 0)
        except: pass

        # ==========================================
        # ШАГ 1: ГОРОД ВЫЛЕТА (ЛОГИКА КАК У СТРАНЫ)
        # ==========================================
        try:
            # 1. Сначала проверяем, какой город сейчас стоит.
            # Ищем текст "Москва" или "Санкт-Петербург" на странице.
            # Это и есть кнопка открытия меню.
            
            triggers = ["Москва", "Санкт-Петербург", target_city]
            found_btn = None
            current_val = ""

            for trigger in triggers:
                # Ищем кнопку по тексту (мягкий поиск)
                btn = page.get_by_text(trigger, exact=False).first
                if btn.is_visible():
                    found_btn = btn
                    current_val = trigger
                    break
            
            # Если нашли кнопку с городом
            if found_btn:
                # Проверяем, совпадает ли он с тем, что нам нужен
                # "Москва" in "Москва" -> True
                if target_city in current_val:
                     print(f"   ✅ Город {target_city} уже выбран.")
                else:
                    print(f"   🛫 Меняю город: {current_val} -> {target_city}...")
                    found_btn.click(force=True)
                    
                    # Очистка (Ctrl+A -> Backspace)
                    page.keyboard.press("Control+A")
                    page.keyboard.press("Backspace")
                    time.sleep(0.1)
                    
                    # Ввод нового города
                    page.keyboard.type(target_city, delay=100)
                    time.sleep(1.5) # Ждем пока React отрисует список
                    
                    # --- КЛИК ПО СПИСКУ (ТВОЙ HTML) ---
                    try:
                        # Ждем контейнер z-50
                        page.wait_for_selector("div.z-50", state="visible", timeout=5000)
                        
                        # Ищем элемент с cursor-pointer (как ты прислал в коде)
                        item = page.locator("div.z-50 div.cursor-pointer").first
                        
                        if item.is_visible():
                            item.click(force=True)
                            print("      🖱️ Кликнул по городу в списке.")
                        else:
                            print("      ⚠️ Элемент списка не найден, жму Enter.")
                            page.keyboard.press("Enter")
                    except:
                        print("      ⚠️ Список z-50 не появился, жму Enter.")
                        page.keyboard.press("Enter")
                    
                    time.sleep(1)
            else:
                print("   ⚠️ Не нашел кнопку текущего города. Пропускаю смену.")

        except Exception as e:
            print(f"   ⚠️ Ошибка смены города: {e}")

        # ==========================================
        # ШАГ 2: СТРАНА (Та же логика)
        # ==========================================
        try:
            print(f"   🌴 Ввожу страну: {target_country}...")
            dest_input = page.locator("input[placeholder*='Страна']")
            dest_input.click(force=True)
            
            dest_input.press("Control+A")
            dest_input.press("Backspace")
            dest_input.type(target_country, delay=100)
            
            try:
                # Тот же самый z-50
                page.wait_for_selector("div.z-50", state="visible", timeout=5000)
                item = page.locator("div.z-50 div.cursor-pointer").first
                if item.is_visible():
                    item.click(force=True)
                else:
                    page.keyboard.press("Enter")
            except:
                pass 

            time.sleep(1)
            page.mouse.click(100, 10) # Закрыть меню

        except Exception as e:
            print(f"   ❌ Ошибка ввода страны: {e}")
            return

        # ==========================================
        # ШАГ 3: КАЛЕНДАРЬ
        # ==========================================
        print("   📅 Открываю календарь...")
        calendar_opened = False
        
        # 1. Пробуем по тексту "Дата"
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
        
        # 3. План Б (координаты справа от поля страны)
        if not calendar_opened:
            print("      ⚠️ Клик по дате через координаты.")
            box = page.locator("input[placeholder*='Страна']").bounding_box()
            if box:
                page.mouse.click(box['x'] + box['width'] + 20, box['y'] + 20)

        # ==========================================
        # ШАГ 4: ЦЕНЫ
        # ==========================================
        print("   ⏳ Жду цены...")
        try:
            page.wait_for_selector(".text-emerald-600", timeout=20000)
        except:
            print("   ⚠️ Цены не появились.")
            return

        prices_elements = page.locator(".text-emerald-600").all_inner_texts()
        valid_prices = []
        for p in prices_elements:
            clean = re.sub(r'[^0-9]', '', p)
            if clean:
                val = int(clean)
                if val > 10000: valid_prices.append(val)
        
        if not valid_prices:
            print(f"   ⚠️ Цены пусты.")
            return

        min_price = min(valid_prices)
        print(f"   ✅ НАЙДЕНО: {min_price} руб.")

        # ==========================================
        # ШАГ 5: ОТПРАВКА
        # ==========================================
        
        flag = FLAGS.get(target_country, "🏳️")
        current_url = page.url
        
        msg = (
            f"{flag} <b>{target_country}</b>\n"
            f"🛫 Вылет: {target_city}\n"
            f"💰 <b>{min_price:,} руб.</b>\n"
            f"🔗 <a href='{current_url}'>Проверить</a>"
        )
        send_telegram_message(msg)
        print("   📩 Отправлено в Telegram")

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")

def main():
    print(f"🚀 VOLAGO TWIN-LOGIC BOT: {datetime.now()}")
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
                time.sleep(3) # Пауза между странами

        browser.close()

if __name__ == "__main__":
    main()
