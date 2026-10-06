`slugify(text)` in `slugify.py` turns a title into a URL slug, but it only handles the simplest input. Fix it so that:

- the result is lowercase and contains only `a`–`z`, `0`–`9` and single hyphens;
- runs of whitespace, hyphens and underscores become one hyphen;
- all other punctuation is removed;
- accented Latin letters become their plain ASCII letter (`é` becomes `e`);
- there is no leading or trailing hyphen;
- if nothing is left, the result is `untitled`.

Keep the function name and signature. Use only the Python standard library.
