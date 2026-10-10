//! Regression cases for hashes inside TOML strings and backend values.

use super::toml::table_bodies;

/// Comments do not begin inside quoted inline-table values, even after an escaped quote.
#[test]
fn toml_comment_stripping_preserves_quoted_hashes() {
    let input = r##"[build]
flags = { rustflags = ["path#name", "escaped \"# quote"] } # actual comment
"##;
    let tables = table_bodies(input);
    let expected = r##"flags = { rustflags = ["path#name", "escaped \"# quote"] }
"##;
    assert_eq!(tables, vec![("build".to_owned(), expected.to_owned())]);
}

/// Table extraction keeps source order, body boundaries and prelude handling.
#[test]
fn table_reader_flushes_each_table_in_order() {
    let tables = table_bodies("ignored = true\n[first]\none = 1\n[[second]]\ntwo = 2\n");
    assert_eq!(
        tables,
        vec![
            ("first".to_owned(), "one = 1\n".to_owned()),
            ("[second]".to_owned(), "two = 2\n".to_owned()),
        ]
    );
}

/// A backend key with a quoted hash value remains detectable before a real comment.
#[test]
fn profile_backend_key_retains_quoted_hash() {
    let config = "[profile.dev]\ncodegen-backend = \"cranelift#nightly\" # obsolete\n";
    let profile_body = table_bodies(config)
        .into_iter()
        .find(|(name, _)| name == "profile.dev")
        .map(|(_, body)| body)
        .expect("profile table remains readable");
    let backend_key_value = profile_body.lines().find(|line| {
        line.split_once('=')
            .is_some_and(|(key, _)| key.trim() == "codegen-backend")
    });
    assert_eq!(
        backend_key_value,
        Some("codegen-backend = \"cranelift#nightly\"")
    );
}
