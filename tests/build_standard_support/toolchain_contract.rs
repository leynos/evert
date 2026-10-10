//! Focused fixtures for malformed toolchain channel declarations.

use rstest::rstest;

use super::config::{Pin, PinError};

/// A channel string with no closing delimiter is malformed.
const UNTERMINATED_CHANNEL: &str = "[toolchain]\nchannel = \"nightly\n";
/// Trailing text after a closing quote is not a valid channel declaration.
const TRAILING_CHANNEL_TEXT: &str = "[toolchain]\nchannel = \"nightly\" unexpected\n";
/// A key with a channel prefix does not name the exact `channel` key.
const CHANNEL_LIKE_KEY: &str = "[toolchain]\nchannel-name = \"nightly\"\n";
/// A key with a channel suffix does not name the exact `channel` key.
const SUFFIX_CHANNEL_KEY: &str = "[toolchain]\ndefault-channel = \"stable\"\n";

/// The reader rejects malformed values and does not accept approximate keys.
#[rstest]
#[case::unterminated_quote(UNTERMINATED_CHANNEL, Err(PinError::MalformedChannel))]
#[case::trailing_text(TRAILING_CHANNEL_TEXT, Err(PinError::MalformedChannel))]
#[case::channel_prefix_is_missing(CHANNEL_LIKE_KEY, Err(PinError::MissingChannel))]
#[case::channel_suffix_is_missing(SUFFIX_CHANNEL_KEY, Err(PinError::MissingChannel))]
fn toolchain_reader_rejects_malformed_and_channel_like_entries(
    #[case] toolchain: &str,
    #[case] expected: Result<Pin, PinError>,
) {
    assert_eq!(Pin::read(toolchain), expected);
}
