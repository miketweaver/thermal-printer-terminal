from fastapi import APIRouter, Request

from app.db import get_queue_depth, get_recent_jobs
from app.web import base_context, get_callsign, render, is_admin
from app.printer import check_printer_reachable
from app.helpers import friendly_time, build_from, build_details

router = APIRouter()


@router.get('/')
async def home_page(request: Request):
    ctx = await base_context(request)
    client_ip = request.client.host if request.client else ''

    ctx['printer_online'] = await check_printer_reachable()
    ctx['queue_depth'] = await get_queue_depth()
    ctx['user_callsign'] = get_callsign(request, client_ip)

    admin = is_admin(request)
    recent = await get_recent_jobs(limit=10)
    ctx['recent'] = [
        {
            'id': j['id'],
            'job_type': j['job_type'] or '',
            'from_display': build_from(j),
            'status': j['status'],
            'time': friendly_time(j['submitted_at'] or ''),
            'details': build_details(j, show_full=admin),
            'has_image': bool(j['has_image']),
        }
        for j in recent
    ]

    resp = render("home.html", ctx)
    resp.delete_cookie("flash")
    return resp
