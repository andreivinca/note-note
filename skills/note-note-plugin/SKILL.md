---
name: note-note-plugin
description: Write, fix or review a plugin for the Note Note notes app (the Omarchy shell plugin and the standalone/Flatpak Qt app) — color themes, command-palette commands with their keyboard shortcuts, editing-toolbar tools that act on the open note, and note providers that bring notes from a new backend. Use whenever someone asks for a Note Note theme, command, shortcut, toolbar tool or provider, writes or debugs a Note Note plugin.json, or works under ~/.config/notenote/plugins/ or ~/.config/notenote/themes/.
---

# Writing Note Note plugins

Note Note loads plugin **packages**: one folder holding a `plugin.json`
manifest and the files it names. A package contributes any mix of five kinds,
and nothing else — any other key under `contributes` rejects the whole manifest.

| Kind | What it adds | Code | Read |
|---|---|---|---|
| `themes` | A color palette, chosen with Ctrl+Shift+P → Color Theme | none, JSON only | [references/themes.md](references/themes.md) |
| `commands` | An entry in the command palette (Ctrl+Shift+P) | a QML handler, or none when it names a built-in workspace action | [references/commands.md](references/commands.md) |
| `keybindings` | Default shortcuts for the package's **own** commands | none | [references/commands.md](references/commands.md#keybindings) |
| `tools` | An editing-toolbar button or menu entry that acts on the open note, with an optional shortcut and input panel | a QML `Tool` | [references/tools.md](references/tools.md) |
| `providers` | A note backend: sidebar tabs whose notes it lists, loads, saves and deletes | a QML item, plus any scripts it runs | [references/providers.md](references/providers.md) |

Pick by what the user wants:

- **Only colors** → a theme. A single theme needs no package at all: a loose
  theme file in the themes folder is enough.
- **"Do X from the palette / on a shortcut"** → a command, with a keybinding if
  it deserves a default key. Check first that the command API can do X: it can
  show messages and pickers, run a workspace action, read the package's own
  files, and preview or save a theme — it cannot edit the open note.
- **"Insert or format something in the note"** → a tool: a toolbar button or
  menu entry, with a shortcut if it deserves one.
- **"Show my notes from Y"** → a provider.

Status-bar controls are built into the application; they are not a plugin
kind. Say so instead of inventing a contribution for them.

Read the reference for the kind you are writing before writing it. The rules
below apply to every package.

## Where packages live

| | Omarchy plugin, standalone app | Flatpak |
|---|---|---|
| Packages | `~/.config/notenote/plugins/<folder>/` | `~/.var/app/io.github.andreivinca.note-note/config/notenote/plugins/<folder>/` |
| Loose themes | `~/.config/notenote/themes/<id>.json` | `~/.var/app/io.github.andreivinca.note-note/config/notenote/themes/<id>.json` |
| Settings | `~/.config/notenote/config.json` | `~/.var/app/io.github.andreivinca.note-note/config/notenote/config.json` |

`$XDG_CONFIG_HOME` replaces `~/.config` when it is set. Name the folder after
the package ID. The folder and every file in it must be real files — the
loader refuses symlinks, so copy a package into place rather than linking it.

## plugin.json

```json
{
  "schemaVersion": 1,
  "id": "io.github.someone.nord",
  "name": "Nord",
  "version": "1.0.0",
  "apiVersion": 1,
  "contributes": {
    "themes": [{"id": "nord", "path": "nord.json"}],
    "commands": [{"id": "snippet", "title": "Show a Snippet", "category": "Nord", "handler": "Snippet.qml"}],
    "keybindings": [{"command": "snippet", "key": "Ctrl+Alt+S", "context": "notes"}],
    "tools": [{"id": "insertNordStamp", "path": "InsertStamp.qml"}],
    "providers": [{"id": "nord-notes", "path": "Provider.qml", "order": 500}]
  }
}
```

Use only the kinds the package actually supplies. The validator enforces:

- `schemaVersion` and `apiVersion` are the integer `1`.
- `id` is two or more dot-separated segments, each a lowercase letter followed
  by lowercase letters, digits or hyphens: `io.github.someone.nord`. Use a
  domain the author owns, or `io.github.<user>.<name>`. `org.note-note.*` and
  `user.themes` are reserved.
- `name` is a non-empty display string, at most 256 characters.
- `version` is `major.minor.patch` with no leading zeroes (`1.0.0`, not `1.00.0`).
- `contributes` is a non-empty object whose keys are among the five kinds,
  each a list of at most 128 objects.
- Every contribution `id` (and a keybinding's `command`) is a local ID —
  a lowercase letter, then lowercase letters, digits and hyphens — unique
  within its kind. The app qualifies it as `<package-id>/<local-id>`. A tool's
  `id` is the exception: an action ID like `insertStamp`, used unqualified
  (see the tools reference).
- Every `path`/`handler` is relative, inside the package, and names a regular
  file: no leading `/`, no `..`, no `\`, no `:` (so no URLs), no symlinks.
- Size limits: manifest 64 KiB, each theme or JSON resource 256 KiB, 128
  entries per directory.

A package with an invalid manifest is left out entirely, with a diagnostic;
other packages still load.

## Trust, enabling and restarting

- A package holding only themes is data and loads by default.
- A package with `commands`, `tools` or `providers` runs code with the user's
  full privileges — there is no sandbox. It starts **disabled**. The user enables
  it after reading it, in `config.json`:

  ```json
  "plugins": {
    "io.github.someone.nord": {"enabled": true}
  }
  ```

  Enabling is the user's trust decision: tell them how, and edit their
  `config.json` only when they ask you to. `"enabled": false` also turns off a
  data-only package.
- Every package change needs a restart: Omarchy `omarchy-restart-shell`;
  standalone and Flatpak, quit and reopen. The one exception: an existing
  theme file is reread each time the Color Theme picker opens.
- Removing a package: quit the app, delete the folder, start it again. The
  user's notes, settings and sign-ins are untouched.

## Workflow

1. Settle the kind and the behavior with the user. For a provider, also ask
   where the notes live and how the backend is reached.
2. Create the package folder and `plugin.json`.
3. Write each contribution, following its reference.
4. Run the check (below) and fix every error it reports.
5. For code packages, tell the user how to enable it; then restart.
6. Look for diagnostics in the app: the status line at startup, the foot of
   the command palette, the Key bindings page for shortcuts, the Color Theme
   picker's message for theme files, and the log (Omarchy:
   `journalctl --user -b | grep -e "note-note plugins" -e "Editing tool skipped"`;
   standalone: its stderr).

## Checking a package

`scripts/check.py` runs the installed application's own manifest validator
over the user's folders — the same discovery the app does at startup — and
lists what would load and what would be refused:

```sh
python3 <this skill>/scripts/check.py                                   # everything installed
python3 <this skill>/scripts/check.py --enable io.github.someone.nord   # as if it were enabled
python3 <this skill>/scripts/check.py --config ~/.var/app/io.github.andreivinca.note-note/config/notenote
python3 <this skill>/scripts/check.py --app ~/src/note-note             # an app it could not find
```

It exits non-zero when anything is refused. A disabled package with a valid
manifest is reported as a note, not an error; use `--enable` to list its
contributions and catch provider ID clashes. It does not check the colors
inside a theme file, nor load a tool's QML — a tool's ID clashes and QML
errors show in the log when the app starts: follow the rules in the themes reference, then open the
Color Theme picker, which names any theme it could not load and why.

## Code rules (commands, tools and providers)

- Portable code imports only `QtQuick`, `QtQuick.Controls`, `QtQml` and
  `NoteNote.Extensions 1.0`. Importing `Quickshell` or `qs.*` ties the package
  to Omarchy.
- A package cannot import files from the application's source tree; relative
  imports reach only its own files.
- Keep mutable data out of the package folder:
  `services.platform.stateDir + "/plugins/<package-id>"` for data, `cacheDir`
  for anything disposable. Never keep notes or unsaved drafts in a cache.
- Bound everything read from disk, network or a process, and hand secrets and
  note bodies to scripts over stdin, never in argv or a temp file. The
  provider reference spells this out.
- Style, as the bundled examples do it: braces on every `if`, `else`, `for`
  and `while`, with the body on its own lines.

## Inside the Note Note repository

Built-in packages live in `plugins/org.note-note.*/` in the source tree. They
are enabled by default, may use repository-relative imports and the shared
`services/providers/LaneProvider.qml` base, and have tests described in
`docs/testing.md`. When a checkout is at hand, its `docs/plugins.md`,
`docs/themes.md`, `docs/commands.md`, `docs/providers.md`,
`docs/editing-tools.md` and `services/extensions/manifest.py` are the
authority; the references here summarize them. Complete examples:
`examples/plugins/colors` (theme), `examples/plugins/greeting` (command +
keybinding + tool), `plugins/org.note-note.calendar` (tools with a menu and a
panel, using the built-ins' relative imports), `examples/hello` (provider),
also at https://github.com/andreivinca/omarchy-note-note.
