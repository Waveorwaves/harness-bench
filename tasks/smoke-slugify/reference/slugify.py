import re
import unicodedata


def slugify(text):
    """Turn a title into a URL slug."""
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode().lower()
    plain = re.sub(r"[\s_-]+", "-", plain)
    plain = re.sub(r"[^a-z0-9-]", "", plain)
    return re.sub(r"-+", "-", plain).strip("-") or "untitled"
