"""Фоновые задачи бота: еженедельный подбор и запрос отзывов после встречи.

Работают, пока запущен процесс бота. Что уже было сделано, отмечается в
базе (core.models.SchedulerState / Match.feedback_requested_*), поэтому
перезапуск бота не приводит к повторным действиям.
"""

import asyncio
import logging

from aiogram import Bot

from bot.handlers.feedback import send_feedback_requests
from bot.handlers.matches import send_match_notifications
from core.db import async_session
from core.feedback import find_due_feedback_requests
from core.repository import get_scheduler_value, set_scheduler_value
from core.weekly_matching import run_weekly_matching, week_start

MATCHING_CHECK_INTERVAL_SECONDS = 6 * 60 * 60  # проверяем не слишком часто, чтобы не нагружать базу
FEEDBACK_CHECK_INTERVAL_SECONDS = 6 * 60 * 60
SCHEDULER_KEY = "last_matching_run_week"

logger = logging.getLogger(__name__)


async def run_matching_if_due(bot: Bot) -> None:
    this_week = week_start().isoformat()

    async with async_session() as session:
        last_run = await get_scheduler_value(session, SCHEDULER_KEY)
        if last_run == this_week:
            return

        notifications = await run_weekly_matching(session)
        await set_scheduler_value(session, SCHEDULER_KEY, this_week)

    logger.info("Расчёт подбора за неделю %s: создано уведомлений — %s", this_week, len(notifications))
    await send_match_notifications(bot, notifications)


async def matching_scheduler(bot: Bot) -> None:
    while True:
        try:
            await run_matching_if_due(bot)
        except Exception:
            logger.exception("Ошибка при еженедельном расчёте подбора")

        await asyncio.sleep(MATCHING_CHECK_INTERVAL_SECONDS)


async def run_feedback_requests_if_due(bot: Bot) -> None:
    async with async_session() as session:
        requests = await find_due_feedback_requests(session)

    if requests:
        logger.info("Запросов отзыва к отправке: %s", len(requests))
    await send_feedback_requests(bot, requests)


async def feedback_scheduler(bot: Bot) -> None:
    while True:
        try:
            await run_feedback_requests_if_due(bot)
        except Exception:
            logger.exception("Ошибка при рассылке запросов отзыва")

        await asyncio.sleep(FEEDBACK_CHECK_INTERVAL_SECONDS)
