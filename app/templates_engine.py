"""
Receipt text renderers — converts structured data into ESC/POS byte sequences.

Each render function returns bytes ready to send to the printer.
This is NOT the HTML template layer — this is the printer output layer.
"""

from datetime import datetime, timezone

from app.config import settings
from app.printer import (
    INIT, LF, BOLD_ON, BOLD_OFF, ALIGN_LEFT, ALIGN_CENTER,
    SIZE_NORMAL, SIZE_DOUBLE_H, SIZE_DOUBLE,
    build_receipt, feed_and_cut, wrap_text, separator, format_kv,
)

W = settings.PAPER_WIDTH_CHARS


def _header(title: str) -> bytes:
    """Centered bold double-height header with separator."""
    return build_receipt(
        ALIGN_CENTER, SIZE_DOUBLE_H, BOLD_ON,
        title, LF,
        BOLD_OFF, SIZE_NORMAL, ALIGN_LEFT,
        separator("=", W), LF,
    )


def _footer(extra: str = "", submitted_by: str = "") -> bytes:
    """Standard receipt footer with timestamp, node callsign, and source IP."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    parts = [
        separator("-", W), LF,
        ALIGN_CENTER,
    ]
    if submitted_by:
        parts.extend([f"From: {submitted_by}", LF])
    if extra:
        parts.extend([extra, LF])
    parts.extend([
        f"Printed {ts}", LF,
        f"Thermal Printer Terminal v{settings.APP_VERSION}", LF,
        ALIGN_LEFT,
    ])
    return build_receipt(*parts)


# ---------------------------------------------------------------------------
# Message receipt
# ---------------------------------------------------------------------------
def render_message_receipt(data: dict, submitted_by: str = "") -> bytes:
    callsign = data.get("callsign", "UNKNOWN")
    body = data.get("body", "")
    category = data.get("category", "general").upper()
    footer_text = data.get("footer", "")

    parts = [
        INIT,
        _header("MESH MESSAGE"),
        format_kv("FROM", callsign, W), LF,
        format_kv("DATE", datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), W), LF,
        format_kv("CAT", category, W), LF,
        separator("-", W), LF,
    ]

    for line in wrap_text(body, W):
        parts.extend([line, LF])

    parts.append(_footer(footer_text, submitted_by))
    parts.append(feed_and_cut())
    return build_receipt(*parts)


# ---------------------------------------------------------------------------
# Status ticket
# ---------------------------------------------------------------------------
def render_status_ticket(data: dict, submitted_by: str = "") -> bytes:
    parts = [
        INIT,
        _header("MESH STATUS TICKET"),
        format_kv("NODE", data.get("node_name", settings.NODE_CALLSIGN), W), LF,
        format_kv("CALL", data.get("callsign", settings.NODE_CALLSIGN), W), LF,
        format_kv("HOST", data.get("hostname", "unknown"), W), LF,
        format_kv("IP", data.get("ip_address", "unknown"), W), LF,
        separator("-", W), LF,
        format_kv("PRINTER", f"{settings.PRINTER_HOST}:{settings.PRINTER_PORT}", W), LF,
        format_kv("STATUS", data.get("printer_status", "unknown"), W), LF,
        format_kv("QUEUE", str(data.get("queue_depth", 0)), W), LF,
        separator("-", W), LF,
        format_kv("VERSION", settings.APP_VERSION, W), LF,
        format_kv("UPTIME", data.get("uptime", "unknown"), W), LF,
    ]

    # Optional extra fields for future AREDN integration
    if data.get("extra_fields"):
        parts.extend([separator("-", W), LF])
        for k, v in data["extra_fields"].items():
            parts.extend([format_kv(k.upper(), str(v), W), LF])

    parts.append(_footer(submitted_by=submitted_by))
    parts.append(feed_and_cut())
    return build_receipt(*parts)


# ---------------------------------------------------------------------------
# QSO / Contact slip
# ---------------------------------------------------------------------------
def render_qso_receipt(data: dict, submitted_by: str = "") -> bytes:
    parts = [
        INIT,
        _header("QSO / CONTACT LOG"),
        format_kv("CALL", data.get("callsign", ""), W), LF,
        format_kv("DATE", data.get("date", ""), W), LF,
        format_kv("TIME", data.get("time_utc", ""), W), LF,
        format_kv("FREQ", data.get("frequency", ""), W), LF,
        format_kv("MODE", data.get("mode", ""), W), LF,
        format_kv("WRKD", data.get("station_worked", ""), W), LF,
        separator("-", W), LF,
        format_kv("RST TX", data.get("signal_sent", ""), W), LF,
        format_kv("RST RX", data.get("signal_received", ""), W), LF,
    ]

    notes = data.get("notes", "")
    if notes:
        parts.extend([
            separator("-", W), LF,
            BOLD_ON, "NOTES:", BOLD_OFF, LF,
        ])
        for line in wrap_text(notes, W):
            parts.extend([line, LF])

    parts.append(_footer(submitted_by=submitted_by))
    parts.append(feed_and_cut())
    return build_receipt(*parts)


# ---------------------------------------------------------------------------
# EmComm templates
# ---------------------------------------------------------------------------
def render_emcomm_receipt(template_type: str, fields: dict, submitted_by: str = "") -> bytes:
    renderers = {
        "ics213": _render_ics213,
        "dyfi": _render_dyfi,
        "sitrep": _render_sitrep,
        "resource_request": _render_resource_request,
    }
    renderer = renderers.get(template_type)
    if renderer is None:
        return _render_generic_emcomm(template_type, fields, submitted_by)
    return renderer(fields, submitted_by)


def _render_ics213(f: dict, submitted_by: str = "") -> bytes:
    parts = [
        INIT,
        _header("ICS-213 GENERAL MESSAGE"),
    ]
    if f.get("incident_name"):
        parts.extend([format_kv("INCIDENT", f["incident_name"], W), LF])
    if f.get("msg_id"):
        parts.extend([format_kv("MSG ID", f["msg_id"], W), LF])
    parts.extend([
        format_kv("TO", f.get("to_field", ""), W), LF,
        format_kv("FROM", f.get("from_field", ""), W), LF,
        format_kv("SUBJECT", f.get("subject", ""), W), LF,
        format_kv("DATE", f.get("date", ""), W), LF,
        format_kv("TIME", f.get("time", ""), W), LF,
    ])
    if f.get("precedence"):
        parts.extend([format_kv("PREC", f["precedence"], W), LF])
    parts.extend([
        separator("-", W), LF,
        BOLD_ON, "MESSAGE:", BOLD_OFF, LF,
    ])
    for line in wrap_text(f.get("body", ""), W):
        parts.extend([line, LF])
    if f.get("approved_by"):
        parts.extend([separator("-", W), LF, format_kv("APPROVED", f["approved_by"], W), LF])
    if f.get("reply"):
        parts.extend([
            separator("-", W), LF,
            BOLD_ON, "REPLY:", BOLD_OFF, LF,
        ])
        for line in wrap_text(f["reply"], W):
            parts.extend([line, LF])

    parts.append(_footer(submitted_by=submitted_by))
    parts.append(feed_and_cut())
    return build_receipt(*parts)


def _render_dyfi(f: dict, submitted_by: str = "") -> bytes:
    parts = [
        INIT,
        _header("DYFI / SHAKEOUT REPORT"),
        format_kv("LOCATION", f.get("location", ""), W), LF,
        format_kv("DATE", f.get("date", ""), W), LF,
        format_kv("TIME", f.get("time", ""), W), LF,
        format_kv("INTENSITY", f.get("intensity", ""), W), LF,
    ]
    if f.get("duration"):
        parts.extend([format_kv("DURATION", f"{f['duration']}s", W), LF])
    parts.extend([
        separator("-", W), LF,
        BOLD_ON, "DESCRIPTION:", BOLD_OFF, LF,
    ])
    for line in wrap_text(f.get("description", ""), W):
        parts.extend([line, LF])
    parts.extend([
        separator("-", W), LF,
        format_kv("DAMAGE", f.get("damage", "No"), W), LF,
        format_kv("INJURIES", f.get("injuries", "No"), W), LF,
        format_kv("REPORTER", f.get("reporter", ""), W), LF,
    ])

    parts.append(_footer(submitted_by=submitted_by))
    parts.append(feed_and_cut())
    return build_receipt(*parts)


def _render_sitrep(f: dict, submitted_by: str = "") -> bytes:
    parts = [
        INIT,
        _header("SITUATION REPORT"),
        format_kv("STATION", f.get("reporting_station", ""), W), LF,
        format_kv("DTG", f.get("dtg", ""), W), LF,
    ]
    if f.get("period_from") or f.get("period_to"):
        parts.extend([format_kv("PERIOD", f"{f.get('period_from', '')} - {f.get('period_to', '')}", W), LF])
    parts.extend([
        separator("-", W), LF,
        BOLD_ON, "SITUATION:", BOLD_OFF, LF,
    ])
    for line in wrap_text(f.get("situation_summary", ""), W):
        parts.extend([line, LF])
    if f.get("resources_needed"):
        parts.extend([
            separator("-", W), LF,
            BOLD_ON, "RESOURCES NEEDED:", BOLD_OFF, LF,
        ])
        for line in wrap_text(f["resources_needed"], W):
            parts.extend([line, LF])
    if f.get("casualties"):
        parts.extend([format_kv("CASUALTIES", f["casualties"], W), LF])
    if f.get("infrastructure"):
        parts.extend([
            separator("-", W), LF,
            BOLD_ON, "INFRASTRUCTURE:", BOLD_OFF, LF,
        ])
        for line in wrap_text(f["infrastructure"], W):
            parts.extend([line, LF])
    if f.get("next_report"):
        parts.extend([format_kv("NEXT RPT", f["next_report"], W), LF])
    parts.extend([format_kv("REPORTER", f.get("reporter", ""), W), LF])

    parts.append(_footer(submitted_by=submitted_by))
    parts.append(feed_and_cut())
    return build_receipt(*parts)


def _render_resource_request(f: dict, submitted_by: str = "") -> bytes:
    parts = [
        INIT,
        _header("RESOURCE REQUEST"),
        format_kv("FROM", f.get("requesting_station", ""), W), LF,
        format_kv("DATE", f.get("date", ""), W), LF,
        format_kv("TIME", f.get("time", ""), W), LF,
        separator("-", W), LF,
        format_kv("RESOURCE", f.get("resource_type", ""), W), LF,
        format_kv("QTY", f.get("quantity", ""), W), LF,
        BOLD_ON, format_kv("PRIORITY", f.get("priority", "Routine"), W), BOLD_OFF, LF,
        separator("-", W), LF,
        format_kv("DELIVER TO", f.get("delivery_location", ""), W), LF,
        format_kv("POC", f.get("poc_name", ""), W), LF,
    ]
    if f.get("poc_contact"):
        parts.extend([format_kv("CONTACT", f["poc_contact"], W), LF])
    parts.extend([
        separator("-", W), LF,
        BOLD_ON, "JUSTIFICATION:", BOLD_OFF, LF,
    ])
    for line in wrap_text(f.get("justification", ""), W):
        parts.extend([line, LF])

    parts.append(_footer(submitted_by=submitted_by))
    parts.append(feed_and_cut())
    return build_receipt(*parts)


def _render_generic_emcomm(template_type: str, fields: dict, submitted_by: str = "") -> bytes:
    """Fallback renderer for unknown template types."""
    parts = [
        INIT,
        _header(template_type.upper().replace("_", " ")),
    ]
    for key, value in fields.items():
        if isinstance(value, str) and len(value) > 60:
            parts.extend([
                BOLD_ON, f"{key.upper()}:", BOLD_OFF, LF,
            ])
            for line in wrap_text(value, W):
                parts.extend([line, LF])
        else:
            parts.extend([format_kv(key.upper(), str(value), W), LF])

    parts.append(_footer(submitted_by=submitted_by))
    parts.append(feed_and_cut())
    return build_receipt(*parts)


# ---------------------------------------------------------------------------
# Test receipt
# ---------------------------------------------------------------------------
def render_test_receipt() -> bytes:
    """Simple test receipt for printer verification."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    parts = [
        INIT,
        _header("PRINTER TEST"),
        ALIGN_CENTER,
        "*** TEST PRINT ***", LF,
        LF,
        f"Timestamp: {ts}", LF,
        f"Node: {settings.NODE_CALLSIGN}", LF,
        f"Printer: {settings.PRINTER_HOST}:{settings.PRINTER_PORT}", LF,
        f"Paper width: {W} chars", LF,
        LF,
        separator("=", W), LF,
        "All characters:", LF,
        "ABCDEFGHIJKLMNOPQRSTUVWXYZ", LF,
        "abcdefghijklmnopqrstuvwxyz", LF,
        "0123456789", LF,
        "!@#$%^&*()-_=+[]{}|;:',.<>?/", LF,
        separator("=", W), LF,
        BOLD_ON, "BOLD TEXT TEST", LF, BOLD_OFF,
        SIZE_DOUBLE_H, "DOUBLE HEIGHT", LF, SIZE_NORMAL,
        separator("=", W), LF,
        LF,
        "If you can read this, the printer", LF,
        "is working correctly.", LF,
        ALIGN_LEFT,
    ]
    parts.append(_footer())
    parts.append(feed_and_cut())
    return build_receipt(*parts)
