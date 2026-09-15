# Packaging

Group build recipes by package format. Keep desktop integration shared so
every package uses the same launcher, application icon, and store metadata.

| Path | Purpose |
|---|---|
| `desktop/` | Desktop entry, SVG icon, and AppStream metadata, installed by CMake for all standalone packages |
| `flatpak/` | Flatpak manifest for building the current working tree |
| `build-info.json.in` | Build metadata template configured by CMake |
| `package.py` | Creates native standalone and Omarchy plugin release archives |

Add other formats in their own directories when implemented, for example
`aur/` for an AUR package. Reuse the files in `desktop/` through the CMake
installation rather than maintaining a separate copy for each format.

## Local builds

Run `./build-flatpak.sh` from the repository root to create a Flatpak bundle
and checksum. See [Flatpak builds](../docs/flatpak.md) for prerequisites and
output locations, and [release archives](../docs/standalone.md#release-archives)
for the native and Omarchy archive commands. Generated artifacts live in
`build/`.

## Flathub submission

The Flathub fork is a separate Git repository. Its submission manifest lives
at the root of that repository and fetches a published release by tag and
commit. The manifest in `flatpak/` reads the local working tree instead.

The current submission draft targets release `v1.0.21`, whose packaging paths
predate this layout. Its screenshot patch uses those released paths. When a
published release includes the screenshot metadata, update the submission
manifest to that release and remove the patch.
