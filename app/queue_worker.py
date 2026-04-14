"""
Background async worker that consumes the print job queue.

Runs as a single coroutine in the FastAPI lifespan — processes one job
at a time since the printer is a single physical resource.
"""

import asyncio
import io
import json
import logging
import os

from app.config import settings
from app.db import get_next_queued_job, update_job_status, increment_retry, mark_job_has_image
from app.printer import send_to_printer, PrinterError
from app.templates_engine import (
    render_message_receipt,
    render_status_ticket,
    render_qso_receipt,
    render_emcomm_receipt,
    render_test_receipt,
)
from app.camera import is_camera_enabled, capture_photo, CameraError

logger = logging.getLogger(__name__)


def _render_job(job_type: str, content: dict, submitted_by: str = "") -> bytes:
    """Dispatch to the correct receipt renderer based on job type."""
    if job_type == "message":
        return render_message_receipt(content, submitted_by)
    elif job_type == "status":
        return render_status_ticket(content, submitted_by)
    elif job_type == "qso":
        return render_qso_receipt(content, submitted_by)
    elif job_type == "emcomm":
        return render_emcomm_receipt(content["template_type"], content["fields"], submitted_by)
    elif job_type == "test":
        return render_test_receipt()
    else:
        raise ValueError(f"Unknown job type: {job_type}")


async def _capture_proof_photo(job_id: int):
    """If camera is enabled, take a proof-of-print photo and save it."""
    try:
        if not await is_camera_enabled():
            return

        # Brief pause for the paper to finish advancing
        await asyncio.sleep(1.5)

        jpeg_data = await capture_photo()
        raw_size = len(jpeg_data)

        # Re-encode to strip EXIF/metadata and optimize Huffman tables
        try:
            from PIL import Image
            img = Image.open(io.BytesIO(jpeg_data))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)
            jpeg_data = buf.getvalue()
        except Exception as e:
            logger.debug("JPEG optimization skipped: %s", e)

        images_dir = os.path.join(os.path.dirname(settings.DATABASE_PATH) or ".", "images")
        os.makedirs(images_dir, exist_ok=True)
        path = os.path.join(images_dir, f"{job_id}.jpg")
        with open(path, "wb") as f:
            f.write(jpeg_data)

        await mark_job_has_image(job_id)

        logger.info("Proof photo saved for job #%d (%d -> %d bytes)", job_id, raw_size, len(jpeg_data))

    except CameraError as e:
        logger.warning("Proof photo failed for job #%d: %s", job_id, e)
    except Exception as e:
        logger.warning("Unexpected error capturing proof photo for job #%d: %s", job_id, e)


async def queue_worker_loop():
    """Main worker loop — poll queue, print, update status."""
    logger.info("Queue worker started")

    while True:
        job = None
        try:
            job = await get_next_queued_job()

            if job is None:
                await asyncio.sleep(2)
                continue

            job_id = job["id"]
            job_type = job["job_type"]
            logger.info("Processing job #%d (type=%s)", job_id, job_type)

            await update_job_status(job_id, "printing")

            content = json.loads(job["content"])
            submitted_by = job["submitted_by"] or ""
            data = _render_job(job_type, content, submitted_by)

            await send_to_printer(data)

            await update_job_status(job_id, "done")
            logger.info("Job #%d completed (%d bytes sent)", job_id, len(data))

            # Proof-of-print photo: capture after successful print
            await _capture_proof_photo(job_id)

        except PrinterError as e:
            if job is not None:
                retry_count = job["retry_count"] + 1
                logger.warning(
                    "Printer error on job #%d (retry %d/%d): %s",
                    job["id"], retry_count, settings.PRINTER_RETRY_MAX, e,
                )
                await increment_retry(job["id"])
                if retry_count <= settings.PRINTER_RETRY_MAX:
                    await update_job_status(job["id"], "queued", str(e))
                    await asyncio.sleep(5)  # Back off before retry
                else:
                    await update_job_status(job["id"], "failed", str(e))

        except asyncio.CancelledError:
            logger.info("Queue worker shutting down")
            break

        except Exception as e:
            logger.exception("Unexpected error in queue worker")
            if job is not None:
                await update_job_status(job["id"], "failed", f"Internal error: {e}")
            await asyncio.sleep(2)
