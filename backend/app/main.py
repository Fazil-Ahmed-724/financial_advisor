from fastapi import FastAPI
from fastapi.responses import JSONResponse

from app.database import check_database
from app.config import load_settings
from app.routes_auth import router as auth_router
from app.routes_finance import router as finance_router
from app.routes_dashboard import router as dashboard_router
from app.routes_investments import router as investments_router
from app.routes_decisions import router as decisions_router
from app.routes_books import router as books_router
from app.routes_opportunities import router as opportunities_router
from app.routes_marketplace import router as marketplace_router
from app.routes_intelligence import router as intelligence_router
from app.routes_marketplace_review import router as marketplace_review_router

load_settings()
app = FastAPI(title="Personal AI Wealth Manager", version="0.1.0")
app.include_router(auth_router)
app.include_router(finance_router)
app.include_router(dashboard_router)
app.include_router(investments_router)
app.include_router(decisions_router)
app.include_router(books_router)
app.include_router(opportunities_router)
app.include_router(marketplace_router)
app.include_router(intelligence_router)
app.include_router(marketplace_review_router)


@app.get("/health/live")
def liveness() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/health/ready")
def readiness() -> JSONResponse:
    try:
        check_database()
    except Exception:
        # Never disclose connection strings, passwords, or internal errors.
        return JSONResponse(
            status_code=503,
            content={"status": "unavailable", "database": "unavailable"},
        )
    return JSONResponse(content={"status": "ok", "database": "connected"})
