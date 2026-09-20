from aiogram import Router

from bot.handlers import start, survey

router = Router()
router.include_router(start.router)
router.include_router(survey.router)
