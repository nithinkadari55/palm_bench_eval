// krilla 0.7.0 adapter. Every item used here was checked against the krilla-0.7.0 crate source.
use krilla::configure::{Configuration, PdfVersion, Validator};
use krilla::error::KrillaError;
use krilla::icc::ICCProfile;
use krilla::tagging::{ArtifactType, ContentTag};
use krilla::SerializeSettings;

use crate::common::Art;

pub const KRILLA_VERSION: &str = "0.7.0";

pub struct Profile {
    pub id: &'static str,
    pub verapdf: &'static [&'static str],
}

pub const PROFILES: &[Profile] = &[
    Profile { id: "none", verapdf: &[] },
    Profile { id: "pdf20", verapdf: &[] },
    Profile { id: "a1a", verapdf: &["1a"] },
    Profile { id: "a1b", verapdf: &["1b"] },
    Profile { id: "a2a", verapdf: &["2a"] },
    Profile { id: "a2b", verapdf: &["2b"] },
    Profile { id: "a2u", verapdf: &["2u"] },
    Profile { id: "a3a", verapdf: &["3a"] },
    Profile { id: "a3b", verapdf: &["3b"] },
    Profile { id: "a3u", verapdf: &["3u"] },
    Profile { id: "a4", verapdf: &["4"] },
    Profile { id: "a4f", verapdf: &["4f"] },
    Profile { id: "a4e", verapdf: &["4e"] },
    Profile { id: "ua1", verapdf: &["ua1"] },
];

pub const NOT_OFFERED: &[&str] = &["ua2", "a1a+ua1", "a2a+ua1", "a3a+ua1"];

fn configuration(id: &str) -> Result<Configuration, String> {
    let v = match id {
        "none" => return Ok(Configuration::new()),
        "pdf20" => return Ok(Configuration::new_with_version(PdfVersion::Pdf20)),
        "a1a" => Validator::A1_A,
        "a1b" => Validator::A1_B,
        "a2a" => Validator::A2_A,
        "a2b" => Validator::A2_B,
        "a2u" => Validator::A2_U,
        "a3a" => Validator::A3_A,
        "a3b" => Validator::A3_B,
        "a3u" => Validator::A3_U,
        "a4" => Validator::A4,
        "a4f" => Validator::A4F,
        "a4e" => Validator::A4E,
        "ua1" => Validator::UA1,
        _ => return Err(format!("profile {id} is not offered by krilla {KRILLA_VERSION}")),
    };
    Ok(Configuration::new_with_validator(v))
}

pub fn settings(id: &str, cmyk: Option<ICCProfile<4>>) -> Result<SerializeSettings, String> {
    let configuration = configuration(id)?;
    Ok(SerializeSettings {
        configuration,
        cmyk_profile: cmyk,
        ..Default::default()
    })
}

pub fn version_str(s: &SerializeSettings) -> &'static str {
    s.configuration.version().as_str()
}

pub fn validators_str(s: &SerializeSettings) -> String {
    s.configuration.validator().as_str().to_string()
}

pub fn artifact(kind: Art) -> ContentTag<'static> {
    ContentTag::Artifact(match kind {
        Art::Header => ArtifactType::Header,
        Art::Footer => ArtifactType::Footer,
        Art::Page => ArtifactType::Page,
        Art::Other => ArtifactType::Other,
    })
}

pub fn describe(e: &KrillaError) -> (String, Vec<String>) {
    match e {
        KrillaError::Validation(v) => (
            "Validation".to_string(),
            v.iter().map(|x| format!("{x:?}")).collect(),
        ),
        other => {
            let s = format!("{other:?}");
            (crate::common::variant_name(&s), vec![s])
        }
    }
}
