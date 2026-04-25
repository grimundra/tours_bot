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

# --- ЖЕСТКИЕ ЛИМИТЫ ЦЕН ---
MAX_PRICES = {
    "Москва": {"Турция": 50000, "Египет": 60000, "ОАЭ": 70000, "Таиланд": 120000, "Дубай": 80000, "Китай": 110000, "Вьетнам": 115000, "Мальдивы": 160000, "Шри-Ланка": 110000, "Стамбул": 60000, "Куба": 150000},
    "Санкт-Петербург": {"Турция": 60000, "Египет": 80000, "ОАЭ": 70000, "Таиланд": 120000, "Дубай": 80000, "Китай": 130000, "Вьетнам": 130000, "Мальдивы": 200000, "Шри-Ланка": 150000, "Стамбул": 70000, "Куба": 150000},
    "Екатеринбург": {"Турция": 70000, "Египет": 80000, "ОАЭ": 70000, "Таиланд": 120000, "Дубай": 70000, "Китай": 130000, "Вьетнам": 130000, "Мальдивы": 200000, "Шри-Ланка": 160000, "Стамбул": 80000, "Куба": 200000},
    "Сочи": {"Турция": 40000, "Египет": 50000, "ОАЭ": 60000, "Таиланд": 120000, "Дубай": 70000, "Китай": 150000, "Вьетнам": 150000, "Мальдивы": 200000, "Шри-Ланка": 160000, "Стамбул": 50000, "Куба": 200000},
    "Самара": {"Турция": 50000, "Египет": 80000, "ОАЭ": 80000, "Таиланд": 130000, "Дубай": 80000, "Китай": 130000, "Вьетнам": 140000, "Мальдивы": 200000, "Шри-Ланка": 160000, "Стамбул": 70000, "Куба": 200000},
    "Нижний Новгород": {"Турция": 50000, "Египет": 80000, "ОАЭ": 80000, "Таиланд": 130000, "Дубай": 80000, "Китай": 130000, "Вьетнам": 140000, "Мальдивы": 200000, "Шри-Ланка": 160000, "Стамбул": 70000, "Куба": 200000},
    "Тюмень": {"Турция": 90000, "Египет": 100000, "ОАЭ": 90000, "Таиланд": 150000, "Дубай": 90000, "Китай": 130000, "Вьетнам": 140000, "Мальдивы": 200000, "Шри-Ланка": 160000, "Стамбул": 100000, "Куба": 200000},
    "Новосибирск": {"Турция": 75000, "Египет": 100000, "ОАЭ": 90000, "Таиланд": 110000, "Дубай": 100000, "Китай": 130000, "Вьетнам": 115000, "Мальдивы": 200000, "Шри-Ланка": 150000, "Стамбул": 85000, "Куба": 200000},
    "Краснодар": {"Турция": 50000, "Египет": 80000, "ОАЭ": 70000, "Таиланд": 140000, "Дубай": 80000, "Китай": 140000, "Вьетнам": 150000, "Мальдивы": 200000, "Шри-Ланка": 150000, "Стамбул": 60000, "Куба": 200000},
    "Владивосток": {"Турция": 150000, "Египет": 200000, "ОАЭ": 150000, "Таиланд": 140000, "Дубай": 150000, "Китай": 90000, "Вьетнам": 85000, "Мальдивы": 200000, "Шри-Ланка": 200000, "Стамбул": 150000, "Куба": 200000},
    "Иркутск": {"Турция": 150000, "Египет": 150000, "ОАЭ": 150000, "Таиланд": 110000, "Дубай": 150000, "Китай": 110000, "Вьетнам": 120000, "Мальдивы": 200000, "Шри-Ланка": 170000, "Стамбул": 150000, "Куба": 200000}
}
# Дублируем Самару для Казани и Уфы
MAX_PRICES["Казань"] = MAX_PRICES["Самара"]
MAX_PRICES["Уфа"] = MAX_PRICES["Самара"]

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

        # 🛑 ВАЖНО: Даем сайту 1 секунду на анимацию открытия календаря
        # и старт запроса к API за ценами
        time.sleep(1)

        # ==========================================
        # ШАГ 4: ЦЕНЫ
        # ==========================================
        try:
            # Увеличил таймаут до 8 секунд (8000 мс) на случай долгих ответов
            page.wait_for_selector(".text-emerald-600", state="visible", timeout=8000)
            
            # 🛑 ВАЖНО: Цены появились, но даем еще полсекунды, 
            # чтобы все элементы точно добавились в DOM перед чтением
            time.sleep(0.5)
        except:
            # Расскомментируй print, чтобы видеть, где именно он не находит цены
            # print("   ⚠️ Цены в календаре не появились, пропускаю.")
            return

        prices_elements = page.locator(".text-emerald-600").all_inner_texts()
        valid_prices = []
        for p in prices_elements:
            clean = re.sub(r'[^0-9]', '', p)
            if clean:
                val = int(clean)
                if val > 10000: valid_prices.append(val)
        
        if not valid_prices: return

        # ==========================================
        # ШАГ 5: СРАВНЕНИЕ, ЛИМИТЫ И ОТПРАВКА
        # ==========================================
        
        # 1. Проверяем жесткий лимит (отсекаем мусор)
        max_allowed = MAX_PRICES.get(target_city, {}).get(target_country)
        
        if max_allowed and min_price > max_allowed:
            # print(f"   🛑 Дорого: {min_price} руб. (Лимит: {max_allowed}). Игнорируем.")
            return

        print(f"   ✅ НАЙДЕНО: {min_price} руб. (Прошло лимит {max_allowed})")
        
        flag = FLAGS.get(target_country, "🏳️")
        old_price = history.get(history_key)
        
        should_send = False
        status_text = ""
        
        # 2. Логика сравнения с историей
        if old_price is None:
            status_text = "🆕 <b>Новое направление</b>"
            should_send = True
            
        elif min_price < old_price:
            diff = old_price - min_price
            status_text = f"📉 <b>Цена СНИЗИЛАСЬ на {diff:,} руб.</b>"
            should_send = True
            
        elif min_price == old_price:
            status_text = "🟰 <b>Цена не изменилась</b>"
            should_send = True
            
        else:
            diff = min_price - old_price
            # print(f"   📈 Цена выросла на {diff} руб. В канал НЕ отправляем.")
            should_send = False

        # 3. Отправка в Телеграм только при прохождении фильтров
        if should_send:
            msg = (
                f"{flag} <b>{target_country}</b>\n"
                f"🛫 Вылет: {target_city}\n"
                f"💰 <b>{min_price:,} руб.</b>\n"
                f"{status_text}"
            )
            send_telegram_message(msg)
        
        # Обновляем историю в любом случае! Бот должен знать текущую реальную цену
        history[history_key] = min_price

    except Exception as e:
        print(f"   ❌ Ошибка в run_search: {e}")

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
