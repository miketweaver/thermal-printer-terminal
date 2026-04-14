"""
ESP32-CAM capture module via Tasmota HTTP endpoints.

Handles flash control and JPEG capture from a Tasmota-flashed ESP32-CAM.
Camera settings (host, user, pass, enable) are stored in the DB settings table.
"""

import asyncio
import logging
from urllib.parse import quote

import httpx

from app.db import get_setting

logger = logging.getLogger(__name__)

# Settings keys in the DB
CAM_ENABLED = "camera_enabled"
CAM_HOST = "camera_host"
CAM_USER = "camera_user"
CAM_PASS = "camera_pass"


async def is_camera_enabled() -> bool:
    """Check if the camera feature is enabled in settings."""
    val = await get_setting(CAM_ENABLED, "0")
    return val == "1"


async def _get_cam_settings() -> tuple[str, str, str]:
    """Return (host, user, password) from DB settings."""
    host = await get_setting(CAM_HOST, "")
    user = await get_setting(CAM_USER, "")
    passwd = await get_setting(CAM_PASS, "")
    return host, user, passwd


def _cmd_url(host: str, user: str, passwd: str, cmnd: str) -> str:
    """Build a Tasmota command URL with optional auth."""
    auth = ""
    if user:
        auth = f"user={quote(user)}&password={quote(passwd)}&"
    return f"http://{host}/cm?{auth}cmnd={quote(cmnd)}"


async def _send_cmd(host: str, user: str, passwd: str, cmnd: str,
                    client: httpx.AsyncClient, timeout: float = 5.0) -> str:
    """Send a Tasmota command and return the response body."""
    url = _cmd_url(host, user, passwd, cmnd)
    resp = await client.get(url, timeout=timeout)
    resp.raise_for_status()
    return resp.text


async def _fetch_image(host: str, user: str, passwd: str,
                       client: httpx.AsyncClient, timeout: float = 60.0) -> bytes:
    """Fetch JPEG from /wc.jpg using HTTP Basic Auth.

    ESP32-CAMs are slow over mesh — a 5KB JPEG can take 25+ seconds.
    """
    url = f"http://{host}/wc.jpg"
    auth = (user, passwd) if user else None
    # Use a generous per-phase timeout: the ESP32 streams bytes slowly
    t = httpx.Timeout(timeout, connect=10.0)
    resp = await client.get(url, timeout=t, auth=auth)
    resp.raise_for_status()
    return resp.content


async def capture_photo() -> bytes:
    """
    Capture a JPEG from the ESP32-CAM.

    Sequence: flash on -> 2s settle -> capture JPEG -> flash off.
    Returns raw JPEG bytes.
    """
    if not await is_camera_enabled():
        raise CameraError("Camera is not enabled")

    host, user, passwd = await _get_cam_settings()
    if not host:
        raise CameraError("Camera host not configured")

    async with httpx.AsyncClient() as client:
        # Configure and turn flash on
        try:
            await _send_cmd(host, user, passwd, "WcResolution 10", client, timeout=5.0)
            await _send_cmd(host, user, passwd, "Dimmer 25", client, timeout=5.0)
            await _send_cmd(host, user, passwd, "Power On", client, timeout=5.0)
        except Exception as e:
            logger.warning("Flash on failed (continuing anyway): %s", e)

        # Let camera auto-exposure adjust to the flash
        await asyncio.sleep(2.0)

        # Capture JPEG
        try:
            jpeg_data = await _fetch_image(host, user, passwd, client, timeout=15.0)
        except Exception as e:
            # Turn flash off even if capture fails
            try:
                await _send_cmd(host, user, passwd, "Power Off", client, timeout=5.0)
            except Exception:
                pass
            raise CameraError(f"Photo capture failed: {e}")

        # Turn flash off immediately after capture
        try:
            await _send_cmd(host, user, passwd, "Power Off", client, timeout=5.0)
        except Exception as e:
            logger.warning("Flash off failed: %s", e)

    if len(jpeg_data) < 100:
        raise CameraError("Captured image too small — camera may not be ready")

    logger.info("Captured photo: %d bytes", len(jpeg_data))
    return jpeg_data


async def test_camera() -> dict:
    """
    Test camera connectivity. Returns a status dict.
    Flashes briefly and captures a test image.
    """
    result = {"reachable": False, "flash": False, "capture": False, "error": ""}

    host, user, passwd = await _get_cam_settings()
    if not host:
        result["error"] = "Camera host not configured"
        return result

    async with httpx.AsyncClient() as client:
        # Test basic connectivity
        try:
            resp = await client.get(f"http://{host}/", timeout=5.0)
            result["reachable"] = resp.status_code < 500
        except Exception as e:
            result["error"] = f"Cannot reach camera at {host}: {e}"
            return result

        # Test flash command
        try:
            await _send_cmd(host, user, passwd, "Power On", client, timeout=5.0)
            await asyncio.sleep(0.3)
            await _send_cmd(host, user, passwd, "Power Off", client, timeout=5.0)
            result["flash"] = True
        except Exception as e:
            result["error"] = f"Flash command failed: {e}"
            return result

        # Test image capture (uses HTTP Basic Auth, not query-string)
        try:
            jpeg_data = await _fetch_image(host, user, passwd, client, timeout=60.0)
            if len(jpeg_data) > 100:
                result["capture"] = True
            else:
                result["error"] = f"Image too small ({len(jpeg_data)} bytes)"
        except Exception as e:
            result["error"] = f"Image capture failed: {e}"

    return result


class CameraError(Exception):
    """Raised when camera operations fail."""
    pass
