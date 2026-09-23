"""The modules one directory up that this package shares with the provider
converters: the Markdown parser, the HTML tree and tables, the colours.

The tree is run as scripts, never installed, so a package inside it finds
its neighbours by path — the same way every script finds lib/ — and this
is the one place the package says so. Both directions need them: the
writer to parse notes, the reader to check its own output.
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from parse import parse, walk_text  # noqa: E402
import htmltree  # noqa: E402
import htmltables  # noqa: E402
import textcolor  # noqa: E402

__all__ = ["parse", "walk_text", "htmltree", "htmltables", "textcolor"]
