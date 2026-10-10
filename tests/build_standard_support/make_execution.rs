//! Process boundary for repository integration checks of Make's real targets.
//!
//! Parser fixtures call the readers with supplied text; only repository
//! integration checks use this module to obtain evaluated Make output.

use std::process::Command;

/// Runs `make -n` for one target and returns its stdout without parsing it.
pub fn run_make_dry_run(
    target: &str,
    build_host: &str,
    build_arch: &str,
) -> Result<String, String> {
    let output = Command::new("make")
        .args([
            "-n",
            "-B",
            &format!("BUILD_HOST_OS={build_host}"),
            &format!("BUILD_HOST_ARCH={build_arch}"),
            target,
        ])
        .current_dir(concat!(env!("CARGO_MANIFEST_DIR"), ""))
        .env("GITHUB_ACTIONS", "false")
        .output()
        .map_err(|error| format!("running make: {error}"))?;
    let stderr = String::from_utf8_lossy(&output.stderr);
    if !output.status.success() {
        return Err(format!(
            "`make -n {target}` failed, so it is not defined: {stderr}"
        ));
    }
    Ok(String::from_utf8_lossy(&output.stdout).into_owned())
}
