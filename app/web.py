"""Shared web utilities: templates, auth, flash, cookies."""

from fastapi import Request, Response
from fastapi.templating import Jinja2Templates
from itsdangerous import URLSafeTimedSerializer

from app.config import settings
from app.theme import resolve_client_display, callsign_from_hostname

PREFIX = "/thermalprinter"

_templates = Jinja2Templates(directory="app/templates")


def render(name: str, ctx: dict) -> Response:
    """Render a Jinja2 template. Compatible with Starlette 1.0+."""
    request = ctx["request"]
    return _templates.TemplateResponse(request, name, ctx)

_signer = URLSafeTimedSerializer(settings.SECRET_KEY)
_ADMIN_COOKIE = "admin_session"
_CALLSIGN_COOKIE = "callsign"
_FLASH_COOKIE = "flash"


def is_admin(request: Request) -> bool:
    token = request.cookies.get(_ADMIN_COOKIE)
    if not token:
        return False
    try:
        data = _signer.loads(token, max_age=86400)
        return data == "admin"
    except Exception:
        return False


def set_admin_cookie(response: Response):
    token = _signer.dumps("admin")
    response.set_cookie(_ADMIN_COOKIE, token, httponly=True, max_age=86400)


def clear_admin_cookie(response: Response):
    response.delete_cookie(_ADMIN_COOKIE)


def get_callsign(request: Request, client_ip: str) -> str:
    stored = request.cookies.get(_CALLSIGN_COOKIE, "")
    if stored:
        return stored
    return callsign_from_hostname(client_ip)


def save_callsign_cookie(response: Response, callsign: str):
    if callsign:
        response.set_cookie(_CALLSIGN_COOKIE, callsign.strip().upper(), max_age=31536000)


def set_flash(response: Response, msg: str, flash_type: str = "success"):
    response.set_cookie(_FLASH_COOKIE, f"{flash_type}:{msg}", max_age=10)


def get_flash(request: Request) -> tuple[str, str]:
    raw = request.cookies.get(_FLASH_COOKIE, "")
    if not raw:
        return "", ""
    if ":" in raw:
        ftype, msg = raw.split(":", 1)
        return msg, ftype
    return raw, "success"


async def base_context(request: Request) -> dict:
    client_ip = request.client.host if request.client else ""
    flash_msg, flash_type = get_flash(request)
    return {
        "request": request,
        "P": PREFIX,
        "callsign": settings.NODE_CALLSIGN,
        "version": settings.APP_VERSION,
        "client_display": resolve_client_display(client_ip) if client_ip else "",
        "is_admin": is_admin(request),
        "printer_online": None,
        "queue_depth": None,
        "flash_msg": flash_msg,
        "flash_type": flash_type,
    }
