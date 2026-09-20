import enum
from datetime import date, datetime, timezone

from sqlalchemy import JSON, ForeignKey, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class UserStatus(str, enum.Enum):
    NEW = "new"
    VERIFIED = "verified"
    BLOCKED = "blocked"


class Language(str, enum.Enum):
    KZ = "kz"
    RU = "ru"


class Gender(str, enum.Enum):
    MALE = "male"
    FEMALE = "female"


class QuestionLayer(str, enum.Enum):
    FILTER = "filter"
    VALUES = "values"
    LIFESTYLE = "lifestyle"


class Importance(int, enum.Enum):
    NOT_IMPORTANT = 0
    IMPORTANT = 1
    VERY_IMPORTANT = 2


class MatchStatus(str, enum.Enum):
    PENDING = "pending"
    INTERESTED = "interested"
    DECLINED = "declined"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(primary_key=True)
    tg_id: Mapped[int] = mapped_column(unique=True, index=True)
    name: Mapped[str]
    gender: Mapped[Gender]
    birth_date: Mapped[date]
    city: Mapped[str]
    willing_to_relocate: Mapped[bool] = mapped_column(default=False)
    status: Mapped[UserStatus] = mapped_column(default=UserStatus.NEW)
    language: Mapped[Language] = mapped_column(default=Language.RU)
    consent_date: Mapped[datetime | None] = mapped_column(default=None)
    consent_version: Mapped[str | None] = mapped_column(default=None)
    # Род (для добровольной проверки "жеті ата"). Хранится только для этой
    # проверки, нигде не показывается и не используется как фильтр поиска.
    clan_ru: Mapped[str | None] = mapped_column(default=None)

    photos: Mapped[list["Photo"]] = relationship(back_populates="user")
    answers: Mapped[list["Answer"]] = relationship(back_populates="user")


class Photo(Base):
    __tablename__ = "photos"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    file_id: Mapped[str]
    is_selfie_check: Mapped[bool] = mapped_column(default=False)

    user: Mapped["User"] = relationship(back_populates="photos")


class Question(Base):
    __tablename__ = "questions"

    id: Mapped[int] = mapped_column(primary_key=True)
    layer: Mapped[QuestionLayer]
    text_ru: Mapped[str]
    text_kz: Mapped[str]
    options: Mapped[list] = mapped_column(JSON)


class Answer(Base):
    """Ответ пользователя на один вопрос анкеты.

    question_key — стабильный технический ключ вопроса из core/questions.py
    (например, "smoking"), а не номер строки в таблице questions: набор
    вопросов MVP задан в коде, а не в базе (см. core/questions.py).
    """

    __tablename__ = "answers"
    __table_args__ = (UniqueConstraint("user_id", "question_key"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    question_key: Mapped[str]
    own_option: Mapped[str]
    acceptable_options: Mapped[list] = mapped_column(JSON)
    importance: Mapped[Importance]

    user: Mapped["User"] = relationship(back_populates="answers")


class Match(Base):
    __tablename__ = "matches"

    id: Mapped[int] = mapped_column(primary_key=True)
    user_a_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    user_b_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    score: Mapped[float]
    week: Mapped[date]
    status_a: Mapped[MatchStatus] = mapped_column(default=MatchStatus.PENDING)
    status_b: Mapped[MatchStatus] = mapped_column(default=MatchStatus.PENDING)
    created_at: Mapped[datetime] = mapped_column(
        default=lambda: datetime.now(timezone.utc).replace(tzinfo=None)
    )
    # Момент, когда ОБА отметили "интересно" — от него считаются 3 дня до
    # запроса отзыва (см. core/feedback.py). None, если взаимности ещё нет.
    mutual_at: Mapped[datetime | None] = mapped_column(default=None)
    feedback_requested_a: Mapped[bool] = mapped_column(default=False)
    feedback_requested_b: Mapped[bool] = mapped_column(default=False)


class Feedback(Base):
    __tablename__ = "feedback"

    id: Mapped[int] = mapped_column(primary_key=True)
    match_id: Mapped[int] = mapped_column(ForeignKey("matches.id"))
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    met: Mapped[bool | None] = mapped_column(default=None)
    liked: Mapped[bool | None] = mapped_column(default=None)
    reason: Mapped[str | None] = mapped_column(default=None)


class SchedulerState(Base):
    """Служебная таблица для фоновых задач бота.

    Например, хранит, за какую неделю уже был выполнен расчёт подбора,
    чтобы не считать его повторно при каждом перезапуске бота.
    """

    __tablename__ = "scheduler_state"

    key: Mapped[str] = mapped_column(primary_key=True)
    value: Mapped[str]


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(primary_key=True)
    from_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    on_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    reason: Mapped[str]
    resolved: Mapped[bool] = mapped_column(default=False)
