#!/usr/bin/env bash
# Check the compiler and linker capabilities required by development builds.

set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/build-tools-common.sh
. "$script_dir/build-tools-common.sh"

check_linker() {
  local pinned=$1 host=$2 linker installed wrapper wrapper_on_path installed_pin installed_pin_version resolution
  if ! is_supported_build_host "$host"; then
    note "the pinned \`mold\` linker and Clang wrapper are not required on $(build_host_description "$host"); keeping the platform linker"
    return 0
  fi
  linker="$BUILD_TOOLS_PREFIX/bin/ld.mold"
  if [[ ! -x $linker ]]; then
    note "pinned \`mold\` linker is missing or not executable: $linker"
    note 'install it with: make install-build-tools'
    return 1
  fi
  if ! installed=$(linker_binary_version "$linker") || [[ -z $installed ]]; then
    note "\`mold\` linker at $linker is unusable or cannot report its version"
    note 'reinstall it with: make install-build-tools'
    return 1
  fi
  if [[ $installed != "$pinned" ]]; then
    note "\`mold\` linker $installed at $linker does not match the pin $pinned"
    note 'run make install-build-tools to match'
    return 1
  fi
  installed_pin="$BUILD_TOOLS_PREFIX/share/evert/mold/VERSION"
  if ! [[ -r $installed_pin ]]; then
    note "installed linker pin is missing: $installed_pin"
    note 'run make install-build-tools to install the linker wrapper and pin'
    return 1
  fi
  if ! installed_pin_version=$(read_single_line_pin "$installed_pin" 'installed linker'); then
    note "installed linker pin is invalid: $installed_pin"
    note 'run make install-build-tools to install the linker wrapper and pin'
    return 1
  fi
  if [[ $installed_pin_version != "$pinned" ]]; then
    note "installed linker pin $installed_pin_version does not match repository pin $pinned"
    note 'run make install-build-tools to match'
    return 1
  fi
  wrapper="$BUILD_TOOLS_PREFIX/bin/evert-clang-mold"
  if [[ ! -x $wrapper ]]; then
    note "pinned Clang linker wrapper is missing or not executable: $wrapper"
    note 'install it with: make install-build-tools'
    return 1
  fi
  if ! wrapper_on_path=$(command -v evert-clang-mold 2>/dev/null) ||
    [[ $wrapper_on_path != "$wrapper" ]]; then
    note "PATH does not select the installed linker wrapper at $wrapper"
    note 'ensure BUILD_TOOLS_PREFIX/bin is first on PATH, then run make install-build-tools'
    return 1
  fi
  if ! resolution=$("$wrapper" -fuse-ld=mold -### -x c /dev/null -o /dev/null 2>&1); then
    note "Clang linker wrapper at $wrapper cannot resolve the pinned \`mold\` linker"
    note 'install clang and run make install-build-tools'
    return 1
  fi
  if ! grep -Fq -- "$linker" <<< "$resolution"; then
    note "Clang does not resolve -fuse-ld=mold to $linker"
    note 'run make install-build-tools to select the pinned linker'
    return 1
  fi
  note "\`mold\` linker $installed at $linker; the installed wrapper selects the pinned linker"
}

check_toolchain() {
  local toolchain=$1 details host
  if ! command -v rustup >/dev/null 2>&1; then
    note 'rustup not found on PATH; it is required to select the pinned toolchain'
    note 'install rustup from https://rustup.rs, then run make install-build-tools'
    return 1
  fi
  if ! details=$(rustup run "$toolchain" rustc -vV 2>/dev/null); then
    note "toolchain $toolchain is not installed or cannot run"
    note 'install it with: make install-build-tools'
    return 1
  fi
  host=$(awk '$1 == "host:" { print $2; exit }' <<< "$details")
  if [[ -z $host ]]; then
    note "could not determine the host for toolchain $toolchain"
    note 'reinstall it with: make install-build-tools'
    return 1
  fi
  printf '%s' "$host"
  note "toolchain $toolchain is available for $host"
}

main() {
  local status=0 linker_pin toolchain_pin host
  linker_pin=$(linker_version) || return 1
  toolchain_pin=$(pinned_toolchain) || return 1
  if ! host=$(check_toolchain "$toolchain_pin"); then status=1; fi
  if [[ -n $host ]]; then check_linker "$linker_pin" "$host" || status=1; fi
  [[ $status -eq 0 ]] || note 'capability check failed; see the messages above'
  return "$status"
}

main "$@"
