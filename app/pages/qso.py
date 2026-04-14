from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from app.config import settings
from app.db import enqueue_job, get_queue_depth
from app.web import base_context, get_callsign, save_callsign_cookie, set_flash, render, PREFIX
from app.models import QSOJob
from app.rate_limit import check_rate_limit

router = APIRouter()

MODES = [
    'SSB', 'FM', 'AM', 'CW', 'FT8', 'FT4', 'DMR',
    'DSTAR', 'C4FM', 'JS8', 'WINLINK', 'OTHER',
]


@router.get('/qso')
async def qso_form(request: Request):
    ctx = await base_context(request)
    client_ip = request.client.host if request.client else ''
    now = datetime.now(timezone.utc)
    ctx['modes'] = MODES
    ctx['form'] = {
        'callsign': get_callsign(request, client_ip),
        'date': now.strftime('%Y-%m-%d'),
        'time_utc': now.strftime('%H:%M'),
        'mode': 'FM',
    }
    resp = render("qso.html", ctx)
    resp.delete_cookie("flash")
    return resp


@router.post('/qso')
async def qso_submit(request: Request):
    client_ip = request.client.host if request.client else 'unknown'
    form_data = await request.form()
    form = dict(form_data)

    if not check_rate_limit(client_ip):
        ctx = await base_context(request)
        ctx['modes'] = MODES
        ctx['form'] = form
        ctx['flash_msg'] = "Easy, OM! Rig's still warming up."
        ctx['flash_type'] = 'warning'
        return render("qso.html", ctx)

    try:
        job = QSOJob(
            callsign=form.get('callsign', ''),
            date=form.get('date', ''),
            time_utc=form.get('time_utc', ''),
            frequency=form.get('frequency', ''),
            mode=form.get('mode', 'SSB'),
            station_worked=form.get('station_worked', ''),
            signal_sent=form.get('signal_sent', ''),
            signal_received=form.get('signal_received', ''),
            notes=form.get('notes', ''),
        )
    except ValidationError as e:
        ctx = await base_context(request)
        ctx['modes'] = MODES
        ctx['form'] = form
        errors = [err['msg'].removeprefix('Value error, ') for err in e.errors()]
        ctx['flash_msg'] = ' / '.join(errors)
        ctx['flash_type'] = 'error'
        return render("qso.html", ctx)

    depth = await get_queue_depth()
    if depth >= settings.MAX_QUEUE_SIZE:
        ctx = await base_context(request)
        ctx['modes'] = MODES
        ctx['form'] = form
        ctx['flash_msg'] = 'Queue is full up! Stand by.'
        ctx['flash_type'] = 'error'
        return render("qso.html", ctx)

    job_id = await enqueue_job('qso', client_ip, job.model_dump())
    resp = RedirectResponse(f'{PREFIX}/qso', status_code=303)
    save_callsign_cookie(resp, job.callsign)
    set_flash(resp, f'QSL! Contact slip #{job_id} headed to the printer. Position {depth + 1}.')
    return resp
