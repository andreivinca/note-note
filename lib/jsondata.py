"""Bounded strict JSON for declarative application data."""
import json
import math
import sys

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


def answer(handle, cap):
    """One JSON object from stdin in, one JSON object on stdout out.

    A helper script's whole conversation with the application. What goes
    wrong is part of the answer, as `error`, so the caller never has to read
    a traceback.
    """
    try:
        raw = sys.stdin.buffer.read(cap + 1)
        if len(raw) > cap:
            raise ValueError("request exceeds the byte limit")
        request = parse(raw)
        if not isinstance(request, dict):
            raise ValueError("request must be a JSON object")
        result = handle(request)
    except (OSError, ValueError, KeyError, TypeError) as error:
        result = {"error": str(error)}
    json.dump(result, sys.stdout)
