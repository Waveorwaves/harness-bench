import re


def slugify(text):
    """Turn a title into a URL slug."""
    return re.sub(r"\s+", "-", text.strip().lower())
