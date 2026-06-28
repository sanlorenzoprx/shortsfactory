from __future__ import annotations

import html


def escape_html(value: object) -> str:
    """Escape all preview content, including quotes, for static local HTML."""
    return html.escape(str(value), quote=True)
