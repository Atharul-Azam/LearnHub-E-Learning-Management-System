"""Small helpers shared by several apps."""
import re

from django.core.exceptions import ValidationError


def normalise_text(value):
    """Collapse runs of whitespace and strip. Used for titles and categories."""
    return re.sub(r"\s+", " ", (value or "")).strip()


class BusinessRuleError(Exception):
    """Raised by service functions when a documented business rule forbids an action."""


def require_text(value, label):
    value = normalise_text(value)
    if not value:
        raise ValidationError(f"{label} is required.")
    return value
