from aiogram.fsm.state import State, StatesGroup


class SearchStates(StatesGroup):
    district = State()
    budget = State()
    rooms = State()
    term = State()


class BookingStates(StatesGroup):
    waiting_contact = State()


class SupportStates(StatesGroup):
    waiting_message = State()


class StaffStates(StatesGroup):
    ticket_reply = State()
    excel_upload = State()
    property_photo = State()
