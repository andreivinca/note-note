# Standalone Flatpak

The Flatpak packages the standalone Qt application. The Omarchy plugin
continues to use its own archive or Git installation; it runs in the shell.
Both use the shared workspace and providers in this repository.

## Install and run

With Flatpak installed, install the local 1.0.21 x86_64 bundle:

```bash
flatpak install --user ./note-note-1.0.21-x86_64.flatpak
flatpak run io.github.andreivinca.note-note
```

The bundle records Flathub as its runtime source. Flatpak downloads the
matching KDE runtime if needed; the SDK and builder are only needed for
building. Note Note appears in your desktop launcher after installation.
This is a local bundle, not a published Flathub listing. Install a newer
bundle with the same command to update the application.

## Build

The [manifest](../packaging/flatpak/io.github.andreivinca.note-note.json) uses
`org.kde.Platform` and `org.kde.Sdk` 6.11. Qt and Python come from the
runtime; the manifest builds a pinned, checksum-verified inotify-tools
source archive and then the application using CMake. Host Qt packages
are not used. The Qt text inspector is compiled into the executable.

Set up the build tools once. The build script also uses Bash, Python 3,
and the standard `sha256sum` utility on the host:

```bash
flatpak remote-add --user --if-not-exists flathub https://flathub.org/repo/flathub.flatpakrepo
flatpak install --user flathub org.flatpak.Builder org.kde.Sdk//6.11 org.kde.Platform//6.11
```

From the repository root, build the current working tree and create an
installable bundle:

```bash
./build-flatpak.sh
```

The [script](../build-flatpak.sh) locates the repository from its own path,
so it also works when launched from another directory. It reads the version
from `manifest.json` and uses Flatpak's default architecture. The manifest
remains the build recipe, including its runtime, dependencies and permissions.
The build downloads and prepares the screenshot metadata for software stores.

The script runs two compile jobs by default. To choose another limit:

```bash
JOBS=4 ./build-flatpak.sh
```

| Output | Location |
|---|---|
| Installable bundle | `build/dist/<version>/note-note-<version>-<arch>.flatpak` |
| SHA-256 checksum | The bundle path followed by `.sha256` |
| Build log | `build/flatpak/build.log` |
| Build files and cache | `build/flatpak/app/` and `build/flatpak/cache/` |
| Local OSTree repository | `build/flatpak/repo/` |

The checksum is generated and checked after the bundle is built. Build output
also appears in the terminal, and a failed build stops the script before
bundling. The runtime is downloaded separately when installing the bundle.
Keep `manifest.json`, the CMake project version and the AppStream release
metadata in sync when changing versions.

The script builds locally; it does not install the app, create commits, or
publish releases. Flathub uses its own build automation and the manifest in
the app's Flathub repository. To test that manifest locally, run
`flatpak run --command=flathub-build org.flatpak.Builder <manifest>` from its
checkout, following the [Flathub build instructions](https://docs.flathub.org/docs/for-app-authors/submission#build-and-install).

## Storage and permissions

| Data | Default location |
|---|---|
| Settings | `~/.var/app/io.github.andreivinca.note-note/config/notenote/config.json` |
| Sessions and sign-ins | `~/.var/app/io.github.andreivinca.note-note/.local/state/notenote/` |
| Caches | `~/.var/app/io.github.andreivinca.note-note/cache/notenote/` |
| External providers | `~/.var/app/io.github.andreivinca.note-note/config/notenote/providers/` |
| Local notebooks | `~/Notes/`, shared with the native app and plugin |

Sign in separately in the Flatpak. Settings and tokens are not copied
from the native app or Omarchy. External providers execute inside the
same sandbox and have the same permissions as the application.

The manifest grants read/write access to `~/Notes`, network access for
connected providers, Wayland with an X11 fallback, and graphics acceleration.
Qt handles clipboard access and opens external URLs through the desktop
portal. Theme files have narrowly scoped read-only permissions; there is
no blanket home-directory or session-bus access.

For notes elsewhere, grant that directory explicitly and set
`providers.local.notesDir` in the app's Settings to the same path:

```bash
flatpak override --user --filesystem=/absolute/path/to/notebooks io.github.andreivinca.note-note
```

Linked notes and images must also be inside an accessible directory.
ImageMagick is optional and is not bundled: images within the normal
size limits work, but automatic scaling of oversized pasted images is
unavailable.

## System colors

The Flatpak reads the host's Omarchy theme and KDE `kdeglobals` using
read-only grants. The theme resolver uses `HOST_XDG_CONFIG_HOME` and
`HOST_XDG_STATE_HOME` inside Flatpak, while application storage continues
to use the sandbox's private XDG directories. Desktop portal preferences
and the built-in palette remain available when theme files cannot be read.

The manifest covers Omarchy's standard current-theme directories. A custom
`XDG_STATE_HOME`, or a theme symlink pointing outside the granted directories,
needs an additional read-only filesystem override for that location.
GNOME's portal supplies appearance preferences and an accent when supported;
it does not expose every GNOME theme color.

## Verify the installed bundle

Close any running Note Note Flatpak, then run the integration tests from
the repository root:

```bash
python3 tests/flatpak_selftest.py
```

The script runs against the installed app and platform runtime, with the
repository available read-only and networking disabled. It creates
temporary notes, settings and test credentials, and checks the packaged
process transport, clipboard, editor, saves, providers, system theme
fixture and window shutdown. It also checks activation across two separate
Flatpak launches. It does not use your notebooks or account tokens.

See Flatpak's official documentation for [Qt runtimes](https://docs.flatpak.org/en/latest/qt.html),
[single-file bundles](https://docs.flatpak.org/en/latest/single-file-bundles.html)
and [sandbox permissions](https://docs.flatpak.org/en/latest/sandbox-permissions.html).
