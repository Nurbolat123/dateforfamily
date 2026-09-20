from aiogram.fsm.state import State, StatesGroup


class Registration(StatesGroup):
    waiting_consent = State()
    waiting_name = State()
    waiting_gender = State()
    waiting_birth_date = State()
    waiting_city = State()
    waiting_relocate = State()


class ConsentRenewal(StatesGroup):
    waiting_consent = State()


class Survey(StatesGroup):
    waiting_own_answer = State()
    waiting_acceptable_answers = State()
    waiting_importance = State()
