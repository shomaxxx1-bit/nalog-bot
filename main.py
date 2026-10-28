import asyncio
import os
import json
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F
from aiogram.filters import Command, CommandStart
from aiogram.types import (
    Message, ReplyKeyboardMarkup, KeyboardButton,
    PreCheckoutQuery, LabeledPrice, BotCommand,
    InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery,
)
from aiogram.methods import SetMyCommands

DATA_FILE = "bot_data.json"
FREE_CHECKS = 3
SUB_PRICE_STARS = 75
SUB_DAYS = 30
REF_SUB_DAYS = 30
REMINDER_DAYS = (25, 26, 27, 28)   # числа месяца, когда шлём напоминание
REMINDER_HOUR = 10                 # час по серверу, когда шлём напоминание

# Токен: сначала переменная окружения BOT_TOKEN, затем значение из кода (для хостингов без env-переменных)
BOT_TOKEN = os.environ.get("BOT_TOKEN") or "ВСТАВЬТЕ_ТОКЕН_СЮДА"

# ---------- хранилище ----------

def load_data():
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}

def dump(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=1)

DATA = load_data()

def user(uid):
    return DATA.setdefault(str(uid), {
        "type": None, "checks_used": 0, "bonus": 0,
        "sub_until": None, "history": [], "ref": None,
        "sent_reminders": {},
    })

def sub_active(u):
    return bool(u.get("sub_until")) and datetime.fromisoformat(u["sub_until"]) > datetime.now()

def add_sub_days(u, days):
    base = datetime.fromisoformat(u["sub_until"]) if sub_active(u) else datetime.now()
    u["sub_until"] = (base + timedelta(days=days)).isoformat()

def checks_left(u):
    if sub_active(u):
        return 999
    return max(0, FREE_CHECKS + u.get("bonus", 0) - u.get("checks_used", 0))

# ---------- клавиатура ----------

start_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🧮 Рассчитать налог")],
        [KeyboardButton(text="📄 Подготовить чек"), KeyboardButton(text="⭐ Подписка")],
        [KeyboardButton(text="📊 Мой статус"), KeyboardButton(text="🎁 Пригласить друга")],
        [KeyboardButton(text="🔄 Выбрать тип")],
    ],
    resize_keyboard=True,
    input_field_placeholder="Выберите действие или напишите сумму",
)

type_kb = InlineKeyboardMarkup(
    inline_keyboard=[
        [
            InlineKeyboardButton(text="Физлицо 4%", callback_data="type_физ"),
            InlineKeyboardButton(text="Юрлицо 6%", callback_data="type_юр"),
        ]
    ]
)

commands = [
    BotCommand(command="start", description="Начать работу"),
    BotCommand(command="nalog", description="Рассчитать налог НПД"),
    BotCommand(command="check", description="Подготовить текст чека"),
    BotCommand(command="subscribe", description="Подписка и лимиты"),
    BotCommand(command="status", description="Мой статус и остаток чеков"),
    BotCommand(command="type", description="Тип: физлицо 4% / юрлицо 6%"),
    BotCommand(command="ref", description="Пригласить друга — месяц подписки обоим"),
    BotCommand(command="help", description="Что умеет бот"),
]

# ---------- бот ----------

bot = Bot(BOT_TOKEN)
dp = Dispatcher()


@dp.message(CommandStart())
async def start_cmd(message: Message):
    payload = message.text.split(maxsplit=1)[1] if message.text and len(message.text.split()) > 1 else None
    u = user(message.from_user.id)
    text = (
        f"Привет, {message.from_user.first_name or 'друг'}! 👋\n\n"
        "Я помогаю самозанятым и фрилансерам:\n"
        "🧮 считаю налог НПД (4% или 6%)\n"
        "📄 готовлю текст чека одной строкой\n"
        "📊 показываю статус и остаток бесплатных чеков\n\n"
        f"Бесплатных чеков доступно: {checks_left(u)}\n\n"
        "Напишите сумму — посчитаю налог. Например: 50000"
    )
    if payload and payload.startswith("ref_"):
        ref_id = payload[4:]
        if ref_id != str(message.from_user.id):
            u["ref"] = ref_id
            inviter = DATA.get(ref_id)
            if inviter is not None:
                add_sub_days(inviter, REF_SUB_DAYS)
                add_sub_days(u, REF_SUB_DAYS)
                dump(DATA)
                text += (
                    f"\n\n🎉 Вы пришли по приглашению — обоим активирована подписка на {REF_SUB_DAYS} дней!\n"
                    f"Ваша подписка активна до {u['sub_until'][:10]}."
                )
                try:
                    await bot.send_message(
                        int(ref_id),
                        f"🎁 Ваш друг запустил бота! Обоим активирована подписка на {REF_SUB_DAYS} дней "
                        f"(ваша — до {inviter['sub_until'][:10]})."
                    )
                except Exception:
                    pass
    await message.answer(text, reply_markup=start_kb)


@dp.callback_query(F.data.in_(["type_физ", "type_юр"]))
async def type_callback(query: CallbackQuery):
    u = user(query.from_user.id)
    u["type"] = query.data.split("_")[1]
    dump(DATA)
    rate = "4%" if u["type"] == "физ" else "6%"
    await query.message.edit_reply_markup(reply_markup=None)
    await query.answer(f"Готово! Ставка {rate}.")
    await query.message.answer(
        f"Готово! Ваши доходы теперь от {'физлиц' if u['type'] == 'физ' else 'юрлиц'}, ставка {rate}.",
        reply_markup=start_kb,
    )


@dp.message(Command("help"))
async def help_cmd(message: Message):
    await message.answer(
        "Что я умею:\n\n"
        "• Напишите сумму (например 50000) — рассчитаю налог НПД\n"
        "• «🔄 Выбрать тип» или /type — кнопки выбора: физ 4% / юр 6%\n"
        "• /check Название 3000 — подготовлю текст чека\n"
        "• /status — сколько чеков осталось и подписка\n"
        "• /subscribe — подключить подписку за звёзды\n"
        "• /ref — пригласить друга: месяц подписки обоим"
    )


@dp.message(Command("type"))
async def type_cmd(message: Message):
    await message.answer("Выберите тип налогообложения:", reply_markup=type_kb)


@dp.message(F.text == "🔄 Выбрать тип")
async def select_type(message: Message):
    await message.answer("Выберите тип налогообложения:", reply_markup=type_kb)


@dp.message(Command("status"))
async def status_cmd(message: Message):
    u = user(message.from_user.id)
    if u["type"] == "физ":
        type_text = "физлицо (4%)"
    elif u["type"] == "юр":
        type_text = "юрлицо (6%)"
    else:
        type_text = "не выбран — нажмите «🔄 Выбрать тип» или /type"
    sub_text = "активна до " + u["sub_until"][:10] if sub_active(u) else "не активна"
    hist = "\n".join("• " + h for h in u.get("history", [])[-3:]) or "• пока пусто"
    await message.answer(
        f"📊 Ваш статус:\n\n"
        f"Тип: {type_text}\n"
        f"Бесплатных чеков осталось: {checks_left(u)}\n"
        f"Подписка: {sub_text}\n\n"
        f"Последние расчёты:\n{hist}"
    )


@dp.message(Command("ref"))
async def ref_cmd(message: Message):
    me = await bot.get_me()
    await message.answer(
        f"🎁 Приглашайте друзей — по вашей ссылке оба получат бесплатную подписку на {REF_SUB_DAYS} дней!\n\n"
        f"Ваша ссылка:\nt.me/{me.username}?start=ref_{message.from_user.id}"
    )


@dp.message(Command("subscribe"))
async def subscribe_cmd(message: Message):
    u = user(message.from_user.id)
    if sub_active(u):
        await message.answer(f"⭐ Подписка активна до {u['sub_until'][:10]}. Лимитов на чеки нет.")
        return
    await message.answer(
        f"⭐ Подписка на 30 дней — {SUB_PRICE_STARS} звёзд:\n\n"
        "• безлимитные чеки\n"
        "• напоминания об уплате до 28-го числа\n\n"
        f"Оплатить: /pay"
    )


@dp.message(Command("pay"))
async def pay_cmd(message: Message):
    await bot.send_invoice(
        message.chat.id,
        title="Подписка на 30 дней",
        description="Безлимитные чеки и напоминания",
        payload="sub30",
        currency="XTR",
        prices=[LabeledPrice(label="Подписка", amount=SUB_PRICE_STARS)],
    )


@dp.pre_checkout_query()
async def pre_checkout(query: PreCheckoutQuery):
    await query.answer(ok=True)


@dp.message(F.successful_payment)
async def paid(message: Message):
    u = user(message.from_user.id)
    add_sub_days(u, SUB_DAYS)
    dump(DATA)
    await message.answer(f"✅ Оплата прошла! Подписка активна до {u['sub_until'][:10]}. Спасибо!")


def calc_nalog(amount, utype):
    rate = 6 if utype == "юр" else 4
    tax = amount * rate / 100
    return rate, tax, amount - tax


@dp.message(Command("nalog"))
async def nalog_cmd(message: Message):
    u = user(message.from_user.id)
    if u["type"] is None:
        await message.answer("Сначала выберите тип:", reply_markup=type_kb)
        return
    await message.answer("Напишите сумму дохода числом, например: 50000")


@dp.message(Command("check"))
async def check_cmd(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer("Формат: /check Название 3000\nНапример: /check Консультация 3000")
        return
    name, amount_s = parts[1], parts[2].replace(",", ".").replace(" ", "")
    try:
        amount = float(amount_s)
    except ValueError:
        await message.answer("Сумма должна быть числом: /check Консультация 3000")
        return
    u = user(message.from_user.id)
    if checks_left(u) <= 0:
        await message.answer("Бесплатные чеки закончились 🙁 /subscribe — подписка за звёзды или /ref — пригласить друга и получить месяц подписки обоим.")
        return
    utype = u["type"] or "физ"
    rate, tax, net = calc_nalog(amount, utype)
    u["checks_used"] = u.get("checks_used", 0) + 1
    u["history"].append(f"Чек «{name}» — {amount:g} ₽ (налог {tax:g} ₽)")
    dump(DATA)
    await message.answer(
        f"📄 Текст чека:\n\n"
        f"Услуга: {name}\n"
        f"Сумма: {amount:g} ₽\n"
        f"Налог НПД ({rate}%): {tax:g} ₽\n"
        f"На руки: {net:g} ₽\n\n"
        f"Осталось бесплатных чеков: {checks_left(u)}"
    )


@dp.message(F.text)
async def text_handler(message: Message):
    u = user(message.from_user.id)
    if message.text == "🧮 Рассчитать налог":
        if u["type"] is None:
            await message.answer("Сначала выберите тип:", reply_markup=type_kb)
            return
        await message.answer("Напишите сумму дохода числом, например: 50000")
        return
    if message.text == "📄 Подготовить чек":
        await message.answer("Формат: /check Название 3000\nНапример: /check Консультация 3000")
        return
    if message.text == "⭐ Подписка":
        await subscribe_cmd(message)
        return
    if message.text == "📊 Мой статус":
        await status_cmd(message)
        return
    if message.text == "🎁 Пригласить друга":
        await ref_cmd(message)
        return
    s = message.text.replace(",", ".").replace(" ", "").replace("₽", "")
    try:
        amount = float(s)
    except ValueError:
        await message.answer("Не понял 🙂 Напишите сумму числом (например 50000) или /help")
        return
    if u["type"] is None:
        await message.answer("Сначала выберите тип:", reply_markup=type_kb)
        return
    rate, tax, net = calc_nalog(amount, u["type"])
    u["history"].append(f"Расчёт {amount:g} ₽ (налог {tax:g} ₽)")
    dump(DATA)
    await message.answer(
        f"🧮 Расчёт налога НПД:\n\n"
        f"Доход: {amount:g} ₽\n"
        f"Ставка: {rate}%\n"
        f"Налог: {tax:g} ₽\n"
        f"На руки: {net:g} ₽"
    )


# ---------- напоминания ----------

async def reminder_loop():
    while True:
        try:
            now = datetime.now()
            if now.day in REMINDER_DAYS and now.hour == REMINDER_HOUR:
                today = now.strftime("%Y-%m-%d")
                for uid, u in list(DATA.items()):
                    if sub_active(u) and not u.get("sent_reminders", {}).get(today):
                        try:
                            await bot.send_message(
                                int(uid),
                                "🔔 Напоминание: уплатите налог НПД за месяц до 28-го числа!\n\n"
                                "Сумму налога за каждый доход можно посмотреть в /status — раздел «Последние расчёты»."
                            )
                            u.setdefault("sent_reminders", {})[today] = True
                            dump(DATA)
                        except Exception:
                            pass
        except Exception:
            pass
        await asyncio.sleep(1800)


async def main():
    await bot(SetMyCommands(commands=commands))
    print("Бот запущен. Для остановки нажмите Ctrl+C")
    asyncio.create_task(reminder_loop())
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
