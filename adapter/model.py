from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from uuid import UUID

UTC = timezone.utc
PROMPTS = {"person_on_railway_tracks": (
    "Is a person visible on the railway tracks in this clip? Start your answer "
    "with RAIL_INTRUSION if a person is visibly on the tracks, RAIL_CLEAR if no "
    "person is on the tracks, or RAIL_UNCERTAIN if the view is unclear. Then give "
    "one sentence of visible evidence, location and movement. Distinguish the "
    "tracks from the platform. Do not infer identity or intent."
), "school_gate_break_in_night": (
    "What visible activity occurs at the school gate in this clip? Start your "
    "answer with GATE_INTERACTION if a person visibly manipulates the gate or "
    "padlock, GATE_CLEAR if no such interaction occurs, or GATE_UNCERTAIN if "
    "darkness or occlusion prevents a conclusion. Then describe the visible "
    "interaction in one sentence. Do not infer identity, intent or criminality."
), "blocked_sidewalk": (
    "Is the sidewalk obstructed by a fallen e-scooter or overturned bin in this "
    "clip? Start your answer with SIDEWALK_BLOCKED if such an object visibly "
    "obstructs the walkway, SIDEWALK_CLEAR if the path is clear, or "
    "SIDEWALK_UNCERTAIN if the view is unclear. Then give one sentence describing "
    "the object, its position and the remaining walking space."
)}
PROMPT = PROMPTS["person_on_railway_tracks"]


def guid(value):
    try:
        parsed = UUID(str(value))
        if parsed.int == 0:
            raise ValueError
        return str(parsed)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Expected a nonzero UUID") from None


def utc(value):
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if dt.tzinfo is None or dt.utcoffset() is None:
            raise ValueError
        return dt.astimezone(UTC)
    except (ValueError, TypeError, AttributeError):
        raise ValueError("Timestamp must be ISO 8601 with an explicit timezone") from None


def iso(dt):
    return dt.astimezone(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


@dataclass(frozen=True)
class Trigger:
    event_id: str
    camera_id: str
    timestamp_utc: str
    origin: str
    label: str = "person_on_railway_tracks"
    before_seconds: int = 20
    after_seconds: int = 10
    prompt: str = PROMPT

    def __post_init__(self):
        object.__setattr__(self, "event_id", guid(self.event_id))
        object.__setattr__(self, "camera_id", guid(self.camera_id))
        object.__setattr__(self, "timestamp_utc", iso(utc(self.timestamp_utc)))
        if self.origin not in {"manual", "synthetic", "xprotect_event"}:
            raise ValueError("Unknown trigger origin")
        if self.label not in PROMPTS:
            raise ValueError("Unknown demo scenario")
        if any(type(n) is not int or not 0 <= n <= 60
               for n in (self.before_seconds, self.after_seconds)):
            raise ValueError("Clip offsets must be whole seconds from 0 to 60")
        if not 1 <= self.before_seconds + self.after_seconds <= 60:
            raise ValueError("Clip duration must be 1 to 60 seconds")
        if self.prompt != PROMPTS[self.label]:
            raise ValueError("Prompt must match the reviewed gateway prompt")

    def validate_recording_window(self, now):
        start, end = self.window()
        if end > now - timedelta(seconds=2):
            raise ValueError("Clip is not fully recorded yet; wait for its end plus 2 seconds")
        if start < now - timedelta(hours=23):
            raise ValueError("Clip exceeds the conservative 23-hour recording window")

    def window(self):
        t = utc(self.timestamp_utc)
        return (t - timedelta(seconds=self.before_seconds),
                t + timedelta(seconds=self.after_seconds))

    def validate_live_request(self, now):
        # On the installed p042 server UDEs receive server time, regardless of
        # the REST body's time. Never silently analyze a different historical clip.
        age = (now - utc(self.timestamp_utc)).total_seconds()
        if not -2 <= age <= 30:
            raise ValueError("Native user events require a fresh trigger within 30 seconds; historical clip replay is unsupported")

    def payload(self, event_type_id):
        # User-defined events do not carry analytics data. The reviewed native
        # gateway webhook owns the prompt and clip offsets, not this REST body.
        return {"type": guid(event_type_id), "datatype": "none",
                "tag": f"icit-hackathon:{self.origin}:{self.event_id}"}

    def record(self):
        return asdict(self)
