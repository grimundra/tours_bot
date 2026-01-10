import time
import re
import requests
from datetime import datetime, timedelta
from playwright.sync_api import sync_playwright
from supabase import create_client, Client

# --- КОНФИГУРАЦИЯ ---
SUPABASE_URL = "ТВОЙ_SUPABASE_URL"
SUPABASE_KEY = "ТВОЙ_SUPABASE_SERVICE_ROLE_KEY"
TG_BOT_TOKEN = "ТВОЙ_TG_TOKEN"
TG_CHAT_ID = "ТВОЙ_CHAT_ID"

# Инициализация Supabase
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Направления (Словарь: Город вылета -> Список направлений)
# Можно расширять
ROUTES = {
    "Москва": ["Дубай", "ОАЭ", "Таиланд", "Турция"],
    "Санкт-Петербург": ["ОАЭ", "Турция"]
}

DURATIONS = [7, 10] # Сколько ночей смотреть

def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_BOT_TOKEN}/sendMessage"
    try:
        requests.post(url, json={"chat_id": TG_CHAT_ID, "text": text, "parse_mode": "Markdown"})
    except Exception as e:
        print(f"Ошибка отправки в TG: {e}")

def check_history_and_alert(origin, dest, duration, current_price, date_found):
    """
    Смотрит цены за последние 3 дня в базе.
    Если текущая цена ниже средней хотя бы на 1% — шлет алерт.
    """
    three_days_ago = (datetime.utcnow() - timedelta(days=3)).isoformat()
    
    # Запрос к Supabase: берем цены по этому маршруту за 3 дня
    response = supabase.table("tour_prices") \
        .select("min_price") \
        .eq("origin_city", origin) \
        .eq("destination", dest) \
        .eq("duration", duration) \
        .gte("created_at", three_days_ago) \
        .execute()
    
    history = [item['min_price'] for item in response.data]
    
    # Логика анализа
    if not history:
        print(f"  -> Первая запись для {dest}, просто сохраняем.")
        return

    avg_price = sum(history) / len(history)
    
    # Условие: Текущая цена < Средней * 0.99 (то есть ниже на 1%)
    if current_price < (avg_price * 0.99):
        drop_percent = round((1 - current_price / avg_price) * 100, 1)
        msg = (
            f"🔥 **Цена упала на {drop_percent}%!**\n"
            f"✈️ {origin} -> {dest} ({duration} н.)\n"
            f"💰 Сейчас: **{current_price} ₽** (Вылет: {date_found})\n"
            f"📊 Средняя (3 дня): {int(avg_price)} ₽"
        )
        send_telegram(msg)
        print(f"  -> АЛЕРТ ОТПРАВЛЕН! Цена {current_price} ниже средней {avg_price}")
    else:
        print(f"  -> Цена обычная. Текущая: {current_price}, Средняя: {int(avg_price)}")

def run_scanner():
    with sync_playwright() as p:
        # headless=True, чтобы браузер не мешал (работал в фоне)
        browser = p.chromium.launch(headless=False) 
        page = browser.new_page()
        
        # Чтобы сайт думал, что мы человек
        page.set_extra_http_headers({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36..."})

        for origin, destinations in ROUTES.items():
            for dest in destinations:
                for nights in DURATIONS:
                    try:
                        print(f"🔎 Проверяем: {origin} -> {dest}, {nights} ночей")
                        
                        page.goto("https://onlinetours.ru/", timeout=60000)
                        
                        # --- ЛОГИКА ВЗАИМОДЕЙСТВИЯ С САЙТОМ (ПРИМЕРНАЯ) ---
                        # 1. Ввод города вылета
                        # Тебе нужно найти актуальные селекторы input'ов
                        # page.fill("input[name='start_from']", origin)
                        # page.click(f"text={origin}")
                        
                        # 2. Ввод направления (Дубай/ОАЭ)
                        # page.fill("input[name='country']", dest)
                        # page.wait_for_selector(".autocomplete-result")
                        # page.click(".autocomplete-result:first-child") 
                        
                        # 3. Выбор длительности (nights)
                        # ... клики по дропдауну длительности ...
                        
                        # 4. Открытие календаря цен
                        # page.click(".datepicker-trigger")
                        # page.wait_for_selector(".day-price-value") # Ждем загрузки цифр

                        # --- ЭМУЛЯЦИЯ ПОЛУЧЕНИЯ ЦЕНЫ (Тут будет твой парсинг) ---
                        # Допустим, мы спарсили цены со страницы
                        # prices_elements = page.query_selector_all(".day-price-value")
                        # real_prices = [int(el.inner_text().replace(" ", "")) for el in prices_elements]
                        # min_price = min(real_prices)
                        
                        # --- ЗАГЛУШКА ДЛЯ ТЕСТА (Удали это, когда настроишь селекторы) ---
                        import random
                        min_price = random.randint(40000, 60000) 
                        date_found = "25.10"
                        time.sleep(2)
                        # --------------------------------------------------------

                        # 5. Сохранение в Supabase
                        data = {
                            "origin_city": origin,
                            "destination": dest,
                            "duration": nights,
                            "min_price": min_price,
                            "departure_date_found": date_found
                        }
                        supabase.table("tour_prices").insert(data).execute()
                        
                        # 6. Проверка на скидку
                        check_history_and_alert(origin, dest, nights, min_price, date_found)

                    except Exception as e:
                        print(f"❌ Ошибка на маршруте {origin}-{dest}: {e}")
                        # Делаем скриншот ошибки для отладки
                        page.screenshot(path=f"error_{origin}_{dest}.png")
        
        browser.close()

if __name__ == "__main__":
    print("🚀 Запуск сканера цен...")
    run_scanner()
    print("✅ Готово.")
