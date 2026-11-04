from fastapi import APIRouter

from app.modules.bookings.router import router as bookings_router
from app.modules.crm.router import router as crm_router
from app.modules.excel_sync.router import router as excel_router
from app.modules.properties.router import router as properties_router

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(properties_router)
api_router.include_router(bookings_router)
api_router.include_router(crm_router)
api_router.include_router(excel_router)
