from aiogram import Router

from bot.handlers import feedback, matches, start, survey

router = Router()
router.include_router(start.router)
router.include_router(survey.router)
router.include_router(matches.router)
router.include_router(feedback.router)
