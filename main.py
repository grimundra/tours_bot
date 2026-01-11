import os
import time
from datetime import datetime
from playwright.sync_api import sync_playwright

def main():
    print(f"📸 ЗАПУСК ФОТО-ОТЧЕТА: {datetime.now()}")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=['--disable-blink-features=AutomationControlled', '--no-sandbox', '--disable-setuid-sandbox']
        )
        # Ставим большое разрешение, чтобы все влезло
        context = browser.new_context(viewport={'width': 1280, 'height': 800})
        page = context.new_page()

        try:
            # 1. ЗАГРУЗКА
            print("1. Переход на сайт...")
            page.goto("https://www.onlinetours.ru/", timeout=60000)
            time.sleep(3)
            print(f"   Заголовок: {page.title()}")
            page.screenshot(path="01_homepage.png")
            print("   📸 Снято: 01_homepage.png")

            # 2. ВВОД СТРАНЫ
            print("2. Ввод страны 'Турция'...")
            try:
                # Клик по центру экрана, чтобы убрать возможные баннеры
                page.mouse.click(640, 400)
                
                input_field = page.locator("input[placeholder*='Страна']")
                input_field.click(force=True)
                input_field.fill("Турция")
                time.sleep(2)
                page.keyboard.press("Enter")
                time.sleep(2)
            except Exception as e:
                print(f"   Ошибка ввода: {e}")
            
            page.screenshot(path="02_country_input.png")
            print("   📸 Снято: 02_country_input.png")

            # 3. ПОПЫТКА ОТКРЫТЬ КАЛЕНДАРЬ
            print("3. Открытие календаря...")
            try:
                # Пробуем кликнуть на кнопку даты
                date_btn = page.locator(".SearchPanel-date, .search-panel-date").first
                date_btn.click(force=True)
                time.sleep(5) # Ждем прогрузки
            except Exception as e:
                print(f"   Ошибка клика: {e}")

            page.screenshot(path="03_calendar_open.png")
            print("   📸 Снято: 03_calendar_open.png")

            # 4. ПРОВЕРКА ЦЕН (HTML DUMP)
            # Сохраним еще и код страницы, чтобы поискать цены текстом
            with open("page_source.html", "w", encoding="utf-8") as f:
                f.write(page.content())
            print("   📄 Сохранен код страницы: page_source.html")

        except Exception as e:
            print(f"❌ КРИТИЧЕСКАЯ ОШИБКА: {e}")
        finally:
            browser.close()
            print("✅ Работа завершена.")

if __name__ == "__main__":
    main()
