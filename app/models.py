import re

from pydantic import BaseModel, field_validator

from app.text_utils import clean_for_form as _clean_string


class MessageJob(BaseModel):
    callsign: str
    body: str
    category: str = "general"

    @field_validator("callsign")
    @classmethod
    def validate_callsign(cls, v):
        v = v.strip().upper()
        if not re.match(r"^[A-Z0-9/]{1,15}$", v):
            raise ValueError("Callsign must be 1-15 alphanumeric characters")
        return v

    @field_validator("body")
    @classmethod
    def validate_body(cls, v):
        v = _clean_string(v)
        if len(v) > 1000:
            raise ValueError("Message body must be 1000 characters or less")
        if not v:
            raise ValueError("Message body is required")
        return v

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        valid = ("general", "emergency", "weather", "net-control", "info", "social")
        if v.lower() not in valid:
            raise ValueError(f"Category must be one of: {', '.join(valid)}")
        return v.lower()


class QSOJob(BaseModel):
    callsign: str
    date: str
    time_utc: str
    frequency: str
    mode: str = "SSB"
    station_worked: str = ""
    signal_sent: str = ""
    signal_received: str = ""
    notes: str = ""

    @field_validator("callsign")
    @classmethod
    def validate_callsign(cls, v):
        v = v.strip().upper()
        if not re.match(r"^[A-Z0-9/]{1,15}$", v):
            raise ValueError("Callsign must be 1-15 alphanumeric characters")
        return v

    @field_validator("mode")
    @classmethod
    def validate_mode(cls, v):
        valid = ("SSB", "FM", "AM", "CW", "FT8", "FT4", "DMR", "DSTAR", "C4FM", "RTTY", "PSK31", "JS8", "WINLINK", "OTHER")
        v = v.strip().upper()
        if v not in valid:
            raise ValueError(f"Mode must be one of: {', '.join(valid)}")
        return v

    @field_validator("notes")
    @classmethod
    def validate_notes(cls, v):
        return _clean_string(v)[:500] if v else ""

    @field_validator("station_worked")
    @classmethod
    def validate_station_worked(cls, v):
        return v.strip().upper()[:15] if v else ""


class EmCommFields(BaseModel):
    """Base EmComm fields — specific templates extend via their field dicts."""
    template_type: str
    fields: dict

    @field_validator("template_type")
    @classmethod
    def validate_template_type(cls, v):
        valid = ("ics213", "dyfi", "sitrep", "resource_request")
        if v.lower() not in valid:
            raise ValueError(f"Template type must be one of: {', '.join(valid)}")
        return v.lower()

    @field_validator("fields")
    @classmethod
    def validate_fields(cls, v):
        # Sanitize all string values in the fields dict
        cleaned = {}
        for key, val in v.items():
            if isinstance(val, str):
                cleaned[key] = _clean_string(val)[:2000]
            else:
                cleaned[key] = val
        return cleaned


# EmComm template field definitions for form rendering
EMCOMM_TEMPLATES = {
    "ics213": {
        "name": "ICS-213 General Message",
        "description": "Standard ICS general message form for incident communications",
        "fields": [
            {"name": "incident_name", "label": "Incident Name", "type": "text", "required": False},
            {"name": "msg_id", "label": "Message ID", "type": "text", "required": False},
            {"name": "to_field", "label": "To (Name/Position)", "type": "text", "required": True},
            {"name": "from_field", "label": "From (Name/Position)", "type": "text", "required": True},
            {"name": "subject", "label": "Subject", "type": "text", "required": True},
            {"name": "date", "label": "Date", "type": "text", "required": True},
            {"name": "time", "label": "Time (UTC)", "type": "text", "required": True},
            {"name": "precedence", "label": "Precedence", "type": "select", "options": ["Routine", "Priority", "Immediate", "Flash"], "required": False},
            {"name": "body", "label": "Message Body", "type": "textarea", "required": True},
            {"name": "approved_by", "label": "Approved By", "type": "text", "required": False},
            {"name": "reply", "label": "Reply / Comments", "type": "textarea", "required": False},
        ],
    },
    "dyfi": {
        "name": "DYFI / ShakeOut Report",
        "description": "Did You Feel It? earthquake quick report for situational awareness",
        "fields": [
            {"name": "location", "label": "Location / Grid", "type": "text", "required": True},
            {"name": "date", "label": "Date", "type": "text", "required": True},
            {"name": "time", "label": "Time (UTC/Local)", "type": "text", "required": True},
            {"name": "intensity", "label": "Intensity (1-10 Mercalli)", "type": "text", "required": True},
            {"name": "duration", "label": "Duration (seconds)", "type": "text", "required": False},
            {"name": "description", "label": "Description", "type": "textarea", "required": True},
            {"name": "damage", "label": "Structural Damage?", "type": "select", "options": ["No", "Minor", "Moderate", "Severe"], "required": False},
            {"name": "injuries", "label": "Injuries Reported?", "type": "select", "options": ["No", "Yes - Minor", "Yes - Serious", "Unknown"], "required": False},
            {"name": "reporter", "label": "Reporter Callsign/Name", "type": "text", "required": True},
        ],
    },
    "sitrep": {
        "name": "Situation Report",
        "description": "Quick situation report for incident awareness and coordination",
        "fields": [
            {"name": "reporting_station", "label": "Reporting Station", "type": "text", "required": True},
            {"name": "dtg", "label": "Date-Time Group", "type": "text", "required": True},
            {"name": "period_from", "label": "Period From", "type": "text", "required": False},
            {"name": "period_to", "label": "Period To", "type": "text", "required": False},
            {"name": "situation_summary", "label": "Situation Summary", "type": "textarea", "required": True},
            {"name": "resources_needed", "label": "Resources Needed", "type": "textarea", "required": False},
            {"name": "casualties", "label": "Casualties / Injuries", "type": "text", "required": False},
            {"name": "infrastructure", "label": "Infrastructure Status", "type": "textarea", "required": False},
            {"name": "next_report", "label": "Next Report Time", "type": "text", "required": False},
            {"name": "reporter", "label": "Reporter Callsign/Name", "type": "text", "required": True},
        ],
    },
    "resource_request": {
        "name": "Resource Request",
        "description": "Quick resource request form for field operations",
        "fields": [
            {"name": "requesting_station", "label": "Requesting Station", "type": "text", "required": True},
            {"name": "date", "label": "Date", "type": "text", "required": True},
            {"name": "time", "label": "Time (UTC)", "type": "text", "required": True},
            {"name": "resource_type", "label": "Resource Type", "type": "text", "required": True},
            {"name": "quantity", "label": "Quantity", "type": "text", "required": True},
            {"name": "priority", "label": "Priority", "type": "select", "options": ["Routine", "Urgent", "Immediate"], "required": True},
            {"name": "delivery_location", "label": "Delivery Location", "type": "text", "required": True},
            {"name": "poc_name", "label": "Point of Contact", "type": "text", "required": True},
            {"name": "poc_contact", "label": "POC Contact Info", "type": "text", "required": False},
            {"name": "justification", "label": "Justification", "type": "textarea", "required": True},
        ],
    },
}
