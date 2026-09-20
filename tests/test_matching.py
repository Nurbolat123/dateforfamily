from core.matching import (
    Candidate,
    QuestionAnswer,
    build_explanation,
    calculate_match,
    directional_score,
    find_matches,
    is_same_clan,
    passes_hard_filters,
)


def make_candidate(
    user_id: int,
    answers: list[QuestionAnswer],
    is_blocked: bool = False,
    clan_ru: str | None = None,
) -> Candidate:
    return Candidate(
        user_id=user_id,
        is_blocked=is_blocked,
        clan_ru=clan_ru,
        answers=tuple(answers),
    )


def filter_answer(question_id: int, own: str, acceptable: tuple[str, ...], importance: int = 2) -> QuestionAnswer:
    return QuestionAnswer(
        question_id=question_id,
        layer="filter",
        own_option=own,
        acceptable_options=acceptable,
        importance=importance,
    )


def values_answer(question_id: int, own: str, acceptable: tuple[str, ...], importance: int) -> QuestionAnswer:
    return QuestionAnswer(
        question_id=question_id,
        layer="values",
        own_option=own,
        acceptable_options=acceptable,
        importance=importance,
    )


# --- Жёсткие фильтры ---

def test_hard_filter_blocks_when_a_does_not_accept_b():
    a = make_candidate(1, [filter_answer(1, "не курит", ("не курит",))])
    b = make_candidate(2, [filter_answer(1, "курит", ("курит", "не курит"))])

    assert passes_hard_filters(a, b) is False


def test_hard_filter_blocks_when_b_does_not_accept_a():
    a = make_candidate(1, [filter_answer(1, "курит", ("курит", "не курит"))])
    b = make_candidate(2, [filter_answer(1, "не курит", ("не курит",))])

    assert passes_hard_filters(a, b) is False


def test_hard_filter_passes_when_mutually_acceptable():
    a = make_candidate(1, [filter_answer(1, "не курит", ("не курит",))])
    b = make_candidate(2, [filter_answer(1, "не курит", ("курит", "не курит"))])

    assert passes_hard_filters(a, b) is True


def test_blocked_user_never_passes_filters():
    a = make_candidate(1, [], is_blocked=True)
    b = make_candidate(2, [])

    assert passes_hard_filters(a, b) is False


def test_missing_answer_does_not_block():
    a = make_candidate(1, [filter_answer(1, "не курит", ("не курит",))])
    b = make_candidate(2, [])  # b не отвечал на этот вопрос

    assert passes_hard_filters(a, b) is True


# --- Веса и направленный балл ---

def test_directional_score_full_match_is_one():
    a = make_candidate(1, [values_answer(10, "часто", ("часто",), importance=2)])
    b = make_candidate(2, [values_answer(10, "часто", ("часто", "редко"), importance=2)])

    assert directional_score(a, b) == 1.0


def test_directional_score_zero_when_no_match():
    a = make_candidate(1, [values_answer(10, "часто", ("часто",), importance=2)])
    b = make_candidate(2, [values_answer(10, "редко", ("редко",), importance=2)])

    assert directional_score(a, b) == 0.0


def test_directional_score_weights_important_more_than_less_important():
    # Один очень важный вопрос совпал, один важный — нет.
    a = make_candidate(
        1,
        [
            values_answer(1, "да", ("да",), importance=2),  # вес 50, совпадёт
            values_answer(2, "да", ("да",), importance=1),  # вес 10, не совпадёт
        ],
    )
    b = make_candidate(
        2,
        [
            values_answer(1, "да", ("да",), importance=2),
            values_answer(2, "нет", ("нет",), importance=2),
        ],
    )

    # 50 / (50 + 10) = 0.8333...
    assert round(directional_score(a, b), 4) == round(50 / 60, 4)


def test_directional_score_all_unimportant_is_zero_not_error():
    a = make_candidate(1, [values_answer(1, "да", ("да",), importance=0)])
    b = make_candidate(2, [values_answer(1, "нет", ("нет",), importance=0)])

    assert directional_score(a, b) == 0.0


def test_directional_score_no_answers_is_zero():
    a = make_candidate(1, [])
    b = make_candidate(2, [values_answer(1, "да", ("да",), importance=2)])

    assert directional_score(a, b) == 0.0


# --- Взаимность итогового балла ---

def test_match_score_is_symmetric():
    a = make_candidate(
        1,
        [
            filter_answer(1, "не курит", ("не курит",)),
            values_answer(10, "часто", ("часто", "иногда"), importance=2),
        ],
    )
    b = make_candidate(
        2,
        [
            filter_answer(1, "не курит", ("не курит",)),
            values_answer(10, "иногда", ("часто", "иногда"), importance=1),
        ],
    )

    match_ab = calculate_match(a, b)
    match_ba = calculate_match(b, a)

    assert match_ab is not None
    assert match_ba is not None
    assert round(match_ab.score, 9) == round(match_ba.score, 9)


def test_match_below_threshold_returns_none():
    a = make_candidate(1, [values_answer(1, "да", ("да",), importance=2)])
    b = make_candidate(2, [values_answer(1, "нет", ("нет",), importance=2)])

    assert calculate_match(a, b) is None


def test_match_failing_filters_returns_none_even_with_good_values():
    a = make_candidate(
        1,
        [
            filter_answer(1, "не курит", ("не курит",)),
            values_answer(10, "часто", ("часто",), importance=2),
        ],
    )
    b = make_candidate(
        2,
        [
            filter_answer(1, "курит", ("курит",)),
            values_answer(10, "часто", ("часто",), importance=2),
        ],
    )

    assert calculate_match(a, b) is None


def test_explanation_lists_matched_and_mismatched_important_questions():
    a = make_candidate(
        1,
        [
            values_answer(1, "да", ("да",), importance=2),
            values_answer(2, "да", ("да",), importance=2),
            values_answer(3, "да", ("да",), importance=0),  # неважно — не попадает в список
        ],
    )
    b = make_candidate(
        2,
        [
            values_answer(1, "да", ("да",), importance=2),
            values_answer(2, "нет", ("нет",), importance=2),
            values_answer(3, "нет", ("нет",), importance=2),
        ],
    )

    explanation = build_explanation(a, b)

    assert explanation.matched_important == [1]
    assert explanation.mismatched_important == [2]


def test_calculate_match_includes_explanation_when_above_threshold():
    a = make_candidate(
        1,
        [
            values_answer(1, "да", ("да",), importance=2),
            values_answer(2, "да", ("да",), importance=2),
            values_answer(3, "да", ("да",), importance=2),
        ],
    )
    b = make_candidate(
        2,
        [
            values_answer(1, "да", ("да",), importance=2),
            values_answer(2, "да", ("да",), importance=2),
            values_answer(3, "нет", ("нет",), importance=2),
        ],
    )

    match = calculate_match(a, b)

    assert match is not None
    assert match.explanation.matched_important == [1, 2]
    assert match.explanation.mismatched_important == [3]


# --- "Жеті ата" ---

def test_is_same_clan_true_when_equal():
    a = make_candidate(1, [], clan_ru="Найман")
    b = make_candidate(2, [], clan_ru="Найман")

    assert is_same_clan(a, b) is True


def test_is_same_clan_false_when_different_or_unknown():
    a = make_candidate(1, [], clan_ru="Найман")
    b = make_candidate(2, [], clan_ru="Аргын")
    c = make_candidate(3, [], clan_ru=None)

    assert is_same_clan(a, b) is False
    assert is_same_clan(a, c) is False


# --- Поиск кандидатов ---

def test_find_matches_skips_self_and_already_seen():
    user = make_candidate(1, [values_answer(1, "да", ("да",), importance=2)])
    good = make_candidate(2, [values_answer(1, "да", ("да",), importance=2)])
    seen = make_candidate(3, [values_answer(1, "да", ("да",), importance=2)])

    results = find_matches(user, [user, good, seen], already_seen={3})

    result_ids = [c.user_id for c, _ in results]
    assert result_ids == [2]


def test_find_matches_sorted_by_score_descending():
    user = make_candidate(
        1,
        [
            values_answer(1, "да", ("да",), importance=2),
            values_answer(2, "да", ("да",), importance=1),
        ],
    )
    strong = make_candidate(
        2,
        [
            values_answer(1, "да", ("да",), importance=2),
            values_answer(2, "да", ("да",), importance=2),
        ],
    )
    weaker = make_candidate(
        3,
        [
            values_answer(1, "да", ("да",), importance=2),
            values_answer(2, "нет", ("нет",), importance=1),
        ],
    )

    results = find_matches(user, [strong, weaker], already_seen=set())

    assert [c.user_id for c, _ in results] == [2, 3]


def test_find_matches_excludes_same_clan_when_requested():
    user = make_candidate(1, [values_answer(1, "да", ("да",), importance=2)], clan_ru="Найман")
    same_clan = make_candidate(
        2, [values_answer(1, "да", ("да",), importance=2)], clan_ru="Найман"
    )
    other_clan = make_candidate(
        3, [values_answer(1, "да", ("да",), importance=2)], clan_ru="Аргын"
    )

    results = find_matches(user, [same_clan, other_clan], already_seen=set(), exclude_same_clan=True)

    assert [c.user_id for c, _ in results] == [3]
