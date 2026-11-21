use serde_json::Value;

pub struct Entry {
    pub id: String,
    pub group: String,
    pub lang: String,
    pub script: String,
    pub direction: String,
    pub kind: String,
    pub lines: Vec<String>,
}

pub fn load_corpus(path: &str) -> Vec<Entry> {
    let v: Value = serde_json::from_str(&std::fs::read_to_string(path).expect("read corpus")).expect("parse corpus");
    let s = |e: &Value, k: &str| e[k].as_str().unwrap_or("").to_string();
    v["entries"]
        .as_array()
        .cloned()
        .unwrap_or_default()
        .iter()
        .map(|e| Entry {
            id: s(e, "id"),
            group: s(e, "group"),
            lang: s(e, "lang"),
            script: s(e, "script"),
            direction: s(e, "direction"),
            kind: s(e, "kind"),
            lines: e["lines"]
                .as_array()
                .map(|a| a.iter().filter_map(|x| x.as_str().map(str::to_string)).collect())
                .unwrap_or_default(),
        })
        .collect()
}

pub fn is_default_ignorable(c: char) -> bool {
    matches!(c as u32,
        0x00AD | 0x034F | 0x061C | 0x115F | 0x1160 | 0x17B4 | 0x17B5 | 0x180B..=0x180F
        | 0x200B..=0x200F | 0x202A..=0x202E | 0x2060..=0x206F | 0x3164 | 0xFE00..=0xFE0F
        | 0xFEFF | 0xFFA0 | 0xFFF0..=0xFFF8 | 0x1BCA0..=0x1BCA3 | 0x1D173..=0x1D17A
        | 0xE0000..=0xE0FFF)
}
