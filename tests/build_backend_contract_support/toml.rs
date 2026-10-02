//! Small TOML readers used by the Cargo build configuration contract.

/// Strips a trailing comment while preserving hashes inside quoted values.
pub(super) fn strip_toml_comment(line: &str) -> &str {
    let mut quote = None;
    let mut escaped = false;
    for (index, character) in line.char_indices() {
        if character == '#' && quote.is_none() {
            return line.get(..index).unwrap_or(line);
        }
        (quote, escaped) = advance_quoted_state(quote, escaped, character);
    }
    line
}

/// Advances the quote and escape state for one TOML character.
///
/// ```text
/// advance_quoted_state(None, false, '"') -> (Some('"'), false)
/// advance_quoted_state(Some('"'), false, '\\') -> (Some('"'), true)
/// ```
const fn advance_quoted_state(
    quote: Option<char>,
    escaped: bool,
    character: char,
) -> (Option<char>, bool) {
    match (quote, escaped, character) {
        (Some('"'), true, _) => (quote, false),
        (Some('"'), false, '\\') => (quote, true),
        (Some(delimiter), _, current) if delimiter == current => (None, false),
        (None, _, '"' | '\'') => (Some(character), false),
        _ => (quote, escaped),
    }
}

/// Splits a TOML configuration into named table bodies, excluding comments.
pub(super) fn table_bodies(config: &str) -> Vec<(String, String)> {
    let mut current_table = None;
    let mut current_body = String::new();
    let mut tables = Vec::new();
    for raw_line in config.lines() {
        let line = strip_toml_comment(raw_line).trim();
        if let Some(table_name) = table_header(line) {
            if let Some(table) = current_table.replace(table_name.to_owned()) {
                tables.push((table, std::mem::take(&mut current_body)));
            }
        } else if current_table.is_some() && !line.is_empty() {
            current_body.push_str(line);
            current_body.push('\n');
        }
    }
    if let Some(table) = current_table {
        tables.push((table, current_body));
    }
    tables
}

/// Returns the untrimmed name inside a single-bracket TOML table header.
///
/// ```text
/// table_header("[build]") -> Some("build")
/// table_header("[[bin]]") -> Some("[bin]")
/// ```
fn table_header(line: &str) -> Option<&str> { line.strip_prefix('[')?.strip_suffix(']') }

/// Returns the body of a TOML table when it declares `rustflags`.
fn rustflags_body(config: &str, table: &str) -> Option<String> {
    table_bodies(config)
        .into_iter()
        .find(|(name, body)| {
            name == table && body.lines().any(|line| line.starts_with("rustflags"))
        })
        .map(|(_, body)| body)
}

/// Checks that a table's `rustflags` setting carries every required flag.
pub(super) fn rustflags_include(config: &str, table: &str, required: &[&str]) -> bool {
    let Some(body) = rustflags_body(config, table) else {
        return false;
    };
    required.iter().all(|flag| body.contains(flag))
}

/// Lists TOML tables whose `rustflags` setting selects `flag`.
pub(super) fn tables_with_rustflag(config: &str, flag: &str) -> Vec<String> {
    table_bodies(config)
        .into_iter()
        .filter(|(_, body)| {
            body.lines().any(|line| line.starts_with("rustflags")) && body.contains(flag)
        })
        .map(|(table, _)| table)
        .collect()
}
