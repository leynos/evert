//! `Evert` library support for the application crate.

// TODO: Replace this stub when application logic moves behind the executable.
/// Returns the generated application greeting.
///
/// # Examples
///
/// ```
/// use evert::greet;
///
/// assert_eq!(greet(), "Hello from Evert!");
/// ```
#[must_use]
pub const fn greet() -> &'static str { "Hello from Evert!" }
