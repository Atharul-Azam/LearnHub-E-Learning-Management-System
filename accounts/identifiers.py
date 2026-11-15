"""Unique, human-readable Student / Teacher IDs.

Format: ``STU-000042`` for students, ``TCH-000007`` for teachers. The number is
the next free sequence number for that prefix. The column is UNIQUE and the
database CHECK constraint ties the prefix to the role, so a duplicate can never
be stored: if two requests race for the same number the loser hits the unique
constraint and simply retries with the next number.
"""
from django.db import IntegrityError, transaction

PREFIXES = {"student": "STU", "teacher": "TCH"}
WIDTH = 6
MAX_ATTEMPTS = 10


def prefix_for(role):
    return PREFIXES.get(role)


def _next_number(model, prefix):
    last = (
        model.objects.filter(public_id__startswith=f"{prefix}-")
        .order_by("-public_id")  # fixed width -> lexical order equals numeric order
        .values_list("public_id", flat=True)
        .first()
    )
    return int(last.split("-")[1]) + 1 if last else 1


def ensure_public_id(user):
    """Give ``user`` an ID if the role has one and none was assigned yet. Idempotent."""
    prefix = prefix_for(user.role)
    if prefix is None or user.public_id:
        return user.public_id
    model = type(user)
    for _ in range(MAX_ATTEMPTS):
        candidate = f"{prefix}-{_next_number(model, prefix):0{WIDTH}d}"
        try:
            with transaction.atomic():
                updated = model.objects.filter(pk=user.pk, public_id__isnull=True).update(public_id=candidate)
        except IntegrityError:  # another request took this number; try the next one
            continue
        if updated == 0:  # somebody else already assigned an ID to this user
            user.refresh_from_db(fields=["public_id"])
            return user.public_id
        user.public_id = candidate
        return candidate
    raise RuntimeError("Could not allocate a unique ID.")
