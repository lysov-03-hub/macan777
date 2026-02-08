import telebot
from telebot.types import InlineKeyboardMarkup, InlineKeyboardButton
import requests
from bs4 import BeautifulSoup
import time

# Замени на свой токен и ID канала
BOT_TOKEN = '8427230038:AAGZU6qfHMPpeQEH-9wYaggOu0vvc0MeMHk'
CHANNEL_ID = '-1002974116062'  # Например, -1001234567890

bot = telebot.TeleBot(BOT_TOKEN)

# Функция для парсинга страницы товара
import json
from bs4 import BeautifulSoup, Tag

def parse_product(url):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/132.0.0.0 Safari/537.36',
        'Accept-Language': 'ru-RU,ru;q=0.9,en;q=0.8',
        'Referer': 'https://market.yandex.ru/'
    }
    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()  # если 403/429 — покажет ошибку
    except Exception as e:
        print(f"Ошибка запроса: {e}")
        return None

    soup = BeautifulSoup(response.text, 'html.parser')

    # 1. Пробуем вытащить из JSON-LD (самый надёжный способ сейчас)
    title = 'Название не найдено'
    price = 'Цена не найдена'
    description = 'Описание не найдено'

    scripts = soup.find_all('script', type='application/ld+json')
    for script in scripts:
        try:
            data = json.loads(script.string)
            if isinstance(data, dict):
                if 'name' in data:
                    title = data['name'].strip()
                if 'description' in data:
                    description = data['description'].strip()[:250] + '...'
                if 'offers' in data:
                    offers = data['offers']
                    if isinstance(offers, dict) and 'price' in offers:
                        price = f"{offers['price']} ₽"
                    elif isinstance(offers, list) and offers:
                        price = f"{offers[0].get('price', 'Неизвестно')} ₽"
        except json.JSONDecodeError:
            pass

    # 2. Если JSON не дал — fallback на HTML-селекторы (актуальные на 2026)
    if title == 'Название не найдено':
        title_tag = (
            soup.select_one('h1[data-auto="product-title"]') or
            soup.select_one('h1[class*="title"]') or
            soup.select_one('h1') or
            soup.select_one('[data-baobab-name="title"] h1')
        )
        if title_tag:
            title = title_tag.get_text(strip=True)

    if price == 'Цена не найдена':
        price_tag = (
            soup.select_one('[data-auto*="price-current"]') or
            soup.select_one('span[data-auto*="price"]') or
            soup.select_one('[class*="price"][class*="current"]') or
            soup.select_one('span[class*="price"]') or
            soup.find(lambda tag: tag.name in ['span', 'div'] and '₽' in tag.get_text() and len(tag.get_text(strip=True)) > 5)
        )
        if price_tag:
            price = price_tag.get_text(strip=True).replace('\xa0', ' ')

    if description == 'Описание не найдено':
        desc_tag = (
            soup.select_one('[data-auto="snippet-description"]') or
            soup.select_one('div[class*="description"]') or
            soup.select_one('ul[class*="characteristics"]') or
            soup.select_one('div[data-baobab-name="description"]') or
            soup.find('div', class_=lambda c: c and ('tech' in c or 'spec' in c or 'props' in c))
        )
        if desc_tag:
            description = ' '.join([li.get_text(strip=True) for li in desc_tag.find_all(['li', 'p', 'span']) if li.get_text(strip=True)])[:250] + '...'

    # 3. Картинка (обычно работает стабильно)
    image_url = None
    img_tag = (
        soup.select_one('img[class*="mainPic"]') or
        soup.select_one('img[data-auto="mainImage"]') or
        soup.select_one('meta[property="og:image"]') or
        soup.select_one('img[src*="cdn"]')
    )
    if img_tag:
        image_url = img_tag.get('src') or img_tag.get('content')
        if image_url and not image_url.startswith('http'):
            image_url = 'https:' + image_url

    print(f"DEBUG: title={title}, price={price}, desc={description[:100]}...")  # для отладки в консоли

    return {
        'title': title,
        'price': price,
        'description': description,
        'image_url': image_url,
        'ref_url': url
    }

# Функция для поиска товаров (простой поиск через Яндекс Маркет)
def search_products(query):
    search_url = f'https://market.yandex.ru/search?text={query.replace(" ", "%20")}'
    headers = {'User-Agent': 'Mozilla/5.0'}
    response = requests.get(search_url, headers=headers)
    soup = BeautifulSoup(response.text, 'html.parser')
    
    results = []
    items = soup.find_all('div', {'data-zone-name': 'snippet-cell'}, limit=3)
    for item in items:
        link = item.find('a', {'data-zone-name': 'title-link'}).get('href') if item.find('a', {'data-zone-name': 'title-link'}) else None
        if link:
            full_link = f'https://market.yandex.ru{link}'  # Добавь свой ref: + '&ref=your_id'
            results.append(full_link)
    return results

# Обработчик сообщений (ссылки)
@bot.message_handler(func=lambda message: 'market.yandex.ru' in message.text)
def handle_link(message):
    url = message.text.strip()
    product = parse_product(url)
    if not product:
        bot.reply_to(message, 'Не удалось извлечь данные. Проверь ссылку.')
        return
    
    # Создаём красивую карточку
    caption = f"🔥 **{product['title']}**\n\n" \
          f"{product['description']}\n\n" \
          f"💰 Цена: **{product['price']}**\n\n" \
          f"Купить 👉 [Перейти в Яндекс Маркет]({product['ref_url']})"
    
    # Кнопка для покупки
    markup = InlineKeyboardMarkup()
    markup.add(InlineKeyboardButton("Купить по реф-ссылке", url=product['ref_url']))
    
    # Отправляем в канал с фото
    if product['image_url']:
        bot.send_photo(CHANNEL_ID, product['image_url'], caption=caption, parse_mode='Markdown', reply_markup=markup)
    else:
        bot.send_message(CHANNEL_ID, caption, parse_mode='Markdown', reply_markup=markup)
    
    bot.reply_to(message, 'Карточка отправлена в канал!')

# Команда для поиска
@bot.message_handler(commands=['search'])
def handle_search(message):
    query = message.text.replace('/search', '').strip()
    if not query:
        bot.reply_to(message, 'Укажи запрос, например: /search iphone 14')
        return
    
    results = search_products(query)
    if not results:
        bot.reply_to(message, 'Ничего не найдено.')
        return
    
    response = 'Найденные товары (добавь свой ref в ссылки):\n'
    for i, link in enumerate(results, 1):
        response += f"{i}. {link}\n"
    bot.reply_to(message, response)

# Старт бота
@bot.message_handler(commands=['start'])
def start(message):
    bot.reply_to(message, 'Привет! Пришли реферальную ссылку на товар с Яндекс Маркета, или используй /search <запрос> для поиска.')

if __name__ == '__main__':
    while True:
        try:
            bot.polling(none_stop=True)
        except Exception as e:
            print(e)
            time.sleep(5)
input("Нажми Enter для выхода...")