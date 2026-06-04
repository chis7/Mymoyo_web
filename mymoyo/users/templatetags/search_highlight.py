import re

from django import template
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe

register = template.Library()


@register.filter(needs_autoescape=True)
def highlight_match(value, search_term, autoescape=True):
    if value is None:
        return ''

    text = str(value)
    term = str(search_term or '').strip()
    escaper = conditional_escape if autoescape else lambda item: item

    if not term:
        return escaper(text)

    pattern = re.compile(f"({re.escape(term)})", re.IGNORECASE)
    parts = pattern.split(text)
    highlighted = ''.join(
        f'<mark class="search-highlight">{escaper(part)}</mark>'
        if pattern.fullmatch(part)
        else str(escaper(part))
        for part in parts
    )
    return mark_safe(highlighted)
