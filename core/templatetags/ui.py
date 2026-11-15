"""Small presentation helpers: a cover theme + icon for each course category.

Only constant, hard-coded SVG fragments are marked safe here; no user data ever reaches ``mark_safe``.
"""
from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# key -> (inner SVG markup on a 24x24 stroke icon, colour theme class suffix)
_ICONS = {
    "code": '<polyline points="16 18 22 12 16 6"/><polyline points="8 6 2 12 8 18"/>',
    "web": '<circle cx="12" cy="12" r="10"/><path d="M2 12h20"/><path d="M12 2a15 15 0 0 1 0 20 15 15 0 0 1 0-20"/>',
    "data": '<path d="M3 3v18h18"/><path d="M7 15l4-4 3 3 5-6"/>',
    "database": '<ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.7 3.6 3 8 3s8-1.3 8-3V5"/><path d="M4 12c0 1.7 3.6 3 8 3s8-1.3 8-3"/>',
    "math": '<rect x="5" y="2" width="14" height="20" rx="2"/><path d="M8 6h8M8 11h2M14 11h2M8 15h2M14 15h2M8 19h2M14 19h2"/>',
    "business": '<rect x="3" y="7" width="18" height="13" rx="2"/><path d="M9 7V5a2 2 0 0 1 2-2h2a2 2 0 0 1 2 2v2"/><path d="M3 13h18"/>',
    "design": '<path d="M12 19l7-7 3 3-7 7-3-3z"/><path d="M18 13l-1.5-7.5L2 2l3.5 14.5L13 18l5-5z"/><circle cx="11" cy="11" r="2"/>',
    "language": '<path d="M2 4h6a4 4 0 0 1 4 4v12a3 3 0 0 0-3-3H2z"/><path d="M22 4h-6a4 4 0 0 0-4 4v12a3 3 0 0 1 3-3h7z"/>',
    "science": '<path d="M9 3h6"/><path d="M10 3v6l-5.5 9.5A2 2 0 0 0 6.2 21h11.6a2 2 0 0 0 1.7-2.5L14 9V3"/><path d="M7.5 15h9"/>',
    "general": '<path d="M22 10L12 5 2 10l10 5 10-5z"/><path d="M6 12v5c3 2 9 2 12 0v-5"/>',
}

# keyword (matched inside the lower-cased category) -> icon key; first match wins
_KEYWORDS = [
    ("database", "database"), ("sql", "database"),
    ("web", "web"), ("html", "web"), ("javascript", "web"),
    ("data", "data"), ("machine", "data"), ("analytic", "data"), ("statistic", "data"),
    ("program", "code"), ("python", "code"), ("code", "code"), ("algorithm", "code"), ("software", "code"), ("comput", "code"),
    ("math", "math"), ("calculus", "math"), ("algebra", "math"),
    ("business", "business"), ("market", "business"), ("entrepreneur", "business"), ("finance", "business"), ("econom", "business"),
    ("design", "design"), ("art", "design"), ("ux", "design"),
    ("language", "language"), ("english", "language"), ("writing", "language"), ("literature", "language"),
    ("science", "science"), ("physic", "science"), ("chem", "science"), ("bio", "science"),
]

_THEMES = {
    "code": "indigo", "web": "sky", "data": "emerald", "database": "amber", "math": "rose",
    "business": "slate", "design": "violet", "language": "orange", "science": "teal", "general": "indigo",
}


def category_key(category):
    text = (category or "").lower()
    for word, key in _KEYWORDS:
        if word in text:
            return key
    return "general"


@register.filter
def cover_theme(category):
    """CSS theme name (indigo, sky, ...) used as ``cover-<theme>``."""
    return _THEMES[category_key(category)]


@register.filter
def cover_icon(category):
    """Inner SVG markup of the category icon (constant strings only)."""
    return mark_safe(_ICONS[category_key(category)])  # noqa: S308 - constants, no user input
