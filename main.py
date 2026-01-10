import os
import time
import re
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright

# --- НАСТРОЙКИ ---

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')import os
import time
import re
from datetime import datetime
import requests
from playwright.sync_api import sync_playwright
from supabase import create_client, Client

# --- КОНФИГУРАЦИЯ ---

TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_CHANNEL_ID = os.getenv('TELEGRAM_CHANNEL_ID')
SUPABASE_URL = os.getenv('SUPABASE_URL')
SUPABASE_KEY = os.getenv('SUPABASE_KEY')

# Настройка списков (как ты просил ранее)
CITIES_FROM = [
    "Москва", "Санкт-Петербург", "Екатеринбург", "Казань", 
    "Новосибирск", "Сочи", "Уфа", "Самара"
]

# Словарь: Название -> Slug для URL
COUNTRIES_TO = {
    "Турция": "turkey",
    "Египет": "egypt",
    "ОАЭ": "united-arab-emirates",
    "Таиланд": "thailand",
    "Шри-Ланка": "sri-lanka",
    "Куба": "cuba",
    "Мальдивы": "maldives",
}

# Длительность ночей
DURATIONS = [6, 7, 9, 10]

# --- ИНИЦИАЛИЗАЦИЯ SUPABASE ---
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception as e:
        print(f"❌ Ошибка Supabase: {e}")

# --- ФУНКЦИИ ---

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except:
        pass

def get_last_price(city, country, duration):
    """
    Получает последнюю записанную цену из базы для сравнения.
    """
    if not supabase:
        return None
    
    try:
        # Ищем последнюю запись для этого маршрута и длительности
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
        print(f"   ⚠️ Ошибка чтения из БД: {e}")
    
    return None

def save_price_to_db(city, country, duration, price, date_found):
    """
    Сохраняет новую цену в базу.
    """
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
        print(f"   💾 Сохранено в БД (id обновлен)")
    except Exception as e:
        print(f"   ❌ Не удалось сохранить в БД: {e}")

def check_route(page, city_from, country_name, country_slug, duration):
    print(f"🔄 {city_from} -> {country_name} ({duration} н.)")

    # Формируем URL с фильтрами
    # start_from=City
    # nights_from=X & nights_to=X (жесткий фильтр ночей)
    url = (
        f"https://www.onlinetours.ru/tours/{country_slug}"
        f"?start_from={city_from}"
        f"&nights_from={duration}&nights_to={duration}"
    )

    try:
        page.goto(url, timeout=45000)
        
        # Стехический клик в "Куда", чтобы сбить фокус (иногда помогает от попапов)
        try:
            page.locator("body").click(position={"x": 10, "y": 10})
        except:
            pass

        # Ждем загрузки цен. Используем "грязный" метод поиска по всему тексту,
        # так как он показал себя самым надежным.
        time.sleep(4) 
        
        # Скачиваем весь текст страницы
        content = page.content()
        
        # Ищем цены: "12 300 ₽"
        # Регулярка ищет число перед символом рубля
        matches = re.findall(r'(\d[\d\s]*)\s?₽', content)
        
        valid_prices = []
        for m in matches:
            clean = int(re.sub(r'\s+', '', m))
            # Фильтр: цена не может быть 500р и вряд ли 1 млн (хотя бывает, но для минимума пойдет)
            if clean > 10000 and clean < 1000000:
                valid_prices.append(clean)
        
        if not valid_prices:
            print("   ⚠️ Цены не найдены.")
            return

        min_price = min(valid_prices)
        print(f"   ✅ Найдена цена: {min_price} руб.")

        # --- ЛОГИКА СРАВНЕНИЯ И УВЕДОМЛЕНИЯ ---
        
        # 1. Получаем старую цену
        last_price = get_last_price(city_from, country_name, duration)
        
        # 2. Определяем дату (пока заглушка или пытаемся найти в URL/странице)
        # На странице календаря сложно выцепить точную дату самого дешевого тура без сложного парсинга DOM.
        # Для простоты пока пишем "См. календарь" или текущий месяц.
        date_found = datetime.now().strftime("%d.%m.%Y") # Дата обнаружения

        # 3. Сохраняем НОВУЮ цену в любом случае (для истории графика цен)
        save_price_to_db(city_from, country_name, duration, min_price, date_found)

        # 4. Проверяем, надо ли слать уведомление
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
                print("   🔔 Отправляю уведомление (цена упала)")
                send_telegram_message(msg)
            else:
                print(f"   ℹ️ Цена не упала (Старая: {last_price}, Новая: {min_price})")
        else:
            # Если записи в базе нет (первый запуск), можно отправить приветственное сообщение
            # Или промолчать. Давай отправим, чтобы ты видел, что база заполняется.
            msg = (
                f"🆕 <b>Новое направление в базе</b>\n"
                f"✈️ {city_from} -> {country_name}\n"
                f"🌙 {duration} ночей\n"
                f"💰 <b>{min_price:,} руб.</b>\n"
                f"🔗 <a href='{url}'>Смотреть тур</a>"
            )
            print("   🔔 Отправляю уведомление (первая запись)")
            send_telegram_message(msg)

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")

def main():
    print(f"🚀 Запуск мониторинга VOLAGO: {datetime.now()}")
    
    with sync_playwright() as p:
        # Запуск с Anti-Detect флагами
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
        # Скрываем webdriver
        context.add_init_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined});")
        
        page = context.new_page()

        # ГЛАВНЫЙ ЦИКЛ
        for city in CITIES_FROM:
            for country_name, country_slug in COUNTRIES_TO.items():
                for duration in DURATIONS:
                    
                    check_route(page, city, country_name, country_slug, duration)
                    
                    # Пауза, чтобы не забанили (важно при большом количестве запросов)
                    time.sleep(3) 

        browser.close()

if __name__ == "__main__":
    main()

CITIES_FROM = ["Москва"] 
# Пока пробуем Турцию и Египет, чтобы проверить стабильность
COUNTRIES_TO = ["Турция", "Египет"]

def send_telegram_message(text):
    if not TELEGRAM_BOT_TOKEN:
        return
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    payload = {"chat_id": TELEGRAM_CHANNEL_ID, "text": text, "parse_mode": "HTML"}
    try:
        requests.post(url, json=payload, timeout=10)
    except Exception as e:
        print(f"❌ Ошибка отправки в Telegram: {e}")

def check_prices_smart(page, city_from, country_to):
    print(f"🔄 Проверка: {city_from} -> {country_to}")
    
    try:
        # 1. Заходим на главную
        page.goto("https://www.onlinetours.ru/", timeout=60000)
        
        # ДИАГНОСТИКА
        print(f"   👀 Заголовок: '{page.title()}'")
        
        # Ждем поле поиска
        try:
            # Ищем input с placeholder, содержащим "Страна"
            # state="attached" значит "существует в коде", даже если скрыт
            page.wait_for_selector("input[placeholder*='Страна']", state="attached", timeout=15000)
        except:
            print("   ⚠️ Не нашел поле поиска за 15 сек.")
            return None

        # --- ШАГ 1: ВВОДИМ "КУДА" ---
        dest_input = page.locator("input[placeholder*='Страна']")
        
        # МАГИЯ ЗДЕСЬ: force=True пробивает любые перекрытия
        dest_input.click(force=True)
        
        # Очищаем поле на всякий случай
        dest_input.fill("")
        time.sleep(0.5)
        # Печатаем страну
        dest_input.type(country_to, delay=100)
        time.sleep(2) # Ждем пока всплывет подсказка
        
        # Жмем Enter
        page.keyboard.press("Enter")
        time.sleep(1)

        # --- ШАГ 2: КЛИКАЕМ НА ДАТУ/КАЛЕНДАРЬ ---
        print("   📅 Пытаюсь открыть календарь...")
        
        # Пробуем разные варианты клика по дате, так как там часто сложная верстка
        # Вариант А: По классу
        try:
            page.locator(".SearchPanel-date").click(force=True, timeout=2000)
        except:
            # Вариант Б: Если не вышло, ищем элемент с текстом даты (обычно там сегодняшнее число или месяц)
            # Просто кликаем по координатам правее поля ввода страны (грубый хак)
            print("   ⚠️ Клик по классу не прошел, пробую по координатам...")
            box = dest_input.bounding_box()
            if box:
                # Кликаем на 300 пикселей правее поля ввода страны (там обычно дата)
                page.mouse.click(box['x'] + box['width'] + 50, box['y'] + 10)
        
        time.sleep(3) # Ждем открытия календаря

        # --- ШАГ 3: ЧИТАЕМ ЦЕНЫ ---
        # Сначала проверим, открылся ли календарь. Ищем элемент с ценой (содержит ₽)
        
        content = page.content() # Берем весь HTML
        # Ищем цены регуляркой прямо в HTML, чтобы не зависеть от скрытых элементов
        # Ищем паттерн: >45 000 ₽< или похожие
        
        # Ищем все цифры перед знаком рубля
        found_prices = re.findall(r'(\d[\d\s]*)\s?₽', content)
        
        valid_prices = []
        for p in found_prices:
            # Удаляем пробелы
            clean = int(re.sub(r'\s+', '', p))
            # Фильтр адекватности (цена тура не может быть 500 рублей и вряд ли 5 млн для теста)
            if clean > 10000 and clean < 800000:
                valid_prices.append(clean)
        
        if valid_prices:
            min_price = min(valid_prices)
            print(f"   ✅ Нашел цены: {len(valid_prices)} шт. Мин: {min_price}")
            return min_price
        else:
            print(f"   ⚠️ Цены не найдены. Найдено сырых совпадений: {len(found_prices)}")
            # Если не нашли, выведем кусок текста для отладки
            return None

    except Exception as e:
        print(f"   ❌ Ошибка: {e}")
        return None

def main():
    print(f"🚀 Запуск STEALTH-парсера Onlinetours (FORCE MODE): {datetime.now()}")
    
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
        
        # Скрипт-невидимка
        context.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', {
                get: () => undefined
            });
        """)
        
        page = context.new_page()

        for city in CITIES_FROM:
            for country in COUNTRIES_TO:
                price = check_prices_smart(page, city, country)
                
                if price:
                    msg = (
                        f"🔥 <b>Onlinetours (Найден тур):</b>\n"
                        f"✈️ {city} -> {country}\n"
                        f"💰 <b>от {price:,} руб.</b>\n"
                        f"📅 Проверьте сайт, цена из календаря!"
                    )
                    send_telegram_message(msg)
                
                time.sleep(5) 

        browser.close()

if __name__ == "__main__":
    main()
