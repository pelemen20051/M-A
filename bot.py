import asyncio
import sqlite3
import smtplib
import re
from email.mime.text import MIMEText
from aiogram import Bot, Dispatcher, types
from aiogram.enums import ContentType
from aiogram.filters import Command
from aiogram.utils.keyboard import InlineKeyboardBuilder
from aiogram.types import LabeledPrice, PreCheckoutQuery

# ====== Настройки ======
TOKEN = "7960357519:AAF7wenxnXLtNEvzmPfSrRt71XM21TUNQUo"
PROVIDER_TOKEN = "381764678:TEST:149792" 
BARISTA_ID = 5751975391  
DB_PATH = "coffee_menu.db"
SMTP_EMAIL = "kazigasa28@gmail.com"
SMTP_PASSWORD = "-"

bot = Bot(token=TOKEN)
dp = Dispatcher()

# ====== Хранение email пользователей ======
user_emails = {}

# ====== Инициализация БД ======
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS menu (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category TEXT,
        name TEXT,
        volume TEXT,
        price TEXT
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cart (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        item_name TEXT,
        price INTEGER
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER,
        items TEXT,
        total INTEGER,
        status TEXT DEFAULT 'в обработке'
    )""")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS reviews (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        text TEXT
    )""")

    conn.commit()
    conn.close()


def get_menu():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT category, name, volume, price FROM menu")
    rows = cursor.fetchall()
    conn.close()

    menu = {}
    for category, name, volume, price in rows:
        item_name = f"{name} ({volume})" if volume else name
        if category not in menu:
            menu[category] = {}
        menu[category][item_name] = int(price.replace("р", ""))
    return menu

MENU = get_menu()

# ====== Email ======
def send_email(to_email, order_text):
    msg = MIMEText(order_text, "plain", "utf-8")
    msg["Subject"] = "Ваш чек из кофейни ☕"
    msg["From"] = SMTP_EMAIL
    msg["To"] = to_email
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
        server.login(SMTP_EMAIL, SMTP_PASSWORD)
        server.send_message(msg)

# ====== Клавиатуры ======
def main_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="☕ Меню", callback_data="menu")
    builder.button(text="💬 Отзывы", callback_data="reviews")
    builder.button(text="🛒 Корзина", callback_data="cart")
    builder.button(text="ℹ️ О нас", callback_data="about")
    builder.button(text="❓ Помощь", callback_data="help")
    builder.adjust(2, 2, 1)
    return builder.as_markup()

def menu_categories():
    builder = InlineKeyboardBuilder()
    for category in MENU.keys():
        builder.button(text=category, callback_data=f"category:{category}")
    builder.button(text="⬅️ Назад", callback_data="back")
    builder.adjust(2, 1)
    return builder.as_markup()

def category_items(category: str):
    builder = InlineKeyboardBuilder()
    for item_name, price in MENU[category].items():
        builder.button(text=f"{item_name} — {price}₽", callback_data=f"add:{category}:{item_name}")
    builder.button(text="⬅️ Назад", callback_data="menu")
    builder.adjust(1)
    return builder.as_markup()

def cart_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="💳 Оплатить", callback_data="pay")
    builder.button(text="🗑️ Очистить корзину", callback_data="clear_cart")
    builder.button(text="⬅️ Назад", callback_data="back")
    builder.adjust(1)
    return builder.as_markup()

def reviews_menu():
    builder = InlineKeyboardBuilder()
    builder.button(text="✍️ Написать отзыв", callback_data="write_review")
    builder.button(text="⬅️ Назад", callback_data="back")
    builder.adjust(1)
    return builder.as_markup()

# ====== Хэндлеры ======
@dp.message(Command("start"))
async def start(message: types.Message):
    await message.answer("Добро пожаловать в кофейню ☕\nВыберите пункт меню:", reply_markup=main_menu())

@dp.callback_query()
async def handle_callbacks(callback: types.CallbackQuery):
    data = callback.data
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    if data == "menu":
        await callback.message.edit_text("Выберите категорию:", reply_markup=menu_categories())

    elif data.startswith("category:"):
        category = data.split(":", 1)[1]
        await callback.message.edit_text(f"Категория: {category}", reply_markup=category_items(category))

    elif data.startswith("add:"):
        _, category, item_name = data.split(":")
        price = MENU[category][item_name]
        cursor.execute("INSERT INTO cart (user_id, item_name, price) VALUES (?, ?, ?)",
                       (callback.from_user.id, item_name, price))
        conn.commit()
        await callback.answer(f"✅ {item_name} добавлен в корзину!")

    elif data == "cart":
        cursor.execute("SELECT item_name, price FROM cart WHERE user_id=?", (callback.from_user.id,))
        items = cursor.fetchall()
        if not items:
            text = "🛒 Ваша корзина пуста."
        else:
            total = sum(price for _, price in items)
            text = "🛍 В корзине:\n" + "\n".join(f"• {item} — {price}₽" for item, price in items)
            text += f"\n\n💰 Итого: {total}₽"
        await callback.message.edit_text(text, reply_markup=cart_menu())

    elif data == "clear_cart":
        cursor.execute("DELETE FROM cart WHERE user_id=?", (callback.from_user.id,))
        conn.commit()
        await callback.message.edit_text("🧹 Корзина очищена!", reply_markup=cart_menu())

    elif data == "pay":
        await callback.message.answer("📧 Пожалуйста, введите ваш email для получения чека:")
        await bot.delete_message(callback.message.chat.id, callback.message.message_id)

    elif data == "reviews":
        cursor.execute("SELECT text FROM reviews")
        revs = cursor.fetchall()
        text = "💬 Пока нет отзывов." if not revs else "Отзывы гостей:\n\n" + "\n\n".join(f"• {r[0]}" for r in revs)
        await callback.message.edit_text(text, reply_markup=reviews_menu())

    elif data == "write_review":
        await callback.message.answer("✍️ Напишите ваш отзыв:")
        await bot.delete_message(callback.message.chat.id, callback.message.message_id)
        dp.message.register(review_handler)

    elif data in ["about", "help"]:
        text = "Наша кофейня предлагает лучшие напитки ☕!" if data == "about" else "Если есть вопросы, напишите нам 💬"
        await callback.message.edit_text(text, reply_markup=main_menu())

    elif data == "back":
        await callback.message.edit_text("Главное меню:", reply_markup=main_menu())

    # Бариста отмечает готовые заказы
    elif data.startswith("done:") and callback.from_user.id == BARISTA_ID:
        order_id = int(data.split(":")[1])
        cursor.execute("UPDATE orders SET status='готово' WHERE id=?", (order_id,))
        conn.commit()
        await callback.answer(f"Заказ #{order_id} отмечен как готовый ✅")
        await callback.message.edit_text(callback.message.text.replace("Статус: в обработке", "Статус: готово"))

    conn.close()

# ====== Сохранение email и отправка счета ======
@dp.message(lambda message: "@" in message.text and "." in message.text)
async def save_email(message: types.Message):
    user_emails[message.from_user.id] = message.text

    # Получаем корзину и формируем invoice
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT item_name, price FROM cart WHERE user_id=?", (message.from_user.id,))
    items = cursor.fetchall()
    total = sum(price for _, price in items)
    order_text = "\n".join(f"{item} — {price}₽" for item, price in items)
    conn.close()

    prices = [LabeledPrice(label="Ваш заказ", amount=total*100)]
    await bot.send_invoice(
        chat_id=message.chat.id,
        title="Заказ из кофейни ☕",
        description=order_text,
        provider_token=PROVIDER_TOKEN,
        currency="RUB",
        prices=prices,
        payload=f"order_{message.from_user.id}"
    )

# ====== Предварительная проверка платежа ======
@dp.pre_checkout_query()
async def checkout(pre_checkout_query: PreCheckoutQuery):
    await bot.answer_pre_checkout_query(pre_checkout_query.id, ok=True)

from aiogram import F

# ====== Обработка успешной оплаты ======
@dp.message(F.successful_payment)
async def got_payment(message: types.Message):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT item_name, price FROM cart WHERE user_id=?", (message.from_user.id,))
    items = cursor.fetchall()
    total = sum(price for _, price in items)
    order_text = "\n".join(f"{item} — {price}₽" for item, price in items)

    cursor.execute("INSERT INTO orders (user_id, items, total) VALUES (?, ?, ?)",
                   (message.from_user.id, order_text, total))
    cursor.execute("DELETE FROM cart WHERE user_id=?", (message.from_user.id,))
    conn.commit()
    conn.close()

    await message.answer("✅ Оплата получена! Ваш заказ передан баристе ☕")
    await bot.send_message(BARISTA_ID, f"🆕 Новый заказ:\n{order_text}\n💰 Итого: {total}₽\nСтатус: в обработке")

    email = user_emails.get(message.from_user.id)
    if email:
        send_email(email, f"Спасибо за заказ!\n\n{order_text}\n💰 Итого: {total}₽")
        await message.answer(f"📧 Чек отправлен на ваш email: {email}")
    else:
        await message.answer("⚠️ Не указан email, чек отправить не удалось.")


# ====== Отзывы ======
async def review_handler(message: types.Message):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO reviews (text) VALUES (?)", (message.text,))
    conn.commit()
    conn.close()
    await message.answer("✅ Спасибо за отзыв!", reply_markup=main_menu())
    dp.message.unregister(review_handler)

# ====== Бариста: список заказов ======
@dp.message(lambda message: message.from_user.id == BARISTA_ID)
async def barista_orders(message: types.Message):
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT id, items, total, status FROM orders ORDER BY id DESC")
    orders = cursor.fetchall()
    conn.close()

    if not orders:
        await message.answer("📭 Заказов пока нет.")
        return

    for order_id, items, total, status in orders:
        text = f"Заказ #{order_id}\n{items}\n💰 Итого: {total}₽\nСтатус: {status}"
        builder = InlineKeyboardBuilder()
        if status != "готово":
            builder.button(text="✅ Готово", callback_data=f"done:{order_id}")
        builder.adjust(1)
        await message.answer(text, reply_markup=builder.as_markup())

# ====== Запуск ======
async def main():
    init_db()
    print("🤖 Бот запущен...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
