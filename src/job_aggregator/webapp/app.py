from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, Form, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from job_aggregator.db.engine import init_db
from job_aggregator.db.models import User
from job_aggregator.webapp.auth import (
    clear_session_cookie,
    ensure_webapp_secret,
    require_auth_page,
    set_session_cookie,
    touch_last_login,
    verify_password,
)
from job_aggregator.webapp.routers import families, offer_views, offers, regions, users

logger = logging.getLogger(__name__)

_HERE = Path(__file__).resolve().parent


@asynccontextmanager
async def lifespan(application: FastAPI):  # noqa: ARG001
    ensure_webapp_secret()
    await init_db()
    logger.info("Database initialized")
    yield


app = FastAPI(title="Section23 Jobs", lifespan=lifespan)

app.mount("/static", StaticFiles(directory=_HERE / "static"), name="static")
templates = Jinja2Templates(directory=_HERE / "templates")

app.include_router(families.router)
app.include_router(regions.router)
app.include_router(offers.router)
app.include_router(offer_views.router)
app.include_router(users.router)


# ── Page routes ───────────────────────────────────────────────────────

@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@app.post("/login")
async def login_submit(
    request: Request,
    username: str = Form(...),
    password: str = Form(...),
):
    from sqlalchemy import select

    from job_aggregator.db.engine import async_session

    async with async_session() as session:
        result = await session.execute(
            select(User).where(User.username == username, User.is_active == True)  # noqa: E712
        )
        user = result.scalar_one_or_none()

    if not user or not verify_password(password, user.hashed_password):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": "Identifiants incorrects"},
            status_code=status.HTTP_401_UNAUTHORIZED,
        )

    await touch_last_login(user.id)

    response = RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    set_session_cookie(response, user.id)
    return response


@app.get("/logout")
async def logout():
    response = RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    clear_session_cookie(response)
    return response


@app.get("/", response_class=HTMLResponse)
async def index_page(request: Request, current_user: User = Depends(require_auth_page)):
    return templates.TemplateResponse(request, "index.html", {"current_user": current_user})


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request, current_user: User = Depends(require_auth_page)):
    if not current_user.is_admin:
        return RedirectResponse(url="/", status_code=status.HTTP_303_SEE_OTHER)
    return templates.TemplateResponse(request, "admin.html", {"current_user": current_user})


@app.exception_handler(307)
async def redirect_to_login(request: Request, exc):  # noqa: ARG001
    return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
