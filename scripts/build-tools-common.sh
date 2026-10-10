#!/usr/bin/env bash
# Shared pin and diagnostic helpers for the build-tool entry points.

set -euo pipefail

BUILD_TOOLS_SCRIPT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
BUILD_TOOLS_REPO_ROOT=$(cd -- "$BUILD_TOOLS_SCRIPT_DIR/.." && pwd)

LINKER_VERSION_FILE=${LINKER_VERSION_FILE:-$BUILD_TOOLS_REPO_ROOT/tools/mold/VERSION}
LINKER_SHA256SUMS_FILE=${LINKER_SHA256SUMS_FILE:-$BUILD_TOOLS_REPO_ROOT/tools/mold/SHA256SUMS}
RUST_TOOLCHAIN_FILE=${RUST_TOOLCHAIN_FILE:-$BUILD_TOOLS_REPO_ROOT/rust-toolchain.toml}
BUILD_TOOLS_PREFIX=${BUILD_TOOLS_PREFIX:-${HOME:?HOME must be set}/.local}

note() { printf 'build-tools: %s\n' "$*" >&2; }

fail() {
  note "$*"
  exit 1
}

read_single_line_pin() {
  local file=$1 label=$2
  local -a lines=()

  [[ -r $file ]] || fail "cannot read $label pin: $file"
  mapfile -t lines < "$file"
  [[ ${#lines[@]} -eq 1 && -n ${lines[0]} ]] ||
    fail "expected one non-empty line in $label pin: $file"
  [[ ${lines[0]} != *[[:space:]]* ]] || fail "$label pin contains whitespace: $file"
  printf '%s' "${lines[0]}"
}

linker_version() {
  local value
  value=$(read_single_line_pin "$LINKER_VERSION_FILE" linker)
  [[ $value =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] ||
    fail "invalid \`mold\` linker version in $LINKER_VERSION_FILE: $value"
  printf '%s' "$value"
}

pinned_toolchain() {
  local value
  [[ -r $RUST_TOOLCHAIN_FILE ]] || fail "cannot read toolchain pin: $RUST_TOOLCHAIN_FILE"
  value=$(awk -F '"' '/^[[:space:]]*channel[[:space:]]*=/ { print $2; exit }' "$RUST_TOOLCHAIN_FILE")
  [[ -n $value ]] || fail "no channel found in $RUST_TOOLCHAIN_FILE"
  printf '%s' "$value"
}

toolchain_components() {
  awk '
    function emit_components(value, remainder) {
      remainder = value
      while (match(remainder, /"[^"]+"/)) {
        print substr(remainder, RSTART + 1, RLENGTH - 2)
        remainder = substr(remainder, RSTART + RLENGTH)
      }
    }
    /^[[:space:]]*components[[:space:]]*=/ {
      if (found) exit 1
      found = 1
      line = $0
      sub(/^[^[]*\[/, "", line)
      in_array = 1
      emit_components(line)
      if (index(line, "]") > 0) {
        complete = 1
        exit
      }
      next
    }
    in_array {
      line = $0
      emit_components(line)
      if (index(line, "]") > 0) {
        complete = 1
        exit
      }
    }
    END {
      if (!found || !complete) exit 1
    }
  ' "$RUST_TOOLCHAIN_FILE"
}

rustup_default_host() {
  local details host
  command -v rustup >/dev/null 2>&1 || return 1
  details=$(rustup show 2>/dev/null) || return 1
  host=$(awk '$1 == "Default" && $2 == "host:" { print $3; exit }' <<< "$details")
  [[ -n $host ]] || return 1
  printf '%s' "$host"
}

toolchain_rust_host() {
  local toolchain=$1 details host
  details=$(rustup run "$toolchain" rustc -vV 2>/dev/null) || return 1
  host=$(awk '$1 == "host:" { print $2; exit }' <<< "$details")
  [[ -n $host ]] || return 1
  printf '%s' "$host"
}

toolchain_install_host() {
  local toolchain=$1 host
  if host=$(toolchain_rust_host "$toolchain"); then
    printf '%s' "$host"
  else
    rustup_default_host
  fi
}

is_supported_build_host() {
  case "$(uname -s):$(uname -m):$1" in
    Linux:x86_64:x86_64-unknown-linux-gnu | Linux:aarch64:aarch64-unknown-linux-gnu) return 0 ;;
    *) return 1 ;;
  esac
}

build_host_description() {
  printf '%s/%s with Rust host %s' "$(uname -s)" "$(uname -m)" "$1"
}

linker_arch() {
  case $(uname -m) in
    x86_64 | amd64) printf 'x86_64' ;;
    aarch64 | arm64) printf 'aarch64' ;;
    *) fail "unsupported architecture for the pinned \`mold\` linker release: $(uname -m)" ;;
  esac
}

linker_binary_version() {
  local binary=$1 output
  output=$("$binary" --version 2>/dev/null) || return 1
  awk 'NR == 1 && $1 == "mold" { print $2 }' <<< "$output"
}

installed_linker_version() {
  linker_binary_version mold
}
