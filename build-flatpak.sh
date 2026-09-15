#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$project_dir"

app_id="io.github.andreivinca.note-note"
version="$(python3 -c 'import json; print(json.load(open("manifest.json"))["version"])')"
arch="$(flatpak --default-arch)"
flatpak_dir="$project_dir/build/flatpak"
output_dir="$project_dir/build/dist/$version"
bundle="note-note-$version-$arch.flatpak"

mkdir -p -- "$flatpak_dir" "$output_dir"

flatpak run org.flatpak.Builder --user --force-clean \
  --jobs="${JOBS:-2}" \
  --state-dir="$flatpak_dir/cache" --repo="$flatpak_dir/repo" \
  --mirror-screenshots-url=https://dl.flathub.org/media \
  --compose-url-policy=full \
  "$flatpak_dir/app" "$project_dir/packaging/flatpak/$app_id.json" \
  2>&1 | tee "$flatpak_dir/build.log"

flatpak build-bundle \
  --runtime-repo=https://flathub.org/repo/flathub.flatpakrepo \
  --arch="$arch" \
  "$flatpak_dir/repo" "$output_dir/$bundle" "$app_id" stable

(
  cd -- "$output_dir"
  sha256sum "$bundle" > "$bundle.sha256"
  sha256sum --check "$bundle.sha256"
)

printf '\nBundle: %s\nBuild log: %s\n' "$output_dir/$bundle" "$flatpak_dir/build.log"
