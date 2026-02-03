from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder
from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton

from bot.content import SITE


def main_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔎 Поиск статей", callback_data="menu:search")
    kb.button(text="🕘 История", callback_data="menu:history")

    if SITE.get("free"):
        kb.button(text="📚 Бесплатное", callback_data="menu:free")
    if SITE.get("about"):
        kb.button(text="👤 Обо мне", callback_data="menu:about")

    kb.button(text="🗓 Записаться", callback_data="menu:book")

    if SITE.get("contact"):
        kb.button(text="☎️ Контакты", callback_data="menu:contact")

    kb.button(text="🔒 Приватность", callback_data="menu:privacy")
    kb.adjust(2, 2, 2, 1)
    return kb.as_markup()


def link_button(text: str, url: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=text, url=url)
    kb.button(text="⬅️ Меню", callback_data="menu:back")
    kb.adjust(1)
    return kb.as_markup()


def back_to_menu() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="⬅️ Меню", callback_data="menu:back")
    return kb.as_markup()


def phone_request_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="📱 Поделиться контактом", request_contact=True))
    kb.add(KeyboardButton(text="⛔️ Отмена"))
    kb.adjust(1)
    return kb.as_markup(
        resize_keyboard=True,
        one_time_keyboard=True,
        input_field_placeholder="Телефон или контакт",
    )


def cancel_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.add(KeyboardButton(text="⛔️ Отмена"))
    return kb.as_markup(resize_keyboard=True, one_time_keyboard=True)


def confirm_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ Отправить", callback_data="book:send")
    kb.button(text="✏️ Изменить текст", callback_data="book:edit")
    kb.button(text="⛔️ Отмена", callback_data="book:cancel")
    kb.adjust(1)
    return kb.as_markup()
