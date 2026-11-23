from fastapi import APIRouter

from app.api.routes import (
    dashboard_equipment,
    dashboard_menu,
    dashboard_pos,
    dashboard_quotes,
    dashboard_reports,
    dashboard_reservations,
    dashboard_warehouses,
)

router = APIRouter(prefix="/dashboard")
router.include_router(dashboard_menu.router)
router.include_router(dashboard_warehouses.router)
router.include_router(dashboard_equipment.router)
router.include_router(dashboard_quotes.router)
router.include_router(dashboard_reservations.router)
router.include_router(dashboard_pos.router)
router.include_router(dashboard_reports.router)
