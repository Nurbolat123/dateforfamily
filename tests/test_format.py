from datetime import date

from core.format import calculate_age, format_age_ru


def test_calculate_age_before_birthday_this_year():
    assert calculate_age(date(2000, 12, 31), today=date(2025, 6, 1)) == 24


def test_calculate_age_after_birthday_this_year():
    assert calculate_age(date(2000, 1, 1), today=date(2025, 6, 1)) == 25


def test_calculate_age_on_birthday():
    assert calculate_age(date(2000, 6, 1), today=date(2025, 6, 1)) == 25


def test_format_age_ru_one():
    assert format_age_ru(21) == "21 год"
    assert format_age_ru(31) == "31 год"


def test_format_age_ru_few():
    assert format_age_ru(22) == "22 года"
    assert format_age_ru(23) == "23 года"
    assert format_age_ru(24) == "24 года"


def test_format_age_ru_many():
    assert format_age_ru(25) == "25 лет"
    assert format_age_ru(18) == "18 лет"


def test_format_age_ru_teens_exception():
    # 11-14 - всегда "лет", даже 11 ("одиннадцать") не "одиннадцать один"
    assert format_age_ru(11) == "11 лет"
    assert format_age_ru(12) == "12 лет"
    assert format_age_ru(111) == "111 лет"
