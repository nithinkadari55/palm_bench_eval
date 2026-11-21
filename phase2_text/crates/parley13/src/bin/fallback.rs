use fontique::{Collection, CollectionOptions, FallbackKey, FamilyId, GenericFamily, Language, Script, SourceCache};
use p2_parley13::{is_default_ignorable, load_corpus};
use serde_json::{json, Value};
use skrifa::{FontRef, MetadataProvider};
use std::collections::BTreeMap;

const MAX_FAILURES: usize = 20;

struct LoadedFamily {
    name: String,
    blob: fontique::Blob<u8>,
    index: u32,
    path_hint: String,
}

fn load_family(coll: &mut Collection, cache: &mut SourceCache, id: FamilyId) -> Option<LoadedFamily> {
    let fam = coll.family(id)?;
    let font = fam.default_font()?;
    let blob = font.load(Some(cache))?;
    let path_hint = match font.source().kind() {
        fontique::SourceKind::Path(p) => p.display().to_string(),
        fontique::SourceKind::Memory(_) => "<memory>".to_string(),
    };
    Some(LoadedFamily { name: fam.name().to_string(), blob, index: font.index(), path_hint })
}

fn main() {
    let args: Vec<String> = std::env::args().collect();
    if args.len() != 3 {
        eprintln!("usage: fallback <corpus.json> <results.json>");
        std::process::exit(2);
    }
    let corpus = load_corpus(&args[1]);
    let mut coll = Collection::new(CollectionOptions { shared: false, system_fonts: true });
    let mut cache = SourceCache::default();
    let family_count = coll.family_names().count();

    let (mut pass, mut fail) = (0u64, 0u64);
    let mut per_entry = Vec::new();
    let mut failures = Vec::new();
    let mut overall_occ = (0u64, 0u64, 0u64);

    for e in &corpus {
        let lang = Language::parse(&e.lang).ok();
        let mut chain_ids: Vec<(FamilyId, &'static str)> = Vec::new();
        if e.kind == "emoji" {
            for id in coll.generic_families(GenericFamily::Emoji).collect::<Vec<_>>() {
                chain_ids.push((id, "generic:emoji"));
            }
        } else {
            let b = e.script.as_bytes();
            let script = Script::from_bytes([b[0], b[1], b[2], b[3]]);
            let key = FallbackKey::new(script, lang.as_ref());
            for id in coll.fallback_families(key).collect::<Vec<_>>() {
                chain_ids.push((id, "fallback"));
            }
        }
        let script_chain_len = chain_ids.len();
        for id in coll.generic_families(GenericFamily::SansSerif).collect::<Vec<_>>() {
            if !chain_ids.iter().any(|(x, _)| *x == id) {
                chain_ids.push((id, "generic:sans-serif"));
            }
        }
        let loaded: Vec<(LoadedFamily, &str)> = chain_ids
            .iter()
            .filter_map(|(id, role)| load_family(&mut coll, &mut cache, *id).map(|l| (l, *role)))
            .collect();
        let fonts: Vec<(usize, Option<FontRef<'_>>)> = loaded
            .iter()
            .enumerate()
            .map(|(i, (l, _))| (i, FontRef::from_index(l.blob.data(), l.index).ok()))
            .collect();
        let charmaps: Vec<(usize, skrifa::charmap::Charmap<'_>)> =
            fonts.iter().filter_map(|(i, f)| f.as_ref().map(|f| (*i, f.charmap()))).collect();

        let mut counts: BTreeMap<char, u64> = BTreeMap::new();
        for line in &e.lines {
            for c in line.chars() {
                *counts.entry(c).or_default() += 1;
            }
        }
        let (mut occ, mut occ_script, mut occ_chain) = (0u64, 0u64, 0u64);
        let (mut uniq, mut uniq_ok) = (0u64, 0u64);
        let mut uncovered = Vec::new();
        let mut ignorable_unmapped = Vec::new();
        let mut used_fonts: BTreeMap<String, u64> = BTreeMap::new();
        for (&c, &n) in &counts {
            let first = charmaps.iter().find(|(_, cm)| cm.map(c).is_some()).map(|(i, _)| *i);
            if is_default_ignorable(c) || c.is_control() {
                if first.is_none() {
                    ignorable_unmapped.push(format!("U+{:04X}", c as u32));
                }
                continue;
            }
            uniq += 1;
            occ += n;
            match first {
                Some(i) => {
                    uniq_ok += 1;
                    occ_chain += n;
                    if i < script_chain_len {
                        occ_script += n;
                    }
                    *used_fonts.entry(loaded[i].0.name.clone()).or_default() += n;
                }
                None => uncovered.push(json!({"cp": format!("U+{:04X}", c as u32), "char": c.to_string(), "count": n})),
            }
        }
        pass += uniq_ok;
        fail += uniq - uniq_ok;
        overall_occ.0 += occ;
        overall_occ.1 += occ_script;
        overall_occ.2 += occ_chain;
        if !uncovered.is_empty() && failures.len() < MAX_FAILURES {
            failures.push(json!({"entry": e.id, "script": e.script, "lang": e.lang, "uncovered": uncovered.iter().take(30).collect::<Vec<_>>()}));
        }
        let pct = |a: u64, b: u64| if b > 0 { 100.0 * a as f64 / b as f64 } else { 100.0 };
        per_entry.push(json!({
            "entry": e.id,
            "group": e.group,
            "script": e.script,
            "lang": e.lang,
            "chain": loaded.iter().map(|(l, role)| json!({"family": l.name, "role": role, "file": l.path_hint, "index": l.index})).collect::<Vec<_>>(),
            "chars": occ,
            "unique_chars": uniq,
            "coverage_pct_script_fallback_only": pct(occ_script, occ),
            "coverage_pct_full_chain": pct(occ_chain, occ),
            "unique_coverage_pct_full_chain": pct(uniq_ok, uniq),
            "uncovered": uncovered,
            "default_ignorable_unmapped": ignorable_unmapped,
            "chars_per_font": used_fonts,
        }));
        println!("{}: {:.2}% ({} uncovered unique)", e.id, pct(occ_chain, occ), uniq - uniq_ok);
    }
    let total = pass + fail;
    let result: Value = json!({
        "test": "fallback",
        "fontique_version": "0.13.0",
        "skrifa_version": "0.50.0",
        "system_family_count": family_count,
        "pass": pass,
        "fail": fail,
        "total": total,
        "pass_rate": if total > 0 { pass as f64 / total as f64 } else { 0.0 },
        "pass_criterion": "each distinct non-ignorable character of a sample is mapped (skrifa charmap) by some font of the chain: fontique fallback family for (script, language) [generic emoji family for the emoji sample], then the generic sans-serif families; counts are (sample, distinct character) pairs",
        "coverage_pct_overall_occurrences": if overall_occ.0 > 0 { 100.0 * overall_occ.2 as f64 / overall_occ.0 as f64 } else { 0.0 },
        "coverage_pct_script_fallback_only_occurrences": if overall_occ.0 > 0 { 100.0 * overall_occ.1 as f64 / overall_occ.0 as f64 } else { 0.0 },
        "notes": [
            "The fontconfig backend of fontique returns at most one fallback family per (script, locale) key; each family is checked through its default font.",
            "Default_Ignorable_Code_Point characters (ZWJ, variation selectors, ...) and controls are not required to be in a cmap; they are listed under default_ignorable_unmapped."
        ],
        "entries": per_entry,
        "first_failures": failures,
    });
    std::fs::write(&args[2], serde_json::to_string_pretty(&result).unwrap()).expect("write results");
}
