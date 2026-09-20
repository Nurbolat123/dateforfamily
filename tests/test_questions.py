import pytest

from core.locales import option_text, question_text
from core.models import QuestionLayer
from core.questions import QUESTIONS, by_key, by_layer, first_unanswered_index


def test_total_number_of_questions_is_fifteen():
    assert len(QUESTIONS) == 15


@pytest.mark.parametrize("layer", [QuestionLayer.FILTER, QuestionLayer.VALUES, QuestionLayer.LIFESTYLE])
def test_each_layer_has_exactly_five_questions(layer):
    assert len(by_layer(layer)) == 5


def test_question_keys_are_unique():
    keys = [q.key for q in QUESTIONS]
    assert len(keys) == len(set(keys))


def test_each_question_has_at_least_two_options():
    for question in QUESTIONS:
        assert len(question.options) >= 2


def test_by_key_returns_matching_question():
    question = by_key("smoking")
    assert question.layer == QuestionLayer.FILTER


def test_by_key_raises_for_unknown_key():
    with pytest.raises(KeyError):
        by_key("does_not_exist")


def test_every_question_has_russian_text():
    for question in QUESTIONS:
        text = question_text(question.key, "ru")
        assert isinstance(text, str) and text.strip() != ""


def test_every_option_has_russian_text():
    for question in QUESTIONS:
        for option in question.options:
            text = option_text(question.key, option, "ru")
            assert isinstance(text, str) and text.strip() != ""


def test_first_unanswered_index_with_no_answers():
    assert first_unanswered_index(set()) == 0


def test_first_unanswered_index_skips_answered():
    answered = {QUESTIONS[0].key, QUESTIONS[1].key}
    assert first_unanswered_index(answered) == 2


def test_first_unanswered_index_none_when_all_answered():
    answered = {q.key for q in QUESTIONS}
    assert first_unanswered_index(answered) is None
