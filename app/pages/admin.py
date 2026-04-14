import os

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse, FileResponse

from app.config import settings
from app.db import (
    get_recent_jobs, get_job_stats, get_queue_depth,
    delete_job, requeue_job, enqueue_job,
    get_all_settings, set_setting,
)
from app.web import (
    base_context, is_admin, set_admin_cookie, clear_admin_cookie,
    set_flash, render, PREFIX,
)
from app.printer import check_printer_reachable
from app.camera import CAM_ENABLED, CAM_HOST, CAM_USER, CAM_PASS, test_camera
from app.helpers import friendly_time, build_from, build_details

router = APIRouter()


@router.get('/admin/login')
async def admin_login_page(request: Request):
    if is_admin(request):
        return RedirectResponse(f'{PREFIX}/admin', status_code=303)
    ctx = await base_context(request)
    resp = render("admin_login.html", ctx)
    resp.delete_cookie("flash")
    return resp


@router.post('/admin/login')
async def admin_login_submit(request: Request):
    form_data = await request.form()
    password = form_data.get('password', '')

    if password == settings.ADMIN_PASSWORD:
        resp = RedirectResponse(f'{PREFIX}/admin', status_code=303)
        set_admin_cookie(resp)
        return resp

    ctx = await base_context(request)
    ctx['flash_msg'] = 'No copy. Wrong password.'
    ctx['flash_type'] = 'error'
    return render("admin_login.html", ctx)


@router.get('/admin/logout')
async def admin_logout(request: Request):
    resp = RedirectResponse(f'{PREFIX}/', status_code=303)
    clear_admin_cookie(resp)
    return resp


@router.get('/admin')
async def admin_page(request: Request):
    if not is_admin(request):
        return RedirectResponse(f'{PREFIX}/admin/login', status_code=303)

    client_ip = request.client.host if request.client else 'admin'
    ctx = await base_context(request)
    ctx['printer_online'] = await check_printer_reachable()
    ctx['queue_depth'] = await get_queue_depth()
    ctx['printer_host'] = settings.PRINTER_HOST
    ctx['printer_port'] = settings.PRINTER_PORT
    ctx['stats'] = await get_job_stats()

    # Camera settings
    all_settings = await get_all_settings()
    ctx['cam_enabled'] = all_settings.get(CAM_ENABLED, '0') == '1'
    ctx['cam_host'] = all_settings.get(CAM_HOST, '')
    ctx['cam_user'] = all_settings.get(CAM_USER, '')
    ctx['cam_pass'] = all_settings.get(CAM_PASS, '')

    jobs = await get_recent_jobs(100)
    ctx['jobs'] = [
        {
            'id': j['id'],
            'job_type': j['job_type'] or '',
            'from_display': build_from(j),
            'status': j['status'],
            'time': friendly_time(j['submitted_at'] or ''),
            'details': build_details(j, show_full=True),
            'has_image': bool(j['has_image']),
        }
        for j in jobs
    ]

    resp = render("admin.html", ctx)
    resp.delete_cookie("flash")
    return resp


@router.post('/admin/test-print')
async def admin_test_print(request: Request):
    if not is_admin(request):
        return RedirectResponse(f'{PREFIX}/admin/login', status_code=303)

    client_ip = request.client.host if request.client else 'admin'
    job_id = await enqueue_job('test', client_ip, {})
    resp = RedirectResponse(f'{PREFIX}/admin', status_code=303)
    set_flash(resp, f'Test page #{job_id} headed to the printer.')
    return resp


@router.post('/admin/reprint/{job_id}')
async def admin_reprint(request: Request, job_id: int):
    if not is_admin(request):
        return RedirectResponse(f'{PREFIX}/admin/login', status_code=303)

    await requeue_job(job_id)
    resp = RedirectResponse(f'{PREFIX}/admin', status_code=303)
    set_flash(resp, f'Roger, #{job_id} back in the hopper.')
    return resp


@router.post('/admin/delete/{job_id}')
async def admin_delete(request: Request, job_id: int):
    if not is_admin(request):
        return RedirectResponse(f'{PREFIX}/admin/login', status_code=303)

    await delete_job(job_id)
    resp = RedirectResponse(f'{PREFIX}/admin', status_code=303)
    set_flash(resp, f'Job #{job_id} scrubbed.')
    return resp


@router.post('/admin/camera')
async def admin_camera_save(request: Request):
    if not is_admin(request):
        return RedirectResponse(f'{PREFIX}/admin/login', status_code=303)

    form_data = await request.form()
    enabled = '1' if form_data.get('cam_enabled') else '0'
    host = str(form_data.get('cam_host', '')).strip()
    user = str(form_data.get('cam_user', '')).strip()
    passwd = str(form_data.get('cam_pass', '')).strip()

    await set_setting(CAM_ENABLED, enabled)
    await set_setting(CAM_HOST, host)
    await set_setting(CAM_USER, user)
    await set_setting(CAM_PASS, passwd)

    resp = RedirectResponse(f'{PREFIX}/admin', status_code=303)
    set_flash(resp, 'Camera settings saved.')
    return resp


@router.post('/admin/camera/test')
async def admin_camera_test(request: Request):
    if not is_admin(request):
        return RedirectResponse(f'{PREFIX}/admin/login', status_code=303)

    result = await test_camera()
    if result['capture']:
        msg = 'Camera OK! Reachable, flash works, image captured.'
    elif result['flash']:
        msg = f'Partial: flash works but capture failed. {result["error"]}'
    elif result['reachable']:
        msg = f'Partial: reachable but commands failed. {result["error"]}'
    else:
        msg = f'Camera unreachable. {result["error"]}'

    flash_type = 'success' if result['capture'] else 'error'
    resp = RedirectResponse(f'{PREFIX}/admin', status_code=303)
    set_flash(resp, msg, flash_type)
    return resp


@router.get('/images/{job_id}.jpg')
async def serve_image(job_id: int):
    images_dir = os.path.join(os.path.dirname(settings.DATABASE_PATH) or ".", "images")
    path = os.path.join(images_dir, f"{job_id}.jpg")
    if not os.path.isfile(path):
        return RedirectResponse(f'{PREFIX}/admin', status_code=303)
    return FileResponse(path, media_type="image/jpeg")
