import os
import time
import re
import json
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright

# --- НАСТРОЙКИ ---
TELEGRAM_BOT_TOKEN = os.getenv('TG_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TG_CHAT_ID')
HISTORY_FILE = "history.json"

CITIES_FROM = [
    "Москва", "Санкт-Петербург", "Екатеринбург", "Сочи", "Самара", 
    "Нижний Новгород", "Тюмень", "Новосибирск", "Казань", "Уфа", 
    "Краснодар", "Владивосток", "Иркутск"
]

COUNTRIES_TO = [
    "Турция", "Египет", "ОАЭ", "Таиланд", "Дубай", 
    "Китай", "Вьетнам", "Мальдивы", "Шри-Ланка", "Стамбул", "Куба"
]

FLAGS = {
    "Турция": "🇹🇷", "Стамбул": "🇹🇷",
    "Египет": "🇪🇬",
    "ОАЭ": "🇦🇪", "Дубай": "🇦🇪",
    "Таиланд": "🇹🇭",
    "Китай": "🇨🇳",
    "Вьетнам": "🇻🇳",
    "Мальдивы": "🇲🇻",
    "Шри-Ланка": "🇱🇰",
    "Куба": "🇨🇺"
}

# --- ФУНКЦИИ ИСТОРИИ ---

def load_history():
    """Загружает историю цен из файла, если он есть."""
    if os.path.exists(HISTORY_FILE):
        try:
            with open(HISTORY_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except:
            return {}
    return {}

def save_history(history):
    """Перезаписывает файл истории актуальными данными."""
    try:
        with open(HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"❌ Ошибка сохранения истории: {e}")

# --- ФУНКЦИИ БОТА ---

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN: return
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "HTML"}
        requests.post(url, json=payload, timeout=10)
    except: pass

def run_search(page, target_city, target_country, history):
    print(f"🔄 Поиск: {target_city} -> {target_country}")
    
    # Уникальный ключ для пары Город-Страна
    history_key = f"{target_city}_{target_country}"
    
    try:
        page.goto("https://www.onlinetours.ru/", timeout=60000)
        try: page.mouse.click(0, 0)
        except: pass

        # ==========================================
        # ШАГ 1: ГОРОД ВЫЛЕТА (Input Logic)
        # ==========================================
        try:
            city_input = page.locator("input[placeholder='Город вылета']")
            current_val = city_input.input_value()
            
            if target_city not in current_val:
                city_input.click(force=True)
                city_input.press("Control+A")
                city_input.press("Backspace")
                time.sleep(0.1)
                city_input.type(target_city, delay=100)
                
                try:
                    page.wait_for_selector("div.z-50", state="visible", timeout=3000)
                    item = page.locator("div.z-50 div.cursor-pointer").first
                    if item.is_visible(): item.click(force=True)
                    else: page.keyboard.press("Enter")
                except: page.keyboard.press("Enter")
                
                time.sleep(1)
        except Exception as e:
            print(f"   ⚠️ Ошибка смены города: {e}")

        # ==========================================
        # ШАГ 2: СТРАНА
        # ==========================================
        try:
            dest_input = page.locator("input[placeholder*='Страна']")
            dest_input.click(force=True)
            dest_input.press("Control+A")
            dest_input.press("Backspace")
            dest_input.type(target_country, delay=100)
            
            try:
                page.wait_for_selector("div.z-50", state="visible", timeout=3000)
                item = page.locator("div.z-50 div.cursor-pointer").first
                if item.is_visible(): item.click(force=True)
                else: page.keyboard.press("Enter")
            except: pass 
            time.sleep(0.5)
            page.mouse.click(100, 10)
        except: return

        # ==========================================
        # ШАГ 3: КАЛЕНДАРЬ
        # ==========================================
        calendar_opened = False
        try:
            page.get_by_text("Дата вылета").first.click(force=True)
            calendar_opened = True
        except: pass
        if not calendar_opened:
            try:
                page.locator(".SearchPanel-date, .search-panel-date").first.click(force=True)
                calendar_opened = True
            except: pass
        if not calendar_opened:
            box = page.locator("input[placeholder*='Страна']").bounding_box()
            if box: page.mouse.click(box['x'] + box['width'] + 20, box['y'] + 20)

        # ==========================================
        # ШАГ 4: ЦЕНЫ
        # ==========================================
        try:
            # Ждем всего 6 секунд. Если цен нет - значит рейсов нет.
            page.wait_for_selector(".text-emerald-600", timeout=6000)
        except:
            # print("   ⚠️ Цены не появились, пропускаю.")
            return

        prices_elements = page.locator(".text-emerald-600").all_inner_texts()
        valid_prices = []
        for p in prices_elements:
            clean = re.sub(r'[^0-9]', '', p)
            if clean:
                val = int(clean)
                if val > 10000: valid_prices.append(val)
        
        if not valid_prices: return

        min_price = min(valid_prices)
        print(f"   ✅ НАЙДЕНО: {min_price} руб.")

        # ==========================================
        # ШАГ 5: СРАВНЕНИЕ С ИСТОРИЕЙ И ОТПРАВКА
        # ==========================================
        
        flag = FLAGS.get(target_country, "🏳️")
        old_price = history.get(history_key)
        status_text = ""
        
        # Логика сравнения
        if old_price is None:
            status_text = "🆕 <b>Новое направление</b>"
        elif min_price < old_price:
            diff = old_price - min_price
            status_text = f"📉 <b>Цена СНИЗИЛАСЬ на {diff:,} руб.</b>"
        elif min_price > old_price:
            diff = min_price - old_price
            status_text = f"📈 <b>Цена ВЫРОСЛА на {diff:,} руб.</b>"
        else:
            status_text = "🟰 <b>Цена не изменилась</b>"

        # Формируем и шлем сообщение
        msg = (
            f"{flag} <b>{target_country}</b>\n"
            f"🛫 Вылет: {target_city}\n"
            f"💰 <b>{min_price:,} руб.</b>\n"
            f"{status_text}"
        )
        send_telegram_message(msg)
        
        # Обновляем запись в памяти
        history[history_key] = min_price

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")

def main():
    print(f"🚀 VOLAGO FINAL SYSTEM: {datetime.now()}")
    
    # 1. Загрузка старых цен
    history = load_history()
    print(f"📚 В памяти {len(history)} направлений.")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-setuid-sandbox']
        )
        context = browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = context.new_page()

        for city in CITIES_FROM:
            for country in COUNTRIES_TO:
                run_search(page, city, country, history)
                # Маленькая пауза, чтобы не дудосить сайт
                time.sleep(1)

        browser.close()
    
    # 2. Сохранение новых цен в файл
    save_history(history)
    print("💾 История успешно обновлена.")

if __name__ == "__main__":
    main()
