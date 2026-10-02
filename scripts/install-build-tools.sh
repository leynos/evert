#!/usr/bin/env bash
# Install the pinned `mold` linker binary and the repository's dated Rust toolchain.

set -euo pipefail

script_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=scripts/build-tools-common.sh
. "$script_dir/build-tools-common.sh"

LINKER_RELEASE_BASE_URL=${LINKER_RELEASE_BASE_URL:-https://github.com/rui314/mold/releases/download}
CURL_CONNECT_TIMEOUT=${CURL_CONNECT_TIMEOUT:-15}
CURL_MIN_BYTES_PER_SECOND=${CURL_MIN_BYTES_PER_SECOND:-1024}
CURL_STALL_SECONDS=${CURL_STALL_SECONDS:-60}
BUILD_TOOLS_WORKDIR=

remove_workdir() {
  [[ -n $BUILD_TOOLS_WORKDIR ]] || return 0
  rm -rf -- "$BUILD_TOOLS_WORKDIR"
  BUILD_TOOLS_WORKDIR=
}

trap remove_workdir EXIT

require_command() {
  command -v "$1" >/dev/null 2>&1 || fail "$1 is required to install build tools"
}

verify_linker_archive() {
  local archive=$1 name=$2 expected count
  expected=$(awk -v name="$name" '$2 == name { print $1 }' "$LINKER_SHA256SUMS_FILE")
  count=$(awk 'NF { count++ } END { print count + 0 }' <<< "$expected")
  [[ $count -eq 1 && $expected =~ ^[[:xdigit:]]{64}$ ]] ||
    fail "expected one valid checksum for $name in $LINKER_SHA256SUMS_FILE"
  printf '%s  %s\n' "$expected" "$archive" | sha256sum --check --status ||
    fail "checksum mismatch for $name; refusing to install"
  note "verified $name against $LINKER_SHA256SUMS_FILE"
}

is_setup_rust_cache_prefix() {
  [[ ${GITHUB_ACTIONS:-} == true && -n ${RUNNER_TOOL_CACHE:-} &&
    $BUILD_TOOLS_PREFIX == "$RUNNER_TOOL_CACHE"/mold/* ]]
}

reuse_setup_rust_linker() {
  local version=$1 archive_name archive_sha checksum_count arch cache_prefix marker
  local linker path_linker installed
  arch=$(linker_arch) || return 1
  archive_name="mold-$version-$arch-linux.tar.gz"
  archive_sha=$(awk -v name="$archive_name" '$2 == name { print $1 }' "$LINKER_SHA256SUMS_FILE") || return 1
  checksum_count=$(awk 'NF { count++ } END { print count + 0 }' <<< "$archive_sha") || return 1
  [[ $checksum_count -eq 1 && $archive_sha =~ ^[[:xdigit:]]{64}$ ]] || return 1

  cache_prefix="$RUNNER_TOOL_CACHE/mold/$version-$archive_sha/$arch"
  marker="$cache_prefix.complete"
  linker="$cache_prefix/bin/ld.mold"
  path_linker=$(command -v ld.mold 2>/dev/null) || path_linker=
  [[ $BUILD_TOOLS_PREFIX == "$cache_prefix" && -f $marker &&
    $path_linker == "$linker" && -x $linker ]] || return 1
  installed=$(linker_binary_version "$linker") || return 1
  [[ $installed == "$version" ]] || return 1

  note "reusing setup-rust's verified linker $version at $linker"
}

install_linker() {
  local version=$1 host=$2 arch name url workdir installed installed_pin_version
  local linker="$BUILD_TOOLS_PREFIX/bin/ld.mold"
  local installed_pin="$BUILD_TOOLS_PREFIX/share/evert/mold/VERSION"
  if ! is_supported_build_host "$host"; then
    note "the pinned \`mold\` linker and Clang wrapper require Linux x86_64 or aarch64 GNU; keeping the platform linker on $(build_host_description "$host")"
    return 0
  fi

  if is_setup_rust_cache_prefix; then
    if reuse_setup_rust_linker "$version"; then return 0; fi
    fail "setup-rust cache prefix for the linker failed provenance checks at $BUILD_TOOLS_PREFIX; rerun setup-rust before make install-build-tools"
  fi

  if [[ -x $linker && -r $installed_pin ]]; then
    installed=$(linker_binary_version "$linker") || installed=
    if installed_pin_version=$(read_single_line_pin "$installed_pin" 'installed linker' 2>/dev/null) &&
      [[ $installed == "$version" && $installed_pin_version == "$version" ]]; then
      note "reusing verified \`mold\` linker $version at $linker"
      return 0
    fi
  fi

  if [[ -e $linker || -e $installed_pin ]]; then
    note 'existing controlled-prefix linker does not match both pins; replacing it from the verified archive'
  fi

  require_command curl
  require_command sha256sum
  require_command tar
  require_command mktemp
  arch=$(linker_arch)
  name="mold-$version-$arch-linux.tar.gz"
  url="$LINKER_RELEASE_BASE_URL/v$version/$name"
  BUILD_TOOLS_WORKDIR=$(mktemp -d)
  workdir=$BUILD_TOOLS_WORKDIR

  note "downloading $url"
  curl --fail --silent --show-error --location \
    --connect-timeout "$CURL_CONNECT_TIMEOUT" \
    --speed-limit "$CURL_MIN_BYTES_PER_SECOND" --speed-time "$CURL_STALL_SECONDS" \
    --output "$workdir/$name" "$url" || fail "failed to download $name"
  verify_linker_archive "$workdir/$name" "$name"

  mkdir -p -- "$BUILD_TOOLS_PREFIX"
  tar --extract --gzip --strip-components=1 --directory "$BUILD_TOOLS_PREFIX" \
    --file "$workdir/$name" || fail "failed to unpack $name into $BUILD_TOOLS_PREFIX"
  installed=$(linker_binary_version "$linker") ||
    fail "installed \`mold\` linker is unusable at $linker"
  [[ $installed == "$version" ]] ||
    fail "installed \`mold\` linker reports $installed; expected $version"
  note "installed \`mold\` linker $version into $BUILD_TOOLS_PREFIX"
  note "put $BUILD_TOOLS_PREFIX/bin first on PATH when not using the Makefile targets"
}

install_clang_wrapper() {
  local host=$1
  local wrapper="$BUILD_TOOLS_PREFIX/bin/evert-clang-mold"
  local installed_pin="$BUILD_TOOLS_PREFIX/share/evert/mold/VERSION"
  if ! is_supported_build_host "$host"; then
    return 0
  fi
  require_command install
  mkdir -p -- "$(dirname -- "$wrapper")" "$(dirname -- "$installed_pin")"
  install -m 0755 "$script_dir/clang-linker.sh" "$wrapper" ||
    fail "failed to install the linker wrapper at $wrapper"
  install -m 0644 "$LINKER_VERSION_FILE" "$installed_pin" ||
    fail "failed to install the linker version pin at $installed_pin"
  note "installed the self-contained linker wrapper at $wrapper"
}

install_toolchain() {
  local toolchain=$1 component_list component
  local -a components=() rustup_args=(toolchain install "$toolchain" --profile minimal)

  command -v rustup >/dev/null 2>&1 || fail 'rustup not found on PATH; install it from https://rustup.rs'
  component_list=$(toolchain_components) || fail "cannot read components from $RUST_TOOLCHAIN_FILE"
  [[ -n $component_list ]] || fail "no components found in $RUST_TOOLCHAIN_FILE"
  mapfile -t components <<< "$component_list"
  for component in "${components[@]}"; do
    [[ $component =~ ^[[:alnum:]][[:alnum:]-]*$ ]] ||
      fail "invalid component in $RUST_TOOLCHAIN_FILE: $component"
    rustup_args+=(--component "$component")
  done

  note "installing toolchain $toolchain with components from rust-toolchain.toml"
  rustup "${rustup_args[@]}" || fail "failed to install toolchain $toolchain"
}

main() {
  local version toolchain host installed_host
  require_command rustup
  version=$(linker_version) || return 1
  toolchain=$(pinned_toolchain) || return 1
  host=$(toolchain_install_host "$toolchain") ||
    fail 'cannot determine the rustup host; install rustup and retry'
  install_toolchain "$toolchain"
  installed_host=$(toolchain_rust_host "$toolchain") ||
    fail "cannot run the installed toolchain $toolchain"
  [[ $installed_host == "$host" ]] ||
    fail "installed toolchain host $installed_host differs from rustup host $host"
  install_linker "$version" "$installed_host"
  install_clang_wrapper "$installed_host"
  note 'ready; verify with: make check-build-tools'
}

main "$@"
