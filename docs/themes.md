# Color themes

Open **Ctrl+Shift+P → Color Theme**. Arrow keys preview a theme;
Enter or a row click saves it. Escape or clicking outside restores the saved
selection. The Settings page must have no unsaved edits before selecting a theme.

Three built-in palettes offer a Typora-inspired writing environment:

| Theme | Appearance | Inspiration |
| --- | --- | --- |
| **Paper** | White page, pale gray chrome, blue links and selections | [Typora GitHub](https://theme.typora.io/theme/Github/) |
| **Newsprint** | Warm ivory, brown ink, soft beige selections | [Typora Newsprint](https://theme.typora.io/theme/Newsprint/) |
| **Nightfall** | Charcoal, soft gray text, muted blue accents | [Typora Night](https://theme.typora.io/theme/Night/) |

These are original color palettes for note-note's theme tokens. They cover the
editor, sidebar, controls, and command palette; fonts and layout remain the
application’s own. Their saved IDs are `org.note-note.appearance/paper`,
`org.note-note.appearance/newsprint`, and `org.note-note.appearance/nightfall`.
Restart after updating to discover these additions, then preview them in the picker.

**System** is the default and follows live desktop changes. The theme picker
does not write notes or replace their document. Authored text colors retain
precedence over theme ink. The Markdown dialect treats non-code character
backgrounds as semantic `==highlight==`; arbitrary authored backgrounds are
not a separate feature of that dialect.

The standalone application includes the native display helper. In Omarchy,
build it with `sh cpp/build.sh` and restart the shell to enable commands and
custom themes. Without it, the existing script editor remains available with
System colors. A saved custom selection is retained on disk but falls back to
System for that session. This explicit limit avoids rewriting a document to
recolor inline code and highlights.

## Installing a theme

Copy a JSON file into `$XDG_CONFIG_HOME/notenote/themes/`, or
`~/.config/notenote/themes/` when XDG_CONFIG_HOME is unset, and restart.
The filename must match the local ID: `midnight.json` for `"id": "midnight"`.
Its saved ID is `user.themes/midnight`. Packages can also contribute themes;
see [plugins](plugins.md) and [the color example](../examples/plugins/colors).
Flatpak uses its app-scoped configuration directory inside its sandbox.

```json
{
  "schemaVersion": 1,
  "id": "midnight",
  "name": "Midnight",
  "colors": {
    "surface.background": "#181A20",
    "text.primary": "#E6EAF0",
    "accent.primary": "#89B4FA",
    "selection.background": "#384866",
    "selection.foreground": "#FFFFFF"
  }
}
```

A theme file holds `schemaVersion`, `id`, `name` and `colors`, and nothing
else. Values are `system`, `transparent`, `#RRGGBB`, or **`#AARRGGBB`
(alpha first, following Qt)**. Only overlay roles allow transparency. Unknown
fields and keys, duplicate JSON keys, invalid values, future schemas, and
mismatched IDs are rejected. Themes contain no code, imports, expressions, or
inheritance.

An explicit `system` always reads that role from the unmodified desktop
baseline, including when adjacent tokens are custom. Omitted root roles use
that baseline; omitted derived roles follow the effective inputs. A light
desktop's system text on a custom dark background can be unreadable. The picker
reports low contrast without silently changing explicit colors.

The complete token inventory, ordering, opacity rules, paired surfaces, and
recipe names live in [tokens.js](../design/tokens.js), the only list of them:
the application reads it directly, and the theme validator is sent the names
with each request. The small [resolver](../design/resolve.js) implements the
recipes. Key groups cover surfaces/text, selection, inputs/buttons,
popups/tooltips, sidebar/tabs/chrome, editor decorations, the error status,
command palette, and Qt control roles. The
[System file](../plugins/org.note-note.appearance/themes/system.json) lists
every token. Fonts, dimensions, icons, provider identity hues and authored note
content are outside this schema.

The system's colours are resolved before anything is drawn, so the application
never paints a colour of its own in place of a token. A custom theme is read
from its file; the standalone window opens once that is done.

How a control answers the pointer (its hover, pressed and selected fills) is
made from the ink of the control itself, so a button in another colour keeps
its own. A theme reaches those through the colours it gives the ink; they are
not tokens.

The editor uses Qt's native caret without a separate caret color setting.

Only `appearance.theme` is saved to config.json. Missing/invalid themes fall
back to System without replacing that stored ID. Theme files are reread when
the picker opens; navigation uses that validated session snapshot. Package
additions and executable updates require restart. A failed save restores the
committed appearance; closing during an accepted write waits for its result.

Configuration writes share a lock and compare content revisions. A change from
another running host or editor rejects stale saves. Restart to reconcile the
runtime configuration; there is no background provider-config reload. External
editors that ignore advisory locks cannot participate in a perfect transaction.
