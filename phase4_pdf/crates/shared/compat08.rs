// krilla 0.8.2 adapter. Every item used here was checked against the krilla-0.8.2 crate source.
use krilla::configure::{Accessibility, Archival, Configuration, ConfigurationBuilder, PdfVersion};
use krilla::error::KrillaError;
use krilla::icc::ICCProfile;
use krilla::tagging::{Artifact, ArtifactType, ContentTag};
use krilla::SerializeSettings;

use crate::common::Art;

pub const KRILLA_VERSION: &str = "0.8.2";

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
    Profile { id: "a1a+ua1", verapdf: &["1a", "ua1"] },
    Profile { id: "a2a+ua1", verapdf: &["2a", "ua1"] },
    Profile { id: "a3a+ua1", verapdf: &["3a", "ua1"] },
];

pub const NOT_OFFERED: &[&str] = &["ua2"];

fn archival(id: &str) -> Option<Archival> {
    Some(match id {
        "a1a" => Archival::A1_A,
        "a1b" => Archival::A1_B,
        "a2a" => Archival::A2_A,
        "a2b" => Archival::A2_B,
        "a2u" => Archival::A2_U,
        "a3a" => Archival::A3_A,
        "a3b" => Archival::A3_B,
        "a3u" => Archival::A3_U,
        "a4" => Archival::A4,
        "a4f" => Archival::A4F,
        "a4e" => Archival::A4E,
        _ => return None,
    })
}

fn configuration(id: &str) -> Result<Configuration, String> {
    let mut b = ConfigurationBuilder::new();
    let mut known = false;
    for part in id.split('+') {
        if part == "none" {
            known = true;
        } else if part == "pdf20" {
            b = b.with_version(PdfVersion::Pdf20);
            known = true;
        } else if part == "ua1" {
            b = b.with_accessibility_validator(Accessibility::UA1);
            known = true;
        } else if let Some(a) = archival(part) {
            b = b.with_archival_validator(a);
            known = true;
        } else {
            return Err(format!("profile {id} is not offered by krilla {KRILLA_VERSION}"));
        }
    }
    if !known {
        return Err(format!("profile {id} is not offered by krilla {KRILLA_VERSION}"));
    }
    b.finish().map_err(|e| format!("ConfigurationError::{e:?}"))
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
    let v = s.configuration.validators();
    let names: Vec<&str> = v.into_iter().map(|x| x.as_str()).collect();
    if names.is_empty() {
        "None".to_string()
    } else {
        names.join("+")
    }
}

pub fn artifact(kind: Art) -> ContentTag<'static> {
    ContentTag::Artifact(Artifact::with_kind(match kind {
        Art::Header => ArtifactType::Header,
        Art::Footer => ArtifactType::Footer,
        Art::Page => ArtifactType::Page,
        Art::Other => ArtifactType::Other,
    }))
}

pub fn describe(e: &KrillaError) -> (String, Vec<String>) {
    match e {
        KrillaError::Validation(v) => (
            "Validation".to_string(),
            v.iter()
                .map(|(err, by)| {
                    let names: Vec<&str> = (*by).into_iter().map(|x| x.as_str()).collect();
                    format!("{err:?} [{}]", names.join("+"))
                })
                .collect(),
        ),
        other => {
            let s = format!("{other:?}");
            (crate::common::variant_name(&s), vec![s])
        }
    }
}
