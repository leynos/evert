#!/usr/bin/env bash
# Select only the checksum-pinned `mold` installed with this wrapper.

set -euo pipefail

note() { printf 'build-tools: %s\n' "$*" >&2; }

script_path=${BASH_SOURCE[0]}
script_dir=$(cd -- "$(dirname -- "$script_path")" && pwd)
script_parent=$(cd -- "$script_dir/.." && pwd)
installed_pin="$script_parent/share/evert/mold/VERSION"

if [[ -r $installed_pin ]]; then
  BUILD_TOOLS_PREFIX=$script_parent
  linker_version_file=$installed_pin
else
  repository_root=$script_parent
  BUILD_TOOLS_PREFIX=${BUILD_TOOLS_PREFIX:-${HOME:?HOME must be set}/.local}
  linker_version_file="$repository_root/tools/mold/VERSION"
fi

read_linker_pin() {
  local -a lines=()
  [[ -r $linker_version_file ]] || {
    printf 'build-tools: cannot read linker version pin: %s\n' "$linker_version_file" >&2
    return 1
  }
  mapfile -t lines < "$linker_version_file"
  if [[ ${#lines[@]} -ne 1 || ! ${lines[0]} =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    printf 'build-tools: invalid linker version pin: %s\n' "$linker_version_file" >&2
    return 1
  fi
  printf '%s' "${lines[0]}"
}

linker_binary_version() {
  local binary=$1 output
  output=$("$binary" --version 2>/dev/null) || return 1
  awk 'NR == 1 && $1 == "mold" { print $2 }' <<< "$output"
}

linker_binary="$BUILD_TOOLS_PREFIX/bin/ld.mold"
pinned=$(read_linker_pin) || exit 1

if [[ ! -x $linker_binary ]]; then
  note "pinned \`mold\` linker is missing or not executable: $linker_binary"
  note 'install it with: make install-build-tools'
  exit 1
fi

if ! installed=$(linker_binary_version "$linker_binary") || [[ $installed != "$pinned" ]]; then
  note "linker at $linker_binary does not match pinned \`mold\` linker version $pinned"
  note 'run make install-build-tools to match'
  exit 1
fi

if ! command -v clang >/dev/null 2>&1; then
  note 'clang not found on PATH; install clang before building'
  exit 1
fi

exec clang -B"$BUILD_TOOLS_PREFIX/bin" "$@"
