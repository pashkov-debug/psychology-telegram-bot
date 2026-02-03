import os
import re
from datetime import datetime, timezone
from html import escape as html_escape

from aiogram import Router, F
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, CallbackQuery, ReplyKeyboardRemove

from bot.content import SITE, WELCOME_TEXT, DISCLAIMER, PRIVACY_TEXT, HELP_TEXT, SEARCH_INFO_TEXT
from bot.keyboards import main_menu, link_button, back_to_menu, phone_request_kb, cancel_kb, confirm_kb
from bot.states import BookingStates
from bot.runtime import get_crossref, get_literature
from bot.db import add_history, get_history_rows, clear_history, set_history_enabled, is_history_enabled

router = Router()

PHONE_RE = re.compile(r"^\+?[0-9][0-9\s\-\(\)]{7,20}$")

from datetime import datetime, timezone

def _to_utc_dt(v):
    if v is None:
        return None

    if isinstance(v, datetime):
        dt = v
    elif isinstance(v, (int, float)):
        dt = datetime.fromtimestamp(v, tz=timezone.utc)
    elif isinstance(v, str):
        s = v.strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(s)
        except ValueError:
            # fallback под частые форматы SQLite
            for fmt in ("%Y-%m-%d %H:%M:%S%z", "%Y-%m-%d %H:%M:%S"):
                try:
                    dt = datetime.strptime(s, fmt)
                    break
                except ValueError:
                    dt = None
            if dt is None:
                return None
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def normalize_phone(raw: str) -> str:
    return re.sub(r"\s+", " ", raw).strip()


def admin_chat_id() -> int | None:
    v = os.getenv("ADMIN_CHAT_ID", "").strip()
    if not v:
        return None
    try:
        return int(v)
    except ValueError:
        return None


def _arg(text: str | None) -> str:
    if not text:
        return ""
    parts = text.strip().split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _truncate(s: str, n: int = 240) -> str:
    s = (s or "").strip()
    return (s[: n - 1] + "…") if len(s) > n else s


async def _send_history(target: Message, tg_user_id: int) -> None:
    rows = get_history_rows(tg_user_id=tg_user_id, limit=10)
    enabled = is_history_enabled(tg_user_id=tg_user_id)

    if not enabled:
        await target.answer("🕘 История отключена. Включить: /history_on")
        return

    if not rows:
        await target.answer("🕘 История пуста. Попробуйте: /find <запрос>")
        return

    lines = ["🕘 <b>Последние запросы</b>"]
    for i, r in enumerate(rows, 1):
        dt = _to_utc_dt(r.get("created_at"))
        ts = dt.strftime("%Y-%m-%d %H:%M UTC") if dt else "—"
        cmd = html_escape(r["command"] or "")
        q = html_escape(_truncate(r["query"] or "", 120))
        title = html_escape(_truncate(r["result_title"] or "", 160))
        url = r["result_url"] or ""
        if url:
            lines.append(f"{i}) <b>{cmd}</b> — {q}\n   {ts}\n   {title}\n   {html_escape(url)}")
        else:
            lines.append(f"{i}) <b>{cmd}</b> — {q}\n   {ts}\n   {title}")

    await target.answer("\n\n".join(lines))


# --- Команды ---

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


@router.message(Command("help"))
async def cmd_help(message: Message):
    await message.answer(HELP_TEXT)


@router.message(Command("history"))
async def cmd_history(message: Message):
    await _send_history(target=message, tg_user_id=message.from_user.id)


@router.message(Command("clear_history"))
async def cmd_clear_history(message: Message):
    n = clear_history(tg_user_id=message.from_user.id)
    await message.answer(f"🧹 Удалено записей: <b>{n}</b>.")


@router.message(Command("history_off"))
async def cmd_history_off(message: Message):
    clear_history(tg_user_id=message.from_user.id)
    set_history_enabled(tg_user_id=message.from_user.id, enabled=False)
    await message.answer("🔒 Ок. История отключена и очищена. Включить: /history_on")


@router.message(Command("history_on"))
async def cmd_history_on(message: Message):
    set_history_enabled(tg_user_id=message.from_user.id, enabled=True)
    await message.answer("✅ История включена.")


@router.message(Command("whoami"))
async def cmd_whoami(message: Message):
    await message.answer(
        f"Ваш chat_id: <code>{message.chat.id}</code>\n"
        f"Ваш user_id: <code>{message.from_user.id}</code>"
    )


# --- Поиск (Crossref API) ---

@router.message(Command("find"))
async def cmd_find(message: Message):
    query = _arg(message.text)
    if not query:
        await message.answer("Формат: <code>/find название статьи</code> или <code>/find 10.xxxx/xxxxx</code>")
        return

    lit = get_literature()
    try:
        items = await lit.search(query=query, rows=5)
    except Exception as e:
        await message.answer(f"⚠️ Ошибка поиска: {html_escape(str(e))}")
        return

    if not items:
        await message.answer("Ничего не найдено. Попробуйте переформулировать запрос.")
        return

    lines = [f"🔎 <b>Результаты:</b> {html_escape(_truncate(query, 120))}"]
    for i, it in enumerate(items, 1):
        title = html_escape(_truncate(it.title, 220))
        authors = html_escape(_truncate(it.authors, 160))
        year = str(it.year) if it.year else "—"
        doi = html_escape(it.doi or "")
        url = it.url or (f"https://doi.org/{it.doi}" if it.doi else "")
        cited = f" • cited-by: {it.cited_by}" if it.cited_by is not None else ""
        src = html_escape(it.source or "source")
        doi_line = f"   DOI: <code>{doi}</code>\n" if it.doi else ""
        lines.append(
            f"{i}) <b>{title}</b> <i>[{src}]</i>\n"
            f"   {year}{cited}\n"
            f"   {authors}\n"
            f"{doi_line}"
            f"   {html_escape(url)}"
        )

    top = items[0]
    add_history(
        tg_user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        command="/find",
        query=query,
        result_title=top.title,
        result_url=top.url or (f"https://doi.org/{top.doi}" if top.doi else None),
    )

    await message.answer("\n\n".join(lines))


@router.message(Command("author"))
async def cmd_author(message: Message):
    author = _arg(message.text)
    if not author:
        await message.answer("Формат: <code>/author Имя Фамилия</code>")
        return

    client = get_crossref()
    try:
        items = await client.search_by_author(author=author, rows=5)
    except Exception as e:
        await message.answer(f"⚠️ Ошибка поиска: {html_escape(str(e))}")
        return

    if not items:
        await message.answer("Ничего не найдено по автору. Попробуйте другое написание.")
        return

    lines = [f"🔎 <b>Публикации автора:</b> {html_escape(_truncate(author, 120))}"]
    for i, it in enumerate(items, 1):
        title = html_escape(_truncate(it.title, 220))
        authors = html_escape(_truncate(it.authors, 160))
        year = str(it.year) if it.year else "—"
        url = it.url or ""
        cited = f" • cited-by: {it.cited_by}" if it.cited_by is not None else ""
        lines.append(
            f"{i}) <b>{title}</b>\n"
            f"   {year}{cited}\n"
            f"   {authors}\n"
            f"   {html_escape(url)}"
        )

    top = items[0]
    add_history(
        tg_user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        command="/author",
        query=author,
        result_title=top.title,
        result_url=top.url,
    )

    await message.answer("\n\n".join(lines))


@router.message(Command("doi"))
async def cmd_doi(message: Message):
    doi = _arg(message.text)
    if not doi:
        await message.answer("Формат: <code>/doi 10.xxxx/xxxxx</code>")
        return

    lit = get_literature()
    try:
        it = await lit.lookup_doi(doi=doi)
    except Exception as e:
        await message.answer(f"⚠️ Ошибка: {html_escape(str(e))}")
        return

    if not it:
        await message.answer("Ничего не найдено по этому DOI.")
        return

    title = html_escape(_truncate(it.title, 260))
    authors = html_escape(_truncate(it.authors, 220))
    year = str(it.year) if it.year else "—"
    url = it.url or (f"https://doi.org/{it.doi}" if it.doi else "")
    cited = f" • cited-by: {it.cited_by}" if it.cited_by is not None else ""
    src = html_escape(it.source or "source")
    doi_norm = html_escape(it.doi or "")

    add_history(
        tg_user_id=message.from_user.id,
        username=message.from_user.username,
        full_name=message.from_user.full_name,
        command="/doi",
        query=doi,
        result_title=it.title,
        result_url=it.url or (f"https://doi.org/{it.doi}" if it.doi else None),
    )

    await message.answer(
        "🔎 <b>Метаданные по DOI</b>\n"
        f"<b>{title}</b> <i>[{src}]</i>\n"
        f"DOI: <code>{doi_norm}</code>\n"
        f"{year}{cited}\n"
        f"{authors}\n"
        f"{html_escape(url)}"
    )


# --- Inline меню ---

@router.callback_query(F.data == "menu:back")
async def cb_back(call: CallbackQuery, state: FSMContext):
    await state.clear()
    await call.message.edit_text("Меню:", reply_markup=main_menu())
    await call.answer()


@router.callback_query(F.data == "menu:privacy")
async def cb_privacy(call: CallbackQuery):
    await call.message.edit_text(PRIVACY_TEXT, reply_markup=back_to_menu())
    await call.answer()


@router.callback_query(F.data == "menu:search")
async def cb_search(call: CallbackQuery):
    await call.message.edit_text(SEARCH_INFO_TEXT, reply_markup=back_to_menu())
    await call.answer()


@router.callback_query(F.data == "menu:history")
async def cb_history(call: CallbackQuery):
    await call.answer()
    await _send_history(target=call.message, tg_user_id=call.from_user.id)


@router.callback_query(F.data == "menu:free")
async def cb_free(call: CallbackQuery):
    url = SITE.get("free") or SITE.get("home") or ""
    if not url:
        await call.message.edit_text("Ссылка не настроена (SITE_FREE_URL).", reply_markup=back_to_menu())
    else:
        await call.message.edit_text("Бесплатные материалы (онлайн тесты, книги) — по ссылке:", reply_markup=link_button("Открыть", url))
    await call.answer()


@router.callback_query(F.data == "menu:about")
async def cb_about(call: CallbackQuery):
    url = SITE.get("about") or ""
    if not url:
        await call.message.edit_text("Ссылка не настроена (SITE_ABOUT_URL).", reply_markup=back_to_menu())
    else:
        await call.message.edit_text("Обо мне:\nМедицинский психолог\nСистемный семейный терапевт\nОкончил РНИМУ (2й медицинский) в 2015г\nБолее 10 доп образований\nОзнакомится с документами можно по ссылке по ссылке:", reply_markup=link_button("Открыть", url))
    await call.answer()


@router.callback_query(F.data == "menu:contact")
async def cb_contact(call: CallbackQuery):
    url = SITE.get("contact") or ""
    if not url:
        await call.message.edit_text("Ссылка не настроена (SITE_CONTACT_URL).", reply_markup=back_to_menu())
    else:
        await call.message.edit_text("Контакты:\n+79251421401\npashkovnpc@gmail.com\n Или по ссылке:", reply_markup=link_button("Открыть", url))
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

    # ВАЖНО: этот текст не сохраняется в БД (приватность)
    await state.update_data(request_text=text)
    data = await state.get_data()

    preview = (
        "✅ <b>Проверьте заявку</b>\n\n"
        f"<b>Телефон:</b> <code>{html_escape(data['phone'])}</code>\n"
        f"<b>Запрос:</b> {html_escape(data['request_text'])}\n\n"
        "Отправить заявку?"
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
        f"<b>Имя:</b> {html_escape(u.full_name)}\n"
        f"<b>Username:</b> {html_escape(username)}\n"
        f"<b>User ID:</b> <code>{u.id}</code>\n"
        f"<b>Телефон:</b> <code>{html_escape(data.get('phone',''))}</code>\n\n"
        f"<b>Запрос:</b>\n{html_escape(data.get('request_text',''))}"
    )

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
        "✅ Заявка отправлена. Специалист свяжется с вами по указанному номеру.",
        reply_markup=back_to_menu()
    )
    await state.clear()
