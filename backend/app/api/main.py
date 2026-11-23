from fastapi import APIRouter

from app.api.routes import (
    concierge,
    equipment,
    menu,
    operations,
    pos,
    public_api,
    quotes,
    reports,
    reservations,
    schedule,
    subscription,
    utils,
    warehouses,
)

api_router = APIRouter()
api_router.include_router(utils.router)
api_router.include_router(subscription.router)
api_router.include_router(operations.router)
api_router.include_router(menu.router)
api_router.include_router(warehouses.router)
api_router.include_router(equipment.router)
api_router.include_router(public_api.router)
api_router.include_router(schedule.router)
api_router.include_router(quotes.router)
api_router.include_router(reservations.router)
api_router.include_router(pos.router)
api_router.include_router(reports.router)
api_router.include_router(concierge.router)
