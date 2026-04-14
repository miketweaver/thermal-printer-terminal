from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse
from pydantic import ValidationError

from app.config import settings
from app.db import enqueue_job, get_queue_depth
from app.web import base_context, set_flash, render, PREFIX
from app.models import EMCOMM_TEMPLATES, EmCommFields
from app.rate_limit import check_rate_limit

router = APIRouter()


@router.get('/emcomm')
async def emcomm_index(request: Request):
    ctx = await base_context(request)
    ctx['templates'] = EMCOMM_TEMPLATES
    resp = render("emcomm.html", ctx)
    resp.delete_cookie("flash")
    return resp


@router.get('/emcomm/{template_type}')
async def emcomm_form(request: Request, template_type: str):
    tmpl = EMCOMM_TEMPLATES.get(template_type)
    if not tmpl:
        return RedirectResponse(f'{PREFIX}/emcomm', status_code=303)

    ctx = await base_context(request)
    ctx['template_type'] = template_type
    ctx['template_name'] = tmpl['name']
    ctx['template_desc'] = tmpl['description']
    ctx['fields'] = tmpl['fields']
    ctx['form'] = {}
    resp = render("emcomm_form.html", ctx)
    resp.delete_cookie("flash")
    return resp


@router.post('/emcomm/{template_type}')
async def emcomm_submit(request: Request, template_type: str):
    tmpl = EMCOMM_TEMPLATES.get(template_type)
    if not tmpl:
        return RedirectResponse(f'{PREFIX}/emcomm', status_code=303)

    client_ip = request.client.host if request.client else 'unknown'
    form_data = await request.form()
    form = dict(form_data)

    def _render_error(msg, ftype='error'):
        ctx_err = {
            'request': request,
            'callsign': settings.NODE_CALLSIGN,
            'version': settings.APP_VERSION,
            'client_display': '',
            'is_admin': False,
            'printer_online': None,
            'queue_depth': None,
            'flash_msg': msg,
            'flash_type': ftype,
            'template_type': template_type,
            'template_name': tmpl['name'],
            'template_desc': tmpl['description'],
            'fields': tmpl['fields'],
            'form': form,
        }
        return render("emcomm_form.html", ctx_err)

    if not check_rate_limit(client_ip):
        return _render_error("Easy, OM! Rig's still warming up.", 'warning')

    fields = {name: form.get(name, '') for name in [fd['name'] for fd in tmpl['fields']]}

    missing = [fd['label'] for fd in tmpl['fields'] if fd.get('required') and not fields.get(fd['name'])]
    if missing:
        return _render_error(f"Required fields missing: {', '.join(missing)}")

    try:
        job = EmCommFields(template_type=template_type, fields=fields)
    except ValidationError as e:
        errors = [err['msg'].removeprefix('Value error, ') for err in e.errors()]
        return _render_error(' / '.join(errors))

    depth = await get_queue_depth()
    if depth >= settings.MAX_QUEUE_SIZE:
        return _render_error('Queue is full up! Stand by.')

    job_id = await enqueue_job('emcomm', client_ip, job.model_dump())
    resp = RedirectResponse(f'{PREFIX}/emcomm/{template_type}', status_code=303)
    set_flash(resp, f'QSL! {tmpl["name"]} #{job_id} headed to the printer. Position {depth + 1}.')
    return resp
