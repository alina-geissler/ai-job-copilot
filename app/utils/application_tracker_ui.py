"""Define UI helper metadata for application tracker rendering.

Provide one central place for UI-specific tracker metadata such as translated
labels, display order, CSS classes, and the mapped date field per status.
"""

from __future__ import annotations

from app.core.enums import ApplicationStatus

TRACKER_STATUS_ORDER: tuple[ApplicationStatus, ...] = (
    ApplicationStatus.SAVED,
    ApplicationStatus.APPLIED,
    ApplicationStatus.INTERVIEW,
    ApplicationStatus.OFFER,
    ApplicationStatus.REJECTED,
    ApplicationStatus.WITHDRAWN,
)

TRACKER_STATUS_LABELS: dict[ApplicationStatus, str] = {
    ApplicationStatus.SAVED: "Offen",
    ApplicationStatus.APPLIED: "Beworben",
    ApplicationStatus.INTERVIEW: "Interview",
    ApplicationStatus.OFFER: "Angebot",
    ApplicationStatus.REJECTED: "Absage",
    ApplicationStatus.WITHDRAWN: "Zurückgezogen",
}

TRACKER_STATUS_CLASSES: dict[ApplicationStatus, str] = {
    ApplicationStatus.SAVED: "tracker-status--saved",
    ApplicationStatus.APPLIED: "tracker-status--applied",
    ApplicationStatus.INTERVIEW: "tracker-status--interview",
    ApplicationStatus.OFFER: "tracker-status--offer",
    ApplicationStatus.REJECTED: "tracker-status--rejected",
    ApplicationStatus.WITHDRAWN: "tracker-status--withdrawn",
}

TRACKER_STATUS_DATE_FIELDS: dict[ApplicationStatus, str | None] = {
    ApplicationStatus.SAVED: "created_at",
    ApplicationStatus.APPLIED: "applied_at",
    ApplicationStatus.INTERVIEW: "interview_at",
    ApplicationStatus.OFFER: "offer_at",
    ApplicationStatus.REJECTED: "rejected_at",
    ApplicationStatus.WITHDRAWN: "withdrawn_at",
}