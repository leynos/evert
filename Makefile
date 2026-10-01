.PHONY: help all clean test build release coverage lint fmt check-fmt \
	markdownlint nixie audit rust-audit spelling test-workflow-contracts \
	typecheck install-build-tools check-build-tools lint-clippy lint-whitaker \
	lint-python typecheck-python typecheck-rust

# Keep the composite gates sequential even when a caller uses `make -j`.
.NOTPARALLEL: all lint

SHELL := bash


TARGET ?= evert

CARGO ?= cargo
BUILD_JOBS ?=
RUST_FLAGS ?=
RUST_FLAGS := -D warnings $(RUST_FLAGS)
RUSTDOC_FLAGS ?=
RUSTDOC_FLAGS := --cfg docsrs -D warnings $(RUSTDOC_FLAGS)
CARGO_FLAGS ?= --all-targets --all-features
CLIPPY_FLAGS ?= $(CARGO_FLAGS) -- $(RUST_FLAGS)
TEST_FLAGS ?= $(CARGO_FLAGS)
TEST_CMD := $(if $(shell $(CARGO) nextest --version 2>/dev/null),nextest run,test)
COVERAGE_LINKER_FLAGS ?= -fuse-ld=lld
COVERAGE_RUST_FLAGS ?= $(RUST_FLAGS) -C link-arg=$(COVERAGE_LINKER_FLAGS)
MDLINT ?= markdownlint-cli2
# `make fmt` and `make check-fmt` call mdtablefix directly. `--git` selects the
# Markdown files Git tracks and `--include-untracked` adds the untracked files
# Git does not ignore, so a new document is formatted before it is staged.
# Both modes need mdtablefix 0.6.0 or later; CI pins the version at the
# install-mdtablefix step.
MDTABLEFIX ?= mdtablefix
MDTABLEFIX_SELECT = --git --include-untracked
MDTABLEFIX_RULES = --wrap --renumber --breaks --ellipsis --fences
NIXIE ?= nixie
WHITAKER ?= whitaker
WHITAKER_PACKAGES ?= --all
UV ?= uv
UV_ENV = UV_CACHE_DIR=.uv-cache UV_TOOL_DIR=.uv-tools

# The Python baseline every uv-driven Python helper pins. Bump it together with
# `target-version` and `py-version` in pyproject.toml; the workflow contract
# tests hold the three in sync.
PYTHON_BASELINE ?= 3.14

# The Python lint gateway mirrors leynos/netsuke. Each tool is pinned so `make`
# and CI run the same release: rule sets differ between releases, and an
# unpinned install fails the gate without any code change. Bump deliberately
# and fix new findings in the same commit.
RUFF_VERSION ?= 0.16.4
RUFF = $(UV_ENV) $(UV) tool run --from ruff==$(RUFF_VERSION) ruff
# Pylint must run on the baseline so it parses every owned source; the
# `--load-plugins=` argument clears configured plugins so this pass runs
# exactly the messages pyproject.toml enables.
PYLINT_VERSION ?= 4.0.9
PYLINT = $(UV_ENV) $(UV) tool run --managed-python --python $(PYTHON_BASELINE) \
	--from 'pylint==$(PYLINT_VERSION)' pylint --load-plugins=
# The df12 house lints need CPython 3.14: they parse syntax older runtimes
# cannot, and the baseline-gated messages (R9112, C9112) key off the
# `py-version` in pyproject.toml. They run through `uv tool run` so the
# repository never needs a project virtual environment for a Rust
# contributor's sake.
# Pin the commit, not the tag: uv resolves a commit from its cache without the
# network, so the gate keeps working offline (a tag forces a fetch on every run
# and fails whenever GitHub is unreachable), and a moved tag cannot change what
# runs. This is the commit of the v0.3.0 release.
DF12_PYTHON_LINTS_REF ?= 4cf41736cce2f7ba2778882a5c629c044568a0e5
DF12_PYTHON_LINTS = git+https://github.com/leynos/df12-python-lints.git@$(DF12_PYTHON_LINTS_REF)
DF12_PYLINT_MESSAGES = R9101,C9102,R9103,R9104,C9105,C9106,C9107,R9108,R9109,R9110,R9111,R9112,C9112
DF12_PYLINT = $(UV_ENV) $(UV) tool run --python $(PYTHON_BASELINE) \
	--from 'pylint==$(PYLINT_VERSION)' --with '$(DF12_PYTHON_LINTS)' pylint \
	--disable=all --load-plugins=df12_python_lints \
	--enable=$(DF12_PYLINT_MESSAGES)
AMBRLEAKS = $(UV_ENV) $(UV) tool run --python $(PYTHON_BASELINE) \
	--from '$(DF12_PYTHON_LINTS)' ambrleaks
# Interrogate is a documentation-coverage gate only; the repository is not a
# Python distribution and needs no project metadata.
INTERROGATE_VERSION ?= 1.7.0
INTERROGATE = $(UV_ENV) $(UV) tool run --python $(PYTHON_BASELINE) \
	--from 'interrogate==$(INTERROGATE_VERSION)' interrogate --fail-under 100
# Pin ty so `make` and CI invoke the same typechecker release. ty is pre-1.0
# and its diagnostics shift between releases, so an unpinned install can fail
# the gate without any code change. Bump deliberately and fix the new
# diagnostics in the same commit.
TY_VERSION ?= 0.0.74
# ty resolves third-party imports from the environment `uv tool run` builds, so
# the packages the Python sources import are installed beside it. pytest is
# pinned to keep ty's view of its types stable; PyYAML is a floor, as in
# `test-workflow-contracts`.
TY_DEPENDENCIES = --with pytest==9.0.2 --with 'pyyaml>=6'
# The contract tests import their sibling modules through the directory pytest
# puts on `sys.path`, which ty does not follow, so those directories are named
# as search roots. Only directories that exist are passed.
PYTHON_IMPORT_ROOTS = $(addprefix --extra-search-path ,$(wildcard tests/workflow_contracts scripts .github/scripts))
# Directories that may hold Python: tests, scripts, benchmarks, and the
# modules that GitHub Actions workflows and local actions run. Only the roots
# that contain Python today are linted, so a new script or benchmark directory
# is covered as soon as it exists, and an empty root is not an error. The
# workflow contract tests require every tracked Python file to sit under one
# of these roots.
PYTHON_SOURCE_ROOTS ?= .github/scripts .github/actions scripts tests benches benchmarks
PYTHON_SOURCES = $(strip $(foreach root,$(PYTHON_SOURCE_ROOTS),$(if $(strip $(shell find $(root) -type f -name '*.py' -not -path '*/__pycache__/*' 2>/dev/null | head -n 1)),$(root))))

# CV-005 CodeScene contracts run from the shared-actions commit pinned here.
# `.github/cv005.toml` carries this repository's selection parameters.
CV005_CONTRACTS_REF ?= a38feb9be25755c30eca5bda96bd3786a5b89c6b
CV005_CONTRACTS = $(UV_ENV) $(UV) tool run --python 3.13 \
	--from 'git+https://github.com/leynos/shared-actions@$(CV005_CONTRACTS_REF)\#subdirectory=packages/cv005-contracts' \
	cv005-contracts

TYPOS_CONFIG_BUILDER = $(UV_ENV) $(UV) tool run --python 3.14 --from \
	"git+https://github.com/leynos/typos-config-builder.git@v0.1.3" \
	typos-config-builder

# The development build standard (concordat rule `rust-build-defaults`):
# On an x86_64 GNU/Linux host, parallel rustc and `mold` apply when the
# effective target is `x86_64-unknown-linux-gnu`; rustc uses its LLVM backend.
# Route each Cargo command by its effective target. A sole exact native
# --target takes precedence; commands without it follow CARGO_BUILD_TARGET.
# Assigned RUSTFLAGS replace Cargo's target table, so each route restates the
# standard flags. Coverage and release retain their explicit LLVM routes.
BUILD_HOST_OS := $(shell uname -s)
BUILD_HOST_ARCH := $(shell uname -m)
NATIVE_CARGO_TARGET := x86_64-unknown-linux-gnu

# Return the value of the first --target option in a flag list. Unknown forms
# and empty joined values are sentinels, so they fail the exact-target check.
define cargo_target_option_value
$(if $(strip $1),$(if $(filter --target-dir --target-dir=%,$(firstword $1)),$(call cargo_target_option_value,$(wordlist 2,$(words $1),$1)),$(if $(filter --target,$(firstword $1)),$(if $(word 2,$1),$(word 2,$1),__missing__),$(if $(filter --target=%,$(firstword $1)),$(if $(patsubst --target=%,%,$(firstword $1)),$(patsubst --target=%,%,$(firstword $1)),__missing__),$(if $(filter --target%,$(firstword $1)),__malformed__,$(call cargo_target_option_value,$(wordlist 2,$(words $1),$1)))))),)
endef

# No target is valid; an explicit target is valid only when it is the sole,
# well-formed option and names this native target. Cargo's --target-dir is a
# separate output-directory option and does not select a compilation target.
define cargo_target_option_words
$(filter-out --target-dir --target-dir=%,$(filter --target%,$1))
endef

# Keep rustc-only arguments after Cargo's literal `--` out of target routing.
define cargo_words_before_separator
$(if $(strip $1),$(if $(filter --,$(firstword $1)),,$(firstword $1) $(call cargo_words_before_separator,$(wordlist 2,$(words $1),$1))))
endef

define cargo_target_route_supported
$(if $(call cargo_target_option_words,$1),$(if $(filter 1,$(words $(call cargo_target_option_words,$1))),$(if $(filter $(NATIVE_CARGO_TARGET),$(call cargo_target_option_value,$1)),yes,),),yes)
endef

define cargo_effective_target_supported
$(if $(call cargo_target_option_words,$1),$(call cargo_target_route_supported,$1),$(if $(filter-out $(NATIVE_CARGO_TARGET),$(strip $(CARGO_BUILD_TARGET))),,yes))
endef

# Pass each recipe's actual target arguments: empty for build, rustdoc and
# doctest; CARGO_FLAGS for typecheck; TEST_FLAGS for the test runner. Target
# selection stops at each command's first literal `--` separator.
define standard_rustflags_for
$(if $(and $(filter Linux,$(BUILD_HOST_OS)),$(filter x86_64,$(BUILD_HOST_ARCH)),$(call cargo_effective_target_supported,$1)),-Zthreads=8 -Clinker=evert-clang-mold -Clink-arg=-fuse-ld=mold)
endef

STANDARD_RUSTFLAGS = $(call standard_rustflags_for,)
CARGO_FLAGS_STANDARD_RUSTFLAGS = $(call standard_rustflags_for,$(call cargo_words_before_separator,$(CARGO_FLAGS)))
TEST_FLAGS_STANDARD_RUSTFLAGS = $(call standard_rustflags_for,$(call cargo_words_before_separator,$(TEST_FLAGS)))
CLIPPY_FLAGS_STANDARD_RUSTFLAGS = $(call standard_rustflags_for,$(call cargo_words_before_separator,$(CLIPPY_FLAGS)))
define gate_rustflags_with
$(if $1,env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS="$${RUSTFLAGS:+$$RUSTFLAGS }$(RUST_FLAGS) $1",bash -c 'make_flags=$$1; shift; effective_flags="$${RUSTFLAGS:+$$RUSTFLAGS }$$make_flags"; set -f; previous=; for flag in $$effective_flags; do bad=; if [[ "$$flag" == -Zcodegen-backend=cranelift* || "$$flag" == -Zthreads=8* || "$$flag" == -Clink-arg=-fuse-ld=mold ]]; then bad=$$flag; fi; if [[ "$$flag" == -Clinker=evert-clang-mold || "$$flag" == -Clinker=*/evert-clang-mold || "$$flag" == -Clinker=ld.mold || "$$flag" == -Clinker=*/ld.mold ]]; then bad=$$flag; fi; if [[ "$$previous:$$flag" == -Z:codegen-backend=cranelift* || "$$previous:$$flag" == -Z:codegen-backend || "$$previous:$$flag" == -Z:codegen-backend= || "$$previous:$$flag" == -Z:threads=8* || "$$previous:$$flag" == -Z:threads || "$$previous:$$flag" == -Z:threads= || "$$previous:$$flag" == -Zcodegen-backend:cranelift* || "$$previous:$$flag" == -Zthreads:8* ]]; then bad="$$previous $$flag"; fi; if [[ "$$previous:$$flag" == -C:linker=evert-clang-mold || "$$previous:$$flag" == -C:linker=*/evert-clang-mold || "$$previous:$$flag" == -C:linker=ld.mold || "$$previous:$$flag" == -C:linker=*/ld.mold || "$$previous:$$flag" == -Clinker:evert-clang-mold || "$$previous:$$flag" == -Clinker:*/evert-clang-mold || "$$previous:$$flag" == -Clinker:ld.mold || "$$previous:$$flag" == -Clinker:*/ld.mold ]]; then bad="$$previous $$flag"; fi; if [[ "$$previous:$$flag" == -C:link-arg=-fuse-ld=mold || "$$previous:$$flag" == -Clink-arg:-fuse-ld=mold ]]; then bad="$$previous $$flag"; fi; if [[ -n "$$bad" ]]; then printf "explicit non-native Cargo route rejects incompatible flag from inherited RUSTFLAGS or Make RUST_FLAGS: %s\n" "$$bad" >&2; exit 2; fi; previous=$$flag; done; exec env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS="$$effective_flags" "$$@"' _ '$(subst ','"'"',$(RUST_FLAGS))')
endef
GATE_RUSTFLAGS = $(call gate_rustflags_with,$(CARGO_FLAGS_STANDARD_RUSTFLAGS))
TEST_GATE_RUSTFLAGS = $(call gate_rustflags_with,$(TEST_FLAGS_STANDARD_RUSTFLAGS))
BASE_GATE_RUSTFLAGS = $(call gate_rustflags_with,$(STANDARD_RUSTFLAGS))
CLIPPY_GATE_RUSTFLAGS = $(call gate_rustflags_with,$(CLIPPY_FLAGS_STANDARD_RUSTFLAGS))
# Only the selected Linux ELF host requires the runner's action-managed linker.
# Other CI hosts keep their platform toolchain and must parse Make normally.
ifeq ($(GITHUB_ACTIONS)-$(BUILD_HOST_OS)-$(BUILD_HOST_ARCH),true-Linux-x86_64)
BUILD_TOOLS_PREFIX ?= $(shell \
	linker=$$(command -v ld.mold 2>/dev/null); \
	prefix=$${linker%/bin/ld.mold}; \
	if [[ -n "$$RUNNER_TOOL_CACHE" && "$$linker" == "$$RUNNER_TOOL_CACHE"/mold/*/x86_64/bin/ld.mold ]]; then \
		printf '%s' "$$prefix"; \
	fi)
ifeq ($(strip $(BUILD_TOOLS_PREFIX)),)
$(error GITHUB_ACTIONS=true but setup-rust must put its verified linker on PATH before Make runs)
endif
else
BUILD_TOOLS_PREFIX ?= $(HOME)/.local
endif
export BUILD_TOOLS_PREFIX
export PATH := $(BUILD_TOOLS_PREFIX)/bin:$(PATH)
RELEASE_RUSTFLAGS = env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS=""
COVERAGE_ENV = env -u CARGO_ENCODED_RUSTFLAGS

build: target/debug/$(TARGET) ## Build debug binary
release: target/release/$(TARGET) ## Build release binary

all: check-fmt lint test spelling test-workflow-contracts ## Perform a comprehensive check of code

clean: ## Remove build artefacts
	$(CARGO) clean

test: check-build-tools ## Run tests with warnings treated as errors
	$(TEST_GATE_RUSTFLAGS) $(CARGO) $(TEST_CMD) $(TEST_FLAGS) $(BUILD_JOBS)
	$(BASE_GATE_RUSTFLAGS) $(CARGO) test --doc --workspace --all-features $(BUILD_JOBS)

test-workflow-contracts: ## Validate the shared and local workflow contracts
	$(CV005_CONTRACTS) check --repository .
	$(UV_ENV) $(UV) run --no-project --python $(PYTHON_BASELINE) --with 'pytest>=8' --with 'pyyaml>=6' pytest tests/workflow_contracts -q

target/debug/$(TARGET): | check-build-tools ## Build the development binary
	$(BASE_GATE_RUSTFLAGS) $(CARGO) build $(BUILD_JOBS) --bin $(TARGET)

target/release/$(TARGET): ## Build the release binary with stable Rust and LLVM
	$(RELEASE_RUSTFLAGS) $(CARGO) +stable build $(BUILD_JOBS) --release --bin $(TARGET)

coverage: ## Generate lcov coverage with lld for llvm-tools compatibility
	@echo "coverage linker flags: $(COVERAGE_LINKER_FLAGS)"
	$(COVERAGE_ENV) CARGO_TARGET_X86_64_UNKNOWN_LINUX_GNU_LINKER=clang \
		RUSTFLAGS="$(COVERAGE_RUST_FLAGS)" \
		CFLAGS="$(COVERAGE_LINKER_FLAGS)" \
		LDFLAGS="$(COVERAGE_LINKER_FLAGS)" \
		$(CARGO) llvm-cov --lcov --output-path lcov.info $(TEST_FLAGS)

lint: lint-clippy lint-whitaker lint-python ## Run rustdoc, Clippy, Whitaker, and the Python linters with warnings denied

# Keep Whitaker on the Clippy route's explicit prerequisite edge so `make -j`
# cannot overlap the two compiler gates.
lint-whitaker: lint-clippy
	env -u CARGO_ENCODED_RUSTFLAGS RUSTFLAGS="-D warnings" $(WHITAKER) $(WHITAKER_PACKAGES) -- $(CARGO_FLAGS)

# Python lints run last, after the Rust compiler gates, and need no Rust
# toolchain. Every command receives the same source roots so Ruff, Pylint, the
# df12 house lints, ambrleaks, and Interrogate judge one boundary.
lint-python: ## Run Ruff, Pylint, the df12 house lints, ambrleaks, and Interrogate over the Python sources
	@if [ -z "$(PYTHON_SOURCES)" ]; then \
		echo "lint-python: no Python sources under $(PYTHON_SOURCE_ROOTS)"; \
	else \
		set -e; \
		$(RUFF) check $(PYTHON_SOURCES); \
		$(PYLINT) $(PYTHON_SOURCES); \
		$(DF12_PYLINT) $(PYTHON_SOURCES); \
		$(AMBRLEAKS) $(PYTHON_SOURCES); \
		$(INTERROGATE) $(PYTHON_SOURCES); \
	fi

lint-clippy: check-build-tools ## Run rustdoc and Clippy with the development flags
	$(BASE_GATE_RUSTFLAGS) RUSTDOCFLAGS="$(RUSTDOC_FLAGS)" $(CARGO) doc --no-deps
	$(CLIPPY_GATE_RUSTFLAGS) $(CARGO) clippy $(CLIPPY_FLAGS)

# `make typecheck` is the one type gate CI needs. The build-tools preflight
# comes first, so a missing pinned tool stops the gate before any type check
# runs, exactly as it did when `typecheck` was Rust only.
typecheck: check-build-tools typecheck-python typecheck-rust ## Type-check the Python and Rust sources without building

typecheck-rust: check-build-tools ## Type-check the Rust sources without building
	$(GATE_RUSTFLAGS) $(CARGO) check $(CARGO_FLAGS)

# The Python half takes the same source roots as the lint gateway, so a Python
# file cannot be linted but left untyped.
typecheck-python: ## Typecheck the Python sources with ty
	@if [ -z "$(PYTHON_SOURCES)" ]; then \
		echo "typecheck-python: no Python sources under $(PYTHON_SOURCE_ROOTS)"; \
	else \
		$(UV_ENV) $(UV) tool run --python $(PYTHON_BASELINE) \
			--from ty==$(TY_VERSION) $(TY_DEPENDENCIES) \
			ty check --python-version $(PYTHON_BASELINE) \
			$(PYTHON_IMPORT_ROOTS) $(PYTHON_SOURCES); \
	fi

fmt: ## Format Rust and Markdown sources
	$(CARGO) fmt --all
	$(MDTABLEFIX) --in-place $(MDTABLEFIX_SELECT) $(MDTABLEFIX_RULES)
	$(MDLINT) --fix "**/*.md"

check-fmt: ## Verify formatting
	$(CARGO) fmt --all -- --check
	$(MDTABLEFIX) --check $(MDTABLEFIX_SELECT) $(MDTABLEFIX_RULES)

markdownlint: spelling ## Lint Markdown files and enforce repository spelling
	$(MDLINT) '**/*.md'

spelling: ## Enforce en-GB-oxendict spelling across tracked files
	$(TYPOS_CONFIG_BUILDER) gate --repository . --scope all

nixie: ## Validate Mermaid diagrams
	$(NIXIE) --no-sandbox

audit: rust-audit ## Audit dependencies for known vulnerabilities

rust-audit: ## Audit the Rust workspace for known vulnerabilities
	set -eo pipefail; \
	manifest_list=$$(mktemp); \
	trap 'rm -f "$$manifest_list"' EXIT; \
	printf "Audit metadata phase: deriving workspace manifests\n"; \
	$(CARGO) metadata --no-deps --format-version 1 | python3 -c 'import json, sys; metadata = json.load(sys.stdin); members = set(metadata["workspace_members"]); print(metadata["workspace_root"]); [print(package["manifest_path"]) for package in metadata["packages"] if package["id"] in members]' > "$$manifest_list"; \
	workspace_root=$$(sed -n '1p' "$$manifest_list"); \
	audit_flags=(); \
	for advisory in $$CARGO_AUDIT_IGNORES; do \
		audit_flags+=(--ignore "$$advisory"); \
	done; \
	printf "Auditing Rust workspace %s\n" "$$workspace_root"; \
	sed -n '2,$$p' "$$manifest_list" | while IFS= read -r manifest; do \
		manifest_dir=$$(dirname "$$manifest"); \
		printf "Workspace Rust manifest %s\n" "$$manifest_dir/Cargo.toml"; \
	done; \
	printf "Audit execution phase: running cargo audit\n"; \
	printf "Audit failures may indicate RustSec advisories, cargo metadata errors, or documented ignores that need CARGO_AUDIT_IGNORES entries.\n"; \
	(cd "$$workspace_root" && $(CARGO) audit "$${audit_flags[@]}")

help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?##' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS=":"; printf "Available targets:\n"} {printf "  %-20s %s\n", $$1, $$2}'

install-build-tools: ## Install the pinned nightly and linker binary
	@scripts/install-build-tools.sh

check-build-tools: ## Check the development compiler and linker prerequisites
	@scripts/check-build-tools.sh
