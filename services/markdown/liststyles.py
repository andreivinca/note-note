"""List marker names shared by semantic HTML and the document adapters."""

BULLETS = ("disc", "circle", "square")
NUMBERS = ("decimal", "lower-alpha", "upper-alpha", "upper-roman", "lower-roman")
HTML_TYPES = {"1": "decimal", "a": "lower-alpha", "A": "upper-alpha",
              "i": "lower-roman", "I": "upper-roman",
              "disc": "disc", "circle": "circle", "square": "square"}


def default(ordered):
    return "decimal" if ordered else "disc"


def from_attributes(attrs, fallback):
    style = HTML_TYPES.get(attrs.get("type"), fallback)
    for declaration in attrs.get("style", "").split(";"):
        name, separator, value = declaration.partition(":")
        if separator and name.strip().lower() == "list-style-type":
            style = value.strip().lower()
    return style if style in BULLETS + NUMBERS else fallback


def attributes(style, indent=0):
    result = ' style="list-style-type:%s"' % style if style else ""
    if indent:
        result += ' data-list-indent="%d"' % indent
    return result
