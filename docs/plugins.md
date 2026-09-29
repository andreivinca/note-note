# Application plugin packages

Built-ins live in `plugins/<package>/` beside the shared application. User
packages live in `$XDG_CONFIG_HOME/notenote/plugins/<package>/` (default
`~/.config/notenote/plugins/`). Each package keeps all its immutable resources
inside one folder and declares them in `plugin.json`. This manifest is distinct
from the repository root's Omarchy `manifest.json`.

```json
{
  "schemaVersion": 1,
  "id": "org.example.notes",
  "name": "Example",
  "version": "1.0.0",
  "apiVersion": 1,
  "contributes": {
    "commands": [{"id": "hello", "title": "Hello", "handler": "Hello.qml"}],
    "keybindings": [{"command": "hello", "key": "Ctrl+Alt+H", "context": "notes"}],
    "themes": [{"id": "blue", "path": "blue.json"}],
    "providers": [{"id": "example", "path": "Provider.qml", "order": 500}],
    "tools": [{"id": "insertStamp", "path": "InsertStamp.qml"}]
  }
}
```

A command names a `handler` or a `workspaceAction`, one of the two
([commands](commands.md)). A theme's name is the one its file states. A
provider's optional `order` (0 to 9999, 1000 when left out) says where its tabs
stand among the others while the settings name no order of their own; lower
comes first. A tool is an editing-toolbar action with its menu entries,
shortcut and panel ([editing tools](editing-tools.md#tools-in-a-package)).

Use only the kinds the package actually supplies. API and manifest versions are
integers; package versions are `major.minor.patch` without leading zeroes. Package
IDs are dot-separated lowercase identifiers; local IDs use lowercase letters,
digits, and hyphens and start with a letter. `org.note-note.*` and `user.themes`
are reserved. A provider's manifest ID must match its QML `id`; it remains the
prefix of note and notebook identities rather than becoming a qualified ID.
A tool's manifest ID is its action ID, a lowercase letter followed by up to 63
letters and digits (`insertStamp`), and must match its QML `toolId`. It is not
qualified either: toolbar settings, `tool/<id>` shortcut overrides and
`editorTool <id>` name tools the same wherever they come from.

## Writing a package with an AI assistant

[`skills/note-note-plugin/`](../skills/note-note-plugin/SKILL.md) is a skill
for plugin authors' assistants, installed as the [README](../README.md#writing-plugins)
shows. It summarizes this document, [themes](themes.md), [commands](commands.md)
and [providers](providers.md), and its `scripts/check.py` runs `manifest.py`
over the user's folders. When one of those contracts changes, change the
skill's reference for it in the same commit: authors' assistants read the
skill, not these documents. Editing tools are summarized there from
[editing tools](editing-tools.md).

## Enabling trusted code

Data-only theme packages load by default. New packages containing commands,
providers or tools start disabled. After reviewing their code, enable one in Settings:

```json
"plugins": {
  "org.example.notes": {"enabled": true}
}
```

Restart to apply package changes. An explicit false disables data-only packages
too. Built-ins are enabled by default; the appearance package and System recovery
theme are protected. `providers.<id>.enabled` remains the provider activation
setting. A disabled package prevents all its contributions, including keybindings, on the next start.
See [commands](commands.md#registering-shortcuts) for binding scopes, conflicts, and user overrides.

**Enabling QML trusts it with the host process's privileges.** In Omarchy that
includes the shell; in Flatpak it shares the app sandbox and accessible files.
Manifest/resource checks and the small command API are not a code sandbox.
There is no store, signing system, dependency resolver, or automatic updater.

## Discovery and resources

Discovery examines immediate directories, validates complete manifests, then
publishes descriptors. It never executes a command to obtain its title. Invalid
packages produce diagnostics without disabling unrelated packages. Duplicate
external package IDs reject every claimant. Built-in provider IDs are reserved;
ambiguous external provider IDs also reject every claimant, each named in its
own diagnostic. Tool IDs are settled when the editor loads its tools, among the
application's own and every package's: a tool the application ships, in
`ui/tools/` or a built-in package, keeps its ID against a user package, and any
other shared ID rejects every claimant. Its reasons are in the log.

What the application ships is read first, so nothing installed beside it can
use up its share of a limit: a package that would cross one is left out, with
a diagnostic, and the rest stands. What could not be loaded is said in the
status line at startup and at the foot of the command palette, and written to
the log in full.

A shortcut a package contributes is checked for its key and context by the
shortcut resolver, not by discovery: one it cannot use costs that binding and
is listed on the Key bindings page.

Manifest resources must be regular files beneath their package. Absolute paths,
schemes, traversal and symlinks are refused. Supported resource reads reopen via
directory descriptors with no-follow flags and byte/deadline limits. Limits are
128 entries per directory, 64 KiB per manifest, 256 KiB per resource/theme,
128 contributions of each kind per package, 4,096 published contributions,
8 MiB catalog input, and 32 JSON levels. Process transport also bounds output and
time. QML's own loader is trusted executable code, outside these data-read rules.

The stable `NoteNote.Extensions 1.0` import is registered in each host. It
provides `Command` for command handlers and `Tool` for editing tools, so
external packages need no repository-relative imports. Providers retain the injected
`host` and `services` contract documented in [providers](providers.md).
Mutable plugin data belongs under `services.platform.stateDir/plugins/<id>` or
`cacheDir/plugins/<id>`; notes and recovery drafts must never live in the package
or a disposable cache. Existing provider state/cache/account paths are unchanged.

## Migration and removal

The four built-in providers now each have a package, including private scripts,
logos and tests. The calendar tools under **Insert → Insert month** are the
`org.note-note.calendar` package's. There is no top-level provider implementation directory or
second built-in discovery list. Existing provider IDs and stored data are unchanged.

The legacy external provider locations remain a compatibility adapter for the
1.x series. Removal of that adapter is scheduled for 2.0 and must be announced
in its release notes. Migrate an external provider by moving its complete folder
under the shared user plugin root, adding a manifest, fixing any private relative
imports, and enabling its package. Legacy providers retain their previous
activation defaults during this window. Built-in ID shadowing is now rejected.

To remove a user package, first quit every host using it, then remove its whole
folder and restart. Hiding the Omarchy overlay does not unload its code. A removed
package leaves no registered themes/commands/providers/tools/keybindings on restart; a missing
selected theme falls back to System without changing saved settings. Removal
preserves notes, recovery data, credentials, and config. There is no hot-unload
or removal manager: do not delete resources beneath accepted provider writes.
