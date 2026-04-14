"""Shared display helpers for job tables on the home and admin pages."""

import json
from datetime import datetime, timezone

from app.models import EMCOMM_TEMPLATES


def friendly_time(iso_str: str) -> str:
    """Convert an ISO timestamp to a human-friendly relative string."""
    try:
        dt = datetime.fromisoformat(iso_str)
        now = datetime.now(timezone.utc)
        secs = int((now - dt).total_seconds())
        if secs < 60:
            return 'just now'
        if secs < 3600:
            return f'{secs // 60}m ago'
        if secs < 86400:
            return f'{secs // 3600}h ago'
        if secs < 604800:
            return f'{secs // 86400}d ago'
        return dt.strftime('%b %d')
    except Exception:
        return iso_str[:16] if iso_str else ''


def extract_callsign(job) -> str:
    """Pull the operator callsign from a job's content JSON."""
    try:
        content = json.loads(job['content'])
        if 'callsign' in content:
            return content['callsign']
        if 'fields' in content:
            fields = content['fields']
            for key in ('reporter', 'reporting_station',
                        'requesting_station', 'from_field'):
                if fields.get(key):
                    return fields[key]
    except Exception:
        pass
    return ''


def build_from(job) -> str:
    """Build a 'From' display string combining callsign and source IP."""
    callsign = extract_callsign(job)
    source = job['submitted_by'] or ''
    if callsign and source:
        return f'{callsign} \u2014 {source}'
    return callsign or source or '-'


def build_details(job, show_full: bool = False) -> list[tuple[str, str]]:
    """Build key-value detail pairs for a job's expanded row.

    When show_full is True (admin view), message bodies, notes, and
    all emcomm textarea fields are included.  The public traffic log
    passes show_full=False to hide long-form content.
    """
    details = []
    jtype = job['job_type']
    try:
        content = json.loads(job['content'])
    except Exception:
        content = {}

    details.append(('Submitted', (job['submitted_at'] or '')[:19].replace('T', ' ') + ' UTC'))

    if show_full:
        details.append(('Source', job['submitted_by'] or '-'))

    if jtype == 'message':
        if show_full:
            details.append(('Callsign', content.get('callsign', '')))
        details.append(('Category', (content.get('category') or 'general').capitalize()))
        if show_full and content.get('body'):
            details.append(('Message', content['body']))

    elif jtype == 'qso':
        if content.get('station_worked'):
            details.append(('Station Worked', content['station_worked']))
        details.append(('Date/Time', f'{content.get("date", "")} {content.get("time_utc", "")} UTC'))
        details.append(('Frequency', content.get('frequency', '')))
        details.append(('Mode', content.get('mode', '')))
        if content.get('signal_sent') or content.get('signal_received'):
            details.append(('RST', f'TX {content.get("signal_sent", "-")} / RX {content.get("signal_received", "-")}'))
        if show_full and content.get('notes'):
            details.append(('Notes', content['notes']))

    elif jtype == 'emcomm':
        ttype = content.get('template_type', '')
        tmpl = EMCOMM_TEMPLATES.get(ttype, {})
        details.append(('Form', tmpl.get('name', ttype)))
        fields = content.get('fields', {})
        for fd in tmpl.get('fields', []):
            val = fields.get(fd['name'], '')
            if not val:
                continue
            if fd['type'] == 'textarea' and not show_full:
                continue
            details.append((fd['label'], val))

    if job['status'] == 'failed' and job.get('error_message'):
        details.append(('Error', job['error_message']))
    if job['retry_count']:
        details.append(('Retries', str(job['retry_count'])))

    return details
