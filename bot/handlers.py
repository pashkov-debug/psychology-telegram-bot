import os
import re
from datetime import datetime, timezone

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove

from bot.content import SITE, WELCOME_TEXT, DISCLAIMER, PRIVACY_TEXT
from bot.keyboards import main_menu, link_button, back_to_menu, phone_request_kb, cancel_kb, confirm_kb
from bot.states import BookingStates

router = Router()

PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-\(\)]{7,20}$")

def normalize_phone(raw: str) -> str:
    # минимальная нормализация: убрать лишние пробелы
    return re.sub(r"\s+", " ", raw).strip()

def admin_chat_id() -> int | None:
    v = os.getenv("ADMIN_CHAT_ID", "").strip()
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


@router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(WELCOME_TEXT)
    await message.answer(DISCLAIMER)
    await message.answer("Выберите раздел:", reply_markup=main_menu())


@router.message(Command("menu"))
async def cmd_menu(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Меню:", reply_markup=main_menu())


@router.message(Command("whoami"))
async def cmd_whoami(message: Message):
    await message.answer(
        f"Ваш chat_id: <code>{message.chat.id}</code>\n"
        f"Ваш user_id: <code>{message.from_user.id}</code>"
    )


@router.callback_query(F.data == "menu:back")
async def cb_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Меню:", reply_markup=main_menu())
    await call.answer()


@router.callback_query(F.data == "menu:privacy")
async def cb_privacy(call: CallbackQuery):
    await call.message.edit_text(PRIVACY_TEXT, reply_markup=back_to_menu())
    await call.answer()


@router.callback_query(F.data == "menu:free")
async def cb_free(call: CallbackQuery):
    url = SITE.get("free") or SITE.get("home") or ""
    if not url:
        await call.message.edit_text("Ссылка не настроена (SITE_FREE_URL).", reply_markup=back_to_menu())
    else:
        await call.message.edit_text("Бесплатные материалы — по ссылке:", reply_markup=link_button("Открыть", url))
    await call.answer()


@router.callback_query(F.data == "menu:about")
async def cb_about(call: CallbackQuery):
    url = SITE.get("about") or ""
    if not url:
        await call.message.edit_text("Ссылка не настроена (SITE_ABOUT_URL).", reply_markup=back_to_menu())
    else:
        await call.message.edit_text("Обо мне — по ссылке:", reply_markup=link_button("Открыть", url))
    await call.answer()


@router.callback_query(F.data == "menu:contact")
async def cb_contact(call: CallbackQuery):
    url = SITE.get("contact") or ""
    if not url:
        await call.message.edit_text("Ссылка не настроена (SITE_CONTACT_URL).", reply_markup=back_to_menu())
    else:
        await call.message.edit_text("Контакты — по ссылке:", reply_markup=link_button("Открыть", url))
    await call.answer()


# ---- Сценарий записи ----

@router.callback_query(F.data == "menu:book")
async def cb_book(call: CallbackQuery, state: FSMContext):
    await state.set_state(BookingStates.phone)
    await call.answer()
    await call.message.answer(
        "📩 <b>Запрос на консультацию</b>\n"
        "Отправьте номер телефона для обратной связи.\n"
        "Можно нажать кнопку «Поделиться контактом» или написать номер вручную.\n\n"
        "Чтобы отменить — нажмите «Отмена».",
        reply_markup=phone_request_kb()
    )

@router.message(BookingStates.phone)
async def booking_phone(message: Message, state: FSMContext):
    if message.text and message.text.strip() == "⛔️ Отмена":
        await state.clear()
        await message.answer("Ок, отменено.", reply_markup=ReplyKeyboardRemove())
        await message.answer("Меню:", reply_markup=main_menu())
        return

    phone = None
    if message.contact and message.contact.phone_number:
        phone = normalize_phone(message.contact.phone_number)
    elif message.text:
        raw = message.text.strip()
        if PHONE_RE.match(raw):
            phone = normalize_phone(raw)

    if not phone:
        await message.answer(
            "Не похоже на номер телефона.\n"
            "Пример: +7 999 123-45-67\n"
            "Или нажмите «Поделиться контактом».",
            reply_markup=phone_request_kb()
        )
        return

    await state.update_data(phone=phone)
    await state.set_state(BookingStates.request_text)
    await message.answer("Спасибо! Теперь кратко опишите запрос (1–3 предложения).", reply_markup=cancel_kb())

@router.message(BookingStates.request_text)
async def booking_request_text(message: Message, state: FSMContext):
    if message.text and message.text.strip() == "⛔️ Отмена":
        await state.clear()
        await message.answer("Ок, отменено.", reply_markup=ReplyKeyboardRemove())
        await message.answer("Меню:", reply_markup=main_menu())
        return

    text = (message.text or "").strip()
    if len(text) < 5:
        await message.answer("Слишком коротко. Напишите пару слов о запросе (минимум 5 символов).", reply_markup=cancel_kb())
        return
    if len(text) > 1500:
        await message.answer("Слишком длинно. Сократите, пожалуйста, до ~1500 символов.", reply_markup=cancel_kb())
        return

    await state.update_data(request_text=text)
    data = await state.get_data()

    preview = (
        "✅ <b>Проверьте заявку</b>\n\n"
        f"<b>Телефон:</b> <code>{data['phone']}</code>\n"
        f"<b>Запрос:</b> {data['request_text']}\n\n"
        "Отправить вам заявку?"
    )
    await state.set_state(BookingStates.confirm)
    await message.answer(preview, reply_markup=ReplyKeyboardRemove())
    await message.answer("Выберите действие:", reply_markup=confirm_kb())

@router.callback_query(BookingStates.confirm, F.data == "book:edit")
async def booking_edit(call: CallbackQuery, state: FSMContext):
    await state.set_state(BookingStates.request_text)
    await call.answer()
    await call.message.answer("Ок, напишите текст запроса заново:", reply_markup=cancel_kb())

@router.callback_query(BookingStates.confirm, F.data == "book:cancel")
async def booking_cancel(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.answer()
    await call.message.edit_text("Ок, отменено.", reply_markup=back_to_menu())

@router.callback_query(BookingStates.confirm, F.data == "book:send")
async def booking_send(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    chat_id = admin_chat_id()
    await call.answer()

    if not chat_id:
        await call.message.edit_text(
            "⚠️ Не настроен ADMIN_CHAT_ID.\n"
            "Сделайте /whoami у себя и вставьте chat_id в переменные окружения.",
            reply_markup=back_to_menu()
        )
        await state.clear()
        return

    u = call.from_user
    username = f"@{u.username}" if u.username else "(нет username)"
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    admin_text = (
        "📥 <b>Запрос на консультацию</b>\n"
        f"<b>Время:</b> {now}\n"
        f"<b>Имя:</b> {u.full_name}\n"
        f"<b>Username:</b> {username}\n"
        f"<b>User ID:</b> <code>{u.id}</code>\n"
        f"<b>Телефон:</b> <code>{data.get('phone','')}</code>\n\n"
        f"<b>Запрос:</b>\n{data.get('request_text','')}"
    )

    # Важно: бот может написать админу только если админ уже нажал /start у бота
    try:
        await call.bot.send_message(chat_id=chat_id, text=admin_text)
    except Exception:
        await call.message.edit_text(
            "⚠️ Не удалось отправить админу сообщение.\n"
            "Проверьте, что вы (админ) нажали /start у бота и ADMIN_CHAT_ID верный.",
            reply_markup=back_to_menu()
        )
        await state.clear()
        return

    await call.message.edit_text(
        "✅ Заявка отправлена. Я свяжусь с вами по указанному номеру.",
        reply_markup=back_to_menu()
    )
    await state.clear()
