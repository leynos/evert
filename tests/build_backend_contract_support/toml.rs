//! Small TOML readers used by the Cargo build configuration contract.

/// Strips a trailing comment while preserving hashes inside quoted values.
pub(super) fn strip_toml_comment(line: &str) -> &str {
    let mut quote = None;
    let mut escaped = false;
    for (index, character) in line.char_indices() {
        if character == '#' && quote.is_none() {
            return line.get(..index).unwrap_or(line);
        }
        match (quote, escaped, character) {
            (Some('"'), true, _) => escaped = false,
            (Some('"'), false, '\\') => escaped = true,
            (Some(delimiter), _, current) if delimiter == current => quote = None,
            (None, _, '"' | '\'') => quote = Some(character),
            _ => {}
        }
    }
    line
}

/// Splits a TOML configuration into named table bodies, excluding comments.
pub(super) fn table_bodies(config: &str) -> Vec<(String, String)> {
    let mut current_table = None;
    let mut current_body = String::new();
    let mut tables = Vec::new();
    for raw_line in config.lines() {
        let line = strip_toml_comment(raw_line).trim();
        if line.starts_with('[') && line.ends_with(']') {
            let Some(table_name) = line
                .strip_prefix('[')
                .and_then(|header| header.strip_suffix(']'))
            else {
                continue;
            };
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
