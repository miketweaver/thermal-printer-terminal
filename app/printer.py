"""
ESC/POS print engine for Epson TM-m30III.

Handles raw TCP socket communication and ESC/POS byte formatting.
All printer contact goes through send_to_printer().
"""

import asyncio
import logging
import textwrap

from app.config import settings
from app.text_utils import sanitize_text

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# ESC/POS command constants
# ---------------------------------------------------------------------------
ESC = b"\x1b"
GS = b"\x1d"
LF = b"\n"

# Initialize printer (reset to defaults)
INIT = ESC + b"@"

# Text style
BOLD_ON = ESC + b"\x45\x01"
BOLD_OFF = ESC + b"\x45\x00"
UNDERLINE_ON = ESC + b"\x2d\x01"
UNDERLINE_OFF = ESC + b"\x2d\x00"

# Alignment
ALIGN_LEFT = ESC + b"\x61\x00"
ALIGN_CENTER = ESC + b"\x61\x01"
ALIGN_RIGHT = ESC + b"\x61\x02"

# Character size — GS ! n
# Bits 0-3: height magnification, Bits 4-7: width magnification
SIZE_NORMAL = GS + b"\x21\x00"
SIZE_DOUBLE_H = GS + b"\x21\x01"
SIZE_DOUBLE_W = GS + b"\x21\x10"
SIZE_DOUBLE = GS + b"\x21\x11"

# Paper control
CUT_PARTIAL = GS + b"V\x01"
CUT_FULL = GS + b"V\x00"
FEED_LINES = ESC + b"d"  # followed by number-of-lines byte


class PrinterError(Exception):
    """Raised when communication with the printer fails."""
    pass


# ---------------------------------------------------------------------------
# Transport
# ---------------------------------------------------------------------------
async def send_to_printer(data: bytes) -> None:
    """Send raw bytes to the printer over TCP."""
    host = settings.PRINTER_HOST
    port = settings.PRINTER_PORT
    timeout = settings.PRINTER_TIMEOUT

    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(host, port),
            timeout=timeout,
        )
    except asyncio.TimeoutError:
        raise PrinterError(f"Connection to {host}:{port} timed out after {timeout}s")
    except OSError as e:
        raise PrinterError(f"Cannot connect to {host}:{port}: {e}")

    try:
        writer.write(data)
        await asyncio.wait_for(writer.drain(), timeout=timeout)
    except asyncio.TimeoutError:
        raise PrinterError(f"Send to {host}:{port} timed out")
    except OSError as e:
        raise PrinterError(f"Write error to {host}:{port}: {e}")
    finally:
        writer.close()
        try:
            await writer.wait_closed()
        except Exception:
            pass

    logger.info("Sent %d bytes to %s:%d", len(data), host, port)


async def check_printer_reachable() -> bool:
    """Quick TCP connect test. Returns True if printer accepts connection."""
    try:
        reader, writer = await asyncio.wait_for(
            asyncio.open_connection(settings.PRINTER_HOST, settings.PRINTER_PORT),
            timeout=2,
        )
        writer.close()
        await writer.wait_closed()
        return True
    except Exception:
        return False


# ---------------------------------------------------------------------------
# Text formatting helpers
# ---------------------------------------------------------------------------
def wrap_text(text: str, width: int = None) -> list[str]:
    """Word-wrap text to receipt width."""
    width = width or settings.PAPER_WIDTH_CHARS
    lines = []
    for paragraph in text.split("\n"):
        if paragraph.strip() == "":
            lines.append("")
        else:
            lines.extend(textwrap.wrap(paragraph, width=width) or [""])
    return lines


def center_text(text: str, width: int = None) -> str:
    """Center a string within the receipt width."""
    width = width or settings.PAPER_WIDTH_CHARS
    return text.center(width)


def separator(char: str = "-", width: int = None) -> str:
    """Full-width separator line."""
    width = width or settings.PAPER_WIDTH_CHARS
    return char * width


def format_kv(key: str, value: str, width: int = None) -> str:
    """Format a key-value pair: 'KEY:  value' left-aligned."""
    width = width or settings.PAPER_WIDTH_CHARS
    prefix = f"{key}: "
    remaining = width - len(prefix)
    if remaining <= 0:
        return prefix + str(value)
    val_str = str(value)
    if len(val_str) <= remaining:
        return prefix + val_str
    # Wrap the value portion
    wrapped = textwrap.wrap(val_str, width=remaining)
    result = prefix + wrapped[0]
    indent = " " * len(prefix)
    for line in wrapped[1:]:
        result += "\n" + indent + line
    return result


def text_to_bytes(text: str) -> bytes:
    """Sanitize and encode text for the thermal printer."""
    return sanitize_text(text).encode("ascii", errors="replace")


def build_receipt(*parts) -> bytes:
    """Concatenate a mix of bytes and str parts into a single byte sequence."""
    result = bytearray()
    for part in parts:
        if isinstance(part, bytes):
            result.extend(part)
        elif isinstance(part, str):
            result.extend(text_to_bytes(part))
        elif isinstance(part, bytearray):
            result.extend(part)
    return bytes(result)


def feed_and_cut() -> bytes:
    """Feed paper and optionally cut."""
    data = FEED_LINES + b"\x04"  # Feed 4 lines
    if settings.ENABLE_CUT:
        data += CUT_PARTIAL
    return data
