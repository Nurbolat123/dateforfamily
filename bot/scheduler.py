"""Фоновая задача: раз в неделю сама запускает расчёт подбора и рассылку.

Работает, пока запущен процесс бота. Метка "за какую неделю уже считали"
хранится в базе (core.models.SchedulerState), поэтому перезапуск бота не
приводит к повторному расчёту той же недели.
"""

import asyncio
import logging

from aiogram import Bot

from bot.handlers.matches import send_match_notifications
from core.db import async_session
from core.repository import get_scheduler_value, set_scheduler_value
from core.weekly_matching import run_weekly_matching, week_start

CHECK_INTERVAL_SECONDS = 6 * 60 * 60  # проверяем не слишком часто, чтобы не нагружать базу
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

        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
