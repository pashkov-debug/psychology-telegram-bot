from aiogram.fsm.state import State, StatesGroup

class BookingStates(StatesGroup):
    phone = State()
    request_text = State()
    confirm = State()
