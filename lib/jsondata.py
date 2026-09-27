"""Bounded strict JSON for declarative application data."""
import json
import math

from readfile import read_document


def unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate JSON key: " + key)
        result[key] = value
    return result


def invalid_constant(value):
    raise ValueError("invalid JSON constant: " + value)


def check_depth(value, depth=0):
    if depth > 32:
        raise ValueError("JSON nesting exceeds 32 levels")
    if isinstance(value, float) and not math.isfinite(value):
        raise ValueError("JSON numbers must be finite")
    children = value.values() if isinstance(value, dict) else value if isinstance(value, list) else ()
    for child in children:
        check_depth(child, depth + 1)


def parse(text):
    try:
        value = json.loads(text, object_pairs_hook=unique_object, parse_constant=invalid_constant)
        check_depth(value)
        return value
    except RecursionError as error:
        raise ValueError("JSON nesting exceeds 32 levels") from error


def read(path, cap):
    result = read_document(path, cap)
    if result.get("error"):
        raise ValueError(result["error"])
    return parse(result["text"])
