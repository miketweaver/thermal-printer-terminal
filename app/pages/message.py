from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from app.config import settings
from app.db import enqueue_job, get_queue_depth
from app.web import base_context, get_callsign, save_callsign_cookie, set_flash, render, PREFIX
from app.models import MessageJob
from app.rate_limit import check_rate_limit

router = APIRouter()

CATEGORIES = [
    ('general', 'General'),
    ('emergency', 'Emergency'),
    ('weather', 'Weather'),
    ('net-control', 'Net Control'),
    ('info', 'Info'),
    ('social', 'Social'),
]


@router.get('/message')
async def message_form(request: Request):
    ctx = await base_context(request)
    client_ip = request.client.host if request.client else ''
    ctx['categories'] = CATEGORIES
    ctx['form'] = {'callsign': get_callsign(request, client_ip), 'category': 'general'}
    resp = render("message.html", ctx)
    resp.delete_cookie("flash")
    return resp


@router.post('/message')
async def message_submit(request: Request):
    client_ip = request.client.host if request.client else 'unknown'
    form_data = await request.form()
    form = dict(form_data)

    if not check_rate_limit(client_ip):
        ctx = await base_context(request)
        ctx['categories'] = CATEGORIES
        ctx['form'] = form
        ctx['flash_msg'] = "Easy, OM! Rig's still warming up."
        ctx['flash_type'] = 'warning'
        return render("message.html", ctx)

    try:
        job = MessageJob(
            callsign=form.get('callsign', ''),
            body=form.get('body', ''),
            category=form.get('category', 'general'),
        )
    except ValidationError as e:
        ctx = await base_context(request)
        ctx['categories'] = CATEGORIES
        ctx['form'] = form
        errors = [err['msg'].removeprefix('Value error, ') for err in e.errors()]
        ctx['flash_msg'] = ' / '.join(errors)
        ctx['flash_type'] = 'error'
        return render("message.html", ctx)

    depth = await get_queue_depth()
    if depth >= settings.MAX_QUEUE_SIZE:
        ctx = await base_context(request)
        ctx['categories'] = CATEGORIES
        ctx['form'] = form
        ctx['flash_msg'] = 'Queue is full up! Stand by.'
        ctx['flash_type'] = 'error'
        return render("message.html", ctx)

    job_id = await enqueue_job('message', client_ip, job.model_dump())
    resp = RedirectResponse(f'{PREFIX}/message', status_code=303)
    save_callsign_cookie(resp, job.callsign)
    set_flash(resp, f'QSL! Message #{job_id} is in the hopper. Position {depth + 1} in queue.')
    return resp
