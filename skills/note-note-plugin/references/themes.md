# Themes

A theme is a JSON file of colors for the application's named color tokens.
It holds no code, no imports, no expressions and no inheritance. Fonts,
sizes, icons, provider logos and the colors authored inside notes are outside
it.

## Two ways to ship one

**Loose file** — one theme, no package. Save it as
`~/.config/notenote/themes/<id>.json`. The filename must be the theme's `id`,
and that ID must be a local ID (a lowercase letter, then lowercase letters,
digits, hyphens). Its saved identity is `user.themes/<id>`.

**In a package** — several themes, or themes next to commands or providers:

```json
{
  "schemaVersion": 1,
  "id": "io.github.someone.nord",
  "name": "Nord",
  "version": "1.0.0",
  "apiVersion": 1,
  "contributes": {
    "themes": [
      {"id": "nord", "path": "nord.json"},
      {"id": "nord-light", "path": "themes/nord-light.json"}
    ]
  }
}
```

The descriptor `id` must equal the `id` inside the file it points at. The
saved identity is `<package-id>/<id>`. A themes-only package loads without
being enabled.

## The file

```json
{
  "schemaVersion": 1,
  "id": "nord",
  "name": "Nord",
  "colors": {
    "surface.background": "#2E3440",
    "text.primary": "#D8DEE9",
    "accent.primary": "#88C0D0"
  }
}
```

Rules — any break rejects the file:

- Exactly the fields `schemaVersion` (integer `1`), `id`, `name` and
  `colors`; nothing else.
- `colors` keys are token names from the table below; unknown names are refused.
- A value is `"#RRGGBB"`, `"#AARRGGBB"`, `"system"` or `"transparent"`.
  **Alpha comes first, as in Qt**: `#99000000` is black at 60%. `#RRGGBBAA`
  is read as `#AARRGGBB`, which is wrong.
- Only tokens marked translucent below may be `transparent` or have an alpha
  other than `FF`.
- No duplicate keys; the file is at most 256 KiB.

## How colors are filled in

- Omit a token and it is derived, by a fixed recipe, from the tokens it
  depends on (the last column below) — using the theme's own values for those.
  So a theme that sets only the three roots — `surface.background`,
  `text.primary`, `accent.primary` — is already complete and coherent.
- Omit a root and it comes from the desktop, which can clash with the rest:
  a light desktop's text on a dark background is unreadable. **Always set all
  three roots.**
- `"system"` takes that token from the unmodified desktop palette, whatever
  the rest of the theme says.
- Set a derived token only to tune it. Worth tuning on most themes: the
  selection pair, `sidebar.background`, `editor.codeBackground`,
  `editor.link`, `status.error`. **Dark themes must set
  `editor.highlightBackground`/`editor.highlightForeground`**: their fixed
  defaults are a pale yellow with dark ink, meant for light pages.
- The app does not correct colors: the picker reports low contrast, and it is
  the author's job to keep each foreground readable on the background named
  in "Readable on".

## Tokens

Source of truth: `design/tokens.js` in the Note Note source. "Fixed" means a
built-in default that no other token feeds; for the three roots that is the
desktop's color.

| Token | Translucent | Readable on | Derived from |
|---|---|---|---|
| `surface.background` | no |  | fixed (desktop) |
| `text.primary` | no | `surface.background` | fixed (desktop) |
| `accent.primary` | no | `surface.background` | fixed (desktop) |
| `surface.raised` | no |  | `surface.background`, `text.primary` |
| `text.secondary` | yes | `surface.background` | `text.primary` |
| `text.disabled` | yes | `surface.background` | `text.primary` |
| `border.default` | yes |  | `text.primary` |
| `border.focus` | no |  | `surface.raised`, `text.primary` |
| `overlay.scrim` | yes |  | fixed |
| `selection.background` | yes |  | `accent.primary` |
| `selection.foreground` | no | `selection.background` | `accent.primary` |
| `input.background` | no |  | `surface.raised`, `text.primary` |
| `input.foreground` | no | `input.background` | `text.primary` |
| `input.border` | no |  | `surface.raised`, `text.primary` |
| `input.placeholder` | yes | `input.background` | `text.primary` |
| `button.background` | no |  | `surface.raised` |
| `button.foreground` | no | `button.background` | `text.primary` |
| `button.disabledForeground` | yes | `button.background` | `text.primary` |
| `popup.background` | no |  | `surface.raised` |
| `popup.foreground` | no | `popup.background` | `text.primary` |
| `popup.border` | no |  | `popup.background`, `text.primary` |
| `tooltip.background` | no |  | `surface.background` |
| `tooltip.foreground` | no | `tooltip.background` | `text.primary` |
| `sidebar.background` | no |  | `surface.background`, `text.primary` |
| `sidebar.foreground` | no | `sidebar.background` | `text.primary` |
| `tab.activeBackground` | yes |  | `selection.background` |
| `tab.activeForeground` | no | `tab.activeBackground` | `selection.foreground` |
| `tab.inactiveForeground` | yes | `surface.background` | `text.primary` |
| `titlebar.background` | no |  | `surface.background` |
| `toolbar.background` | no |  | `surface.raised` |
| `statusbar.background` | no |  | `surface.background` |
| `statusbar.foreground` | no | `statusbar.background` | `text.primary` |
| `editor.background` | no |  | `surface.background` |
| `editor.foreground` | no | `editor.background` | `text.primary` |
| `editor.selectionBackground` | yes |  | `accent.primary` |
| `editor.selectionForeground` | no | `editor.selectionBackground` | `editor.foreground` |
| `editor.link` | no | `editor.background` | `editor.foreground`, `accent.primary` |
| `editor.quoteForeground` | no | `editor.background` | `editor.background`, `editor.foreground` |
| `editor.quoteBorder` | yes |  | `accent.primary` |
| `editor.codeBackground` | no |  | `editor.background` |
| `editor.codeForeground` | no | `editor.codeBackground` | `editor.foreground` |
| `editor.inlineCodeBackground` | no |  | `editor.background` |
| `editor.highlightBackground` | no |  | fixed (`#F9E2AF`) |
| `editor.highlightForeground` | no | `editor.highlightBackground` | fixed (`#1E1E2E`) |
| `status.error` | no | `surface.background` | fixed |
| `palette.background` | no |  | `popup.background` |
| `palette.foreground` | no | `palette.background` | `popup.foreground` |
| `palette.selectionBackground` | yes |  | `selection.background` |
| `palette.selectionForeground` | no | `palette.selectionBackground` | `selection.foreground` |
| `control.base` | no |  | `input.background` |
| `control.text` | no |  | `input.foreground` |
| `control.alternateBase` | no |  | `surface.raised` |
| `control.highlight` | yes |  | `selection.background` |
| `control.highlightedText` | no |  | `selection.foreground` |
| `control.light` | no |  | `surface.background` |
| `control.midlight` | no |  | `surface.background` |
| `control.mid` | no |  | `surface.background` |
| `control.dark` | no |  | `surface.background` |
| `control.shadow` | no |  | fixed |
| `control.placeholderText` | yes |  | `text.primary` |
| `control.disabledText` | yes |  | `text.primary` |
| `control.link` | no |  | `editor.link` |
| `control.linkVisited` | no |  | `control.link` |

Groups, to know what a token paints: `surface`/`text`/`border` are the
window; `selection`, `input`, `button`, `popup`, `tooltip` the shared
controls; `sidebar`, `tab`, `titlebar`, `toolbar`, `statusbar` the chrome;
`editor.*` the note page (`highlight` is `==marked==` text, `quote` the
blockquote bar and ink, `code`/`inlineCode` code blocks and spans);
`palette.*` the command palette; `control.*` Qt's own control roles.

## A complete dark theme

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
    "selection.foreground": "#FFFFFF",
    "tab.activeBackground": "#384866",
    "tab.activeForeground": "#FFFFFF",
    "editor.highlightBackground": "#635526",
    "editor.highlightForeground": "#FFF2BB"
  }
}
```

## Trying it

A new theme file needs a restart to be discovered; after that, editing its
colors only needs the picker reopened. Ctrl+Shift+P → Color Theme: arrow keys
preview, Enter saves, Escape restores. A file that failed validation is named
in the picker's message with the reason. In Omarchy, custom themes need the
app's native helper built (`sh cpp/build.sh` in the plugin folder, then
restart the shell); without it the app stays on System colors.
