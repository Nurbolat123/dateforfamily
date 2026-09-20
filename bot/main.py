import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from bot.handlers import router
from bot.scheduler import feedback_scheduler, matching_scheduler
from core.config import settings


async def main() -> None:
    logging.basicConfig(level=logging.INFO)

    if not settings.bot_token:
        raise RuntimeError(
            "BOT_TOKEN не задан. Скопируйте .env.example в .env и впишите токен от @BotFather."
        )

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dispatcher = Dispatcher()
    dispatcher.include_router(router)

    asyncio.create_task(matching_scheduler(bot))
    asyncio.create_task(feedback_scheduler(bot))

    await dispatcher.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
