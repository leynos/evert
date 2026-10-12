//! Checks the generated application's observable command-line output.

use std::process::Command;

#[test]
fn application_prints_its_greeting_to_standard_output() {
    let output = Command::new(env!("CARGO_BIN_EXE_evert"))
        .output()
        .expect("running the Evert application");

    assert!(
        output.status.success(),
        "application failed: {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert_eq!(output.stdout, b"Hello from Evert!\n");
    assert!(
        output.stderr.is_empty(),
        "unexpected standard error: {}",
        String::from_utf8_lossy(&output.stderr)
    );
}
