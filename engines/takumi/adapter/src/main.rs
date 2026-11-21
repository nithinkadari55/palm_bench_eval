use std::{
  collections::{HashMap, HashSet},
  error::Error,
  fs,
  path::{Path, PathBuf},
  process::ExitCode,
  sync::{Arc, Mutex},
};

use serde_json::{Value, json};
use takumi::{
  parse_html,
  prelude::{
    FontResource, FontSource, Fonts, FromHtmlOptions, GenericFamily, ImageSource,
    ImageSourceInput, Node, NodeKind, RenderNeeds, StyleSheet,
  },
};
use takumi_pdf::{
  MeasureOptions, PageMargins, PageOptions, PdfError, PdfOptions, UncoveredText,
  needs as pdf_needs, render as render_pdf,
};
use url::Url;

type Images = HashMap<Arc<str>, ImageSource>;
type SharedBytes = Arc<dyn AsRef<[u8]> + Send + Sync>;

const FONT_DIRS: [&str; 2] = ["/usr/share/fonts", "/usr/local/share/fonts"];

const GENERIC_FAMILIES: &[(GenericFamily, &[&str])] = &[
  (GenericFamily::SANS_SERIF, &["LiberationSans", "DejaVuSans"]),
  (GenericFamily::SERIF, &["LiberationSerif", "DejaVuSerif"]),
  (GenericFamily::MONOSPACE, &["DejaVuSansMono", "LiberationMono"]),
  (GenericFamily::EMOJI, &["NotoColorEmoji"]),
];

const MAX_FONT_ROUNDS: usize = 64;

const MAX_LOG_RECORDS: usize = 10_000;

struct Args {
  input: PathBuf,
  output: PathBuf,
  page_width: f32,
  page_height: f32,
  margin: f32,
  geometry: Option<PathBuf>,
  diagnostics: Option<PathBuf>,
}

struct Collector {
  records: Mutex<Vec<(String, String)>>,
}

impl Collector {
  fn take(&self) -> Vec<(String, String)> {
    self
      .records
      .lock()
      .map(|mut records| std::mem::take(&mut *records))
      .unwrap_or_default()
  }
}

impl log::Log for Collector {
  fn enabled(&self, metadata: &log::Metadata) -> bool {
    metadata.level() <= log::Level::Warn
  }

  fn log(&self, record: &log::Record) {
    if !self.enabled(record.metadata()) {
      return;
    }
    if let Ok(mut records) = self.records.lock()
      && records.len() < MAX_LOG_RECORDS
    {
      records.push((record.target().to_string(), record.args().to_string()));
    }
  }

  fn flush(&self) {}
}

static COLLECTOR: Collector = Collector {
  records: Mutex::new(Vec::new()),
};

fn main() -> ExitCode {
  let args = match parse_args() {
    Ok(args) => args,
    Err(message) => {
      eprintln!("error: {message}");
      return ExitCode::from(2);
    }
  };

  let _ = log::set_logger(&COLLECTOR).map(|()| log::set_max_level(log::LevelFilter::Warn));

  let mut warnings: Vec<(String, String)> = Vec::new();
  let result = run(&args, &mut warnings);
  let mut side_files_ok = true;

  if let Some(path) = &args.geometry
    && let Err(message) = write_json(path, &json!({ "unsupported": true }))
  {
    eprintln!("error: {message}");
    side_files_ok = false;
  }

  if let Some(path) = &args.diagnostics {
    warnings.extend(
      COLLECTOR
        .take()
        .into_iter()
        .map(|(target, message)| (format!("log:{target}"), message)),
    );

    let mut seen = HashSet::new();

    warnings.retain(|warning| seen.insert(warning.clone()));

    let list: Vec<Value> = warnings
      .iter()
      .map(|(kind, message)| json!({ "kind": kind, "message": message }))
      .collect();

    if let Err(message) = write_json(path, &json!({ "warnings": list })) {
      eprintln!("error: {message}");
      side_files_ok = false;
    }
  }

  match result {
    Ok(()) if side_files_ok => ExitCode::SUCCESS,
    Ok(()) => ExitCode::from(2),
    Err(error) => {
      eprintln!("error: {error}");
      ExitCode::from(2)
    }
  }
}

fn parse_args() -> Result<Args, String> {
  const USAGE: &str = "usage: adapter-takumi render <input.html> <output.pdf> --page-width-px <W> --page-height-px <H> --margin-px <M> [--geometry <geometry.json>] [--diagnostics <diag.json>]";

  let mut positional: Vec<String> = Vec::new();
  let mut page_width = None;
  let mut page_height = None;
  let mut margin = None;
  let mut geometry = None;
  let mut diagnostics = None;
  let mut iter = std::env::args().skip(1);

  while let Some(arg) = iter.next() {
    if !arg.starts_with("--") {
      positional.push(arg);
      continue;
    }

    let flag = &arg[2..];
    let (name, inline) = match flag.split_once('=') {
      Some((name, value)) => (name.to_string(), Some(value.to_string())),
      None => (flag.to_string(), None),
    };
    let value = match inline {
      Some(value) => value,
      None => iter
        .next()
        .ok_or_else(|| format!("--{name} needs a value. {USAGE}"))?,
    };

    match name.as_str() {
      "page-width-px" => page_width = Some(parse_px(&name, &value)?),
      "page-height-px" => page_height = Some(parse_px(&name, &value)?),
      "margin-px" => margin = Some(parse_px(&name, &value)?),
      "geometry" => geometry = Some(PathBuf::from(value)),
      "diagnostics" => diagnostics = Some(PathBuf::from(value)),
      _ => return Err(format!("unknown option --{name}. {USAGE}")),
    }
  }

  let [command, input, output]: [String; 3] =
    positional.try_into().map_err(|_| USAGE.to_string())?;

  if command != "render" {
    return Err(format!("unknown command `{command}`. {USAGE}"));
  }

  Ok(Args {
    input: PathBuf::from(input),
    output: PathBuf::from(output),
    page_width: page_width.ok_or_else(|| format!("--page-width-px is required. {USAGE}"))?,
    page_height: page_height.ok_or_else(|| format!("--page-height-px is required. {USAGE}"))?,
    margin: margin.ok_or_else(|| format!("--margin-px is required. {USAGE}"))?,
    geometry,
    diagnostics,
  })
}

fn parse_px(name: &str, value: &str) -> Result<f32, String> {
  value
    .trim()
    .parse::<f32>()
    .ok()
    .filter(|px| px.is_finite() && *px >= 0.0)
    .ok_or_else(|| format!("--{name} takes a non-negative number of CSS px, not `{value}`"))
}

fn run(args: &Args, warnings: &mut Vec<(String, String)>) -> Result<(), Box<dyn Error>> {
  let absolute = std::path::absolute(&args.input)?;
  let html =
    fs::read_to_string(&absolute).map_err(|error| format!("{}: {error}", absolute.display()))?;
  let location = Url::from_file_path(&absolute)
    .map_err(|()| format!("{} is not a local file", absolute.display()))?;

  let mut parsed = parse_html(&html, FromHtmlOptions::builder().document(true).build())?;
  let base = parsed
    .base_href
    .as_deref()
    .and_then(|href| location.join(href).ok())
    .unwrap_or_else(|| location.clone());

  let mut loader = stylesheet::StyleSheetLoader::default();

  for (css, style) in parsed.css.iter_mut().zip(&mut parsed.styles) {
    style.text = loader.rewrite(&style.text, &base);
    *css = style.css();
  }

  resolve_image_sources(&mut parsed.node, &base);

  let css = parsed.css_with_links(|link| {
    let url = base.join(&link.href).ok()?;

    loader.load(&url)
  });

  warnings.extend(
    loader
      .skipped
      .drain(..)
      .map(|message| ("stylesheet".to_string(), message)),
  );

  let node = parsed.node;
  let stylesheet = Arc::new(StyleSheet::parse_owned_list_loosy(css));
  let mut fonts = load_system_fonts(warnings)?;
  let page = PageOptions {
    width: args.page_width,
    height: args.page_height,
    margin: PageMargins::uniform(args.margin),
  };

  for _ in 0..MAX_FONT_ROUNDS {
    let font_files = needs_for(&fonts, &node, &stylesheet, &Images::new(), page)?.font_files;

    if font_files.is_empty() {
      break;
    }

    let mut failed = Vec::new();

    for written in font_files {
      let loaded = base
        .join(&written)
        .map_err(|error| format!("{written}: {error}"))
        .and_then(|url| read_url(&url))
        .and_then(|bytes| {
          fonts
            .load_font_file(written.as_str(), FontSource::from(bytes))
            .map_err(|error| format!("{written}: {error}"))
        });

      if let Err(message) = loaded {
        warnings.push(("font-face".to_string(), message));
        failed.push(written);
      }
    }

    fonts = fonts.with_failed_font_files(&failed);
  }

  let needs = needs_for(&fonts, &node, &stylesheet, &Images::new(), page)?;
  let mut images = Images::new();

  for written in &needs.images {
    let decoded = base
      .join(written)
      .map_err(|error| format!("{written}: {error}"))
      .and_then(|url| read_url(&url))
      .and_then(|bytes| {
        ImageSource::from_bytes(&bytes).map_err(|error| format!("{written}: {error}"))
      });

    match decoded {
      Ok(image) => {
        images.insert(Arc::from(written.as_str()), image);
      }
      Err(message) => warnings.push(("image".to_string(), message)),
    }
  }

  for declaration in &needs.ignored_declarations {
    warnings.push((
      declaration.reason.as_str().to_string(),
      format!("{declaration} ({})", declaration.origin.as_str()),
    ));
  }

  for character in &needs.missing_characters {
    warnings.push((
      "missing-character".to_string(),
      format!(
        "no font draws {character} (U+{:04X}); it draws as the font's glyph 0",
        *character as u32
      ),
    ));
  }

  for family in &needs.unresolved_families {
    warnings.push((
      "unresolved-font-family".to_string(),
      format!("no face provides font-family {family:?}"),
    ));
  }

  let mut options = PdfOptions::builder()
    .fonts(&fonts)
    .node(node)
    .stylesheet(stylesheet)
    .images(images)
    .page(page)
    .build();

  options.uncovered_text = UncoveredText::Placeholder;

  let pdf = render_pdf(options)?;

  fs::write(&args.output, pdf).map_err(|error| format!("{}: {error}", args.output.display()))?;

  Ok(())
}

fn needs_for(
  fonts: &Fonts,
  node: &Node,
  stylesheet: &Arc<StyleSheet>,
  images: &Images,
  page: PageOptions,
) -> Result<RenderNeeds, PdfError> {
  pdf_needs(
    MeasureOptions::builder()
      .fonts(fonts)
      .node(node.clone())
      .stylesheet(Arc::clone(stylesheet))
      .images(images.clone())
      .page(page)
      .build(),
  )
}

fn load_system_fonts(warnings: &mut Vec<(String, String)>) -> Result<Fonts, Box<dyn Error>> {
  let mut paths = Vec::new();

  for dir in FONT_DIRS {
    collect_files(Path::new(dir), &mut paths, 0);
  }

  let mut paths: Vec<PathBuf> = paths
    .into_iter()
    .filter_map(|path| fs::canonicalize(path).ok())
    .collect();

  paths.sort();
  paths.dedup();

  let mut files: Vec<(u8, PathBuf, SharedBytes)> = Vec::new();

  for path in paths {
    let Ok(bytes) = fs::read(&path) else {
      continue;
    };

    if !is_sfnt(&bytes) {
      continue;
    }

    let shared: SharedBytes = Arc::new(bytes);

    files.push((install_rank(&path), path, shared));
  }

  files.sort_by(|a, b| (a.0, &a.1).cmp(&(b.0, &b.1)));

  if files.is_empty() {
    warnings.push((
      "font".to_string(),
      format!("no TrueType/OpenType font found under {}", FONT_DIRS.join(", ")),
    ));
  }

  let mut fonts = Fonts::with_system_fonts(
    files
      .iter()
      .map(|(_, _, data)| FontResource::new(FontSource::from_shared(Arc::clone(data)))),
  )?;

  for (generic, stems) in GENERIC_FAMILIES {
    let chosen = stems.iter().find_map(|stem| {
      let matched: Vec<&SharedBytes> = files
        .iter()
        .filter(|(_, path, _)| stem_matches(path, stem))
        .map(|(_, _, data)| data)
        .collect();

      (!matched.is_empty()).then_some(matched)
    });
    let Some(chosen) = chosen else {
      warnings.push((
        "font".to_string(),
        format!("no system font found for generic family {generic:?}"),
      ));
      continue;
    };

    for data in chosen {
      let resource = FontResource::new(FontSource::from_shared(Arc::clone(data)));

      if let Err(error) = fonts.register(resource.generic_family(*generic)) {
        warnings.push((
          "font".to_string(),
          format!("registering a font for {generic:?} failed: {error}"),
        ));
      }
    }
  }

  Ok(fonts)
}

fn collect_files(dir: &Path, out: &mut Vec<PathBuf>, depth: usize) {
  if depth > 16 {
    return;
  }

  let Ok(entries) = fs::read_dir(dir) else {
    return;
  };

  for entry in entries.flatten() {
    let path = entry.path();
    let Ok(file_type) = entry.file_type() else {
      continue;
    };

    if file_type.is_dir() {
      collect_files(&path, out, depth + 1);
    } else if file_type.is_file() || (file_type.is_symlink() && path.is_file()) {
      out.push(path);
    }
  }
}

fn is_sfnt(bytes: &[u8]) -> bool {
  let magic = bytes.get(..4);

  magic == Some(&[0u8, 1, 0, 0][..]) || magic == Some(&b"OTTO"[..]) || magic == Some(&b"ttcf"[..])
}

fn install_rank(path: &Path) -> u8 {
  let name = path
    .file_name()
    .and_then(|name| name.to_str())
    .unwrap_or_default()
    .to_ascii_lowercase();

  if name.starts_with("dejavu") {
    0
  } else if name.starts_with("liberation") {
    1
  } else if name.starts_with("notosans-")
    || name.starts_with("notoserif-")
    || name.starts_with("notosansmono-")
  {
    2
  } else if name.starts_with("notosanscjk") || name.starts_with("notoserifcjk") {
    3
  } else if name.starts_with("notocoloremoji") {
    4
  } else {
    5
  }
}

fn stem_matches(path: &Path, stem: &str) -> bool {
  path
    .file_stem()
    .and_then(|name| name.to_str())
    .is_some_and(|name| {
      name == stem
        || name
          .strip_prefix(stem)
          .is_some_and(|rest| rest.starts_with('-'))
    })
}

fn read_url(url: &Url) -> Result<Vec<u8>, String> {
  if url.scheme() != "file" {
    return Err(format!("{url}: only local file: URLs are read"));
  }

  let path = url
    .to_file_path()
    .map_err(|()| format!("{url}: not a local file path"))?;

  fs::read(&path).map_err(|error| format!("{url}: {error}"))
}

fn resolve_image_sources(node: &mut Node, base: &Url) {
  match &mut node.kind {
    NodeKind::Container { children } => {
      for child in children {
        resolve_image_sources(child, base);
      }
    }
    NodeKind::Image(image) => {
      if let ImageSourceInput::Url(src) = &mut image.src
        && !src.starts_with("data:")
        && let Ok(url) = base.join(src)
      {
        *src = Arc::from(url.as_str());
      }
    }
    _ => {}
  }
}

fn write_json(path: &Path, value: &Value) -> Result<(), String> {
  let text = serde_json::to_string(value).map_err(|error| error.to_string())?;

  fs::write(path, text).map_err(|error| format!("{}: {error}", path.display()))
}

mod stylesheet {
  use std::fmt::Write;

  use cssparser::{
    Delimiter, EncodingSupport, ParseError, Parser, ToCss, Token, serialize_string,
    stylesheet_encoding,
  };
  use encoding_rs::{Encoding, UTF_16BE, UTF_16LE, UTF_8};
  use url::{Position, Url};

  use crate::read_url;

  const MAX_IMPORT_DEPTH: usize = 16;

  #[derive(Default)]
  pub(crate) struct StyleSheetLoader {
    pub(crate) skipped: Vec<String>,
  }

  impl StyleSheetLoader {
    pub(crate) fn load(&mut self, url: &Url) -> Option<String> {
      self.load_nested(url, UTF_8, &mut Vec::new())
    }

    pub(crate) fn rewrite(&mut self, css: &str, base: &Url) -> String {
      self.rewrite_nested(css, base, UTF_8, &mut Vec::new())
    }

    fn load_nested(
      &mut self,
      url: &Url,
      environment: &'static Encoding,
      importing: &mut Vec<Url>,
    ) -> Option<String> {
      if importing
        .iter()
        .any(|sheet| same_ignoring_fragment(sheet, url))
      {
        return Some(String::new());
      }

      if importing.len() >= MAX_IMPORT_DEPTH {
        self
          .skipped
          .push(format!("{url}: @import nested deeper than {MAX_IMPORT_DEPTH}"));
        return Some(String::new());
      }

      let bytes = match read_url(url) {
        Ok(bytes) => bytes,
        Err(message) => {
          self.skipped.push(message);
          return None;
        }
      };

      let encoding = stylesheet_encoding::<EncodingRs>(&bytes, None, Some(environment));
      let (text, _, _) = encoding.decode(&bytes);

      importing.push(url.clone());
      let css = self.rewrite_nested(&text, url, encoding, importing);
      importing.pop();

      Some(css)
    }

    fn rewrite_nested(
      &mut self,
      css: &str,
      base: &Url,
      encoding: &'static Encoding,
      importing: &mut Vec<Url>,
    ) -> String {
      let mut parser = Parser::new(css);
      let mut out = String::with_capacity(css.len());
      let mut imports_allowed = true;

      loop {
        let start = parser.state();
        let Ok(token) = parser.next_including_whitespace_and_comments() else {
          break;
        };
        let token = token.clone();

        match token {
          Token::WhiteSpace(_) | Token::Comment(_) | Token::CDO | Token::CDC => {
            out.push_str(parser.slice_from(start.position()));
          }
          Token::AtKeyword(name) if name.eq_ignore_ascii_case("import") => {
            let rule_start = start.position();
            let import = parser
              .parse_until_after(
                Delimiter::Semicolon | Delimiter::CurlyBracketBlock,
                |input| Ok::<_, ParseError<()>>(Import::parse(input, base)),
              )
              .ok()
              .flatten();
            let rule = parser.slice_from(rule_start);
            let import = import.filter(|_| !rule.trim_end().ends_with('}'));

            match import {
              Some(import) if imports_allowed => {
                if let Some(sheet) = self.load_nested(&import.url, encoding, importing) {
                  import.wrap(sheet, &mut out);
                }
              }
              Some(_) => {}
              None => out.push_str(rule),
            }
          }
          Token::AtKeyword(name)
            if name.eq_ignore_ascii_case("charset") || name.eq_ignore_ascii_case("layer") =>
          {
            let is_layer = name.eq_ignore_ascii_case("layer");

            out.push_str(parser.slice_from(start.position()));
            let ends_in_block = rewrite_rest(&mut parser, base, &mut out);

            imports_allowed &= !(is_layer && ends_in_block);
          }
          _ => {
            parser.reset(&start);
            imports_allowed = false;
            rewrite_rest(&mut parser, base, &mut out);
          }
        }
      }

      out
    }
  }

  /// Copies the rest of one top-level statement or rule to `out`, through its `;` or block, with
  /// its `url()`s resolved against `base`. Whether it ended in a block.
  fn rewrite_rest(parser: &mut Parser<'_>, base: &Url, out: &mut String) -> bool {
    let mut ends_in_block = false;

    while let Ok(token) = parser.next_including_whitespace_and_comments() {
      let token = token.clone();
      let is_end = matches!(token, Token::Semicolon | Token::CurlyBracketBlock);

      write_token(parser, &token, base, false, out);

      if is_end {
        ends_in_block = matches!(token, Token::CurlyBracketBlock);
        break;
      }
    }

    ends_in_block
  }

  /// Writes `token` to `out`, resolving it as a URL if it is one, and the block it opens.
  fn write_token(
    parser: &mut Parser<'_>,
    token: &Token<'_>,
    base: &Url,
    in_image_set: bool,
    out: &mut String,
  ) {
    match token {
      Token::UnquotedUrl(url) => write_url(url, base, out),
      Token::QuotedString(url) if in_image_set => {
        let _ = serialize_string(&resolve(url, base), out);
      }
      Token::Function(name)
        if name.eq_ignore_ascii_case("url") || name.eq_ignore_ascii_case("src") =>
      {
        let argument = parser.parse_nested_block(|input| {
          let start = input.state();

          if let Ok(url) = input.expect_string_cloned() {
            return Ok::<_, ParseError<()>>(Ok(url.to_string()));
          }

          input.reset(&start);
          while input.next_including_whitespace_and_comments().is_ok() {}

          Ok(Err(input.slice_from(start.position()).to_owned()))
        });

        match argument {
          Ok(Ok(url)) => write_url(&url, base, out),
          Ok(Err(raw)) => {
            let _ = token.to_css(out);
            let _ = write!(out, "{raw})");
          }
          Err(_) => {
            let _ = token.to_css(out);
            out.push(')');
          }
        }
      }
      Token::Function(_)
      | Token::ParenthesisBlock
      | Token::SquareBracketBlock
      | Token::CurlyBracketBlock => {
        let image_set = matches!(token, Token::Function(name)
          if name.eq_ignore_ascii_case("image-set") || name.eq_ignore_ascii_case("-webkit-image-set"));

        let _ = token.to_css(out);
        let _ = parser.parse_nested_block(|input| {
          while let Ok(inner) = input.next_including_whitespace_and_comments() {
            let inner = inner.clone();

            write_token(input, &inner, base, image_set, out);
          }

          Ok::<_, ParseError<()>>(())
        });
        out.push(match token {
          Token::SquareBracketBlock => ']',
          Token::CurlyBracketBlock => '}',
          _ => ')',
        });
      }
      _ => {
        let _ = token.to_css(out);
      }
    }
  }

  /// Writes `url()` holding `url` resolved against `base`.
  fn write_url(url: &str, base: &Url, out: &mut String) {
    out.push_str("url(");
    let _ = serialize_string(&resolve(url, base), out);
    out.push(')');
  }

  /// `url` resolved against `base`, or as written when it does not resolve: a fragment-only
  /// reference into an SVG document, or an empty `url()`, which names no resource.
  /// <https://drafts.csswg.org/css-values-4/#url-empty>
  fn resolve(url: &str, base: &Url) -> String {
    if url.is_empty() || url.starts_with('#') {
      return url.to_owned();
    }

    base.join(url).map_or_else(|_| url.to_owned(), String::from)
  }

  /// An `@import` rule: the sheet it loads and the conditions it applies the sheet under.
  ///
  /// Approximate: the sheet loads whatever its `supports()` condition says, where a browser loads
  /// none for a false one, and a `layer()` inside a `@media` that does not match still takes its
  /// place in the layer order.
  struct Import {
    url: Url,
    layer: Option<String>,
    supports: Option<String>,
    media: String,
  }

  impl Import {
    /// The prelude after `@import`, none when it names no URL or a Tailwind entry point such as
    /// `tailwindcss/theme`, which takumi reads itself.
    fn parse(input: &mut Parser<'_>, base: &Url) -> Option<Self> {
      let target = match input.next().ok()?.clone() {
        Token::QuotedString(url) | Token::UnquotedUrl(url) => url.to_string(),
        Token::Function(name) if name.eq_ignore_ascii_case("url") => input
          .parse_nested_block(|input| input.expect_string_cloned().map_err(ParseError::<()>::from))
          .ok()?
          .to_string(),
        _ => return None,
      };

      if target == "tailwindcss" || target.starts_with("tailwindcss/") {
        return None;
      }

      let url = base.join(&target).ok()?;
      let mut layer = None;
      let mut supports = None;

      loop {
        let state = input.state();

        match input.next() {
          // `layer` comes before `supports()`, so after it, `layer` starts the media queries.
          Ok(Token::Ident(name))
            if name.eq_ignore_ascii_case("layer") && layer.is_none() && supports.is_none() =>
          {
            layer = Some(String::new());
          }
          Ok(Token::Function(name))
            if name.eq_ignore_ascii_case("layer") && layer.is_none() && supports.is_none() =>
          {
            layer = Some(nested_text(input));
          }
          Ok(Token::Function(name))
            if name.eq_ignore_ascii_case("supports") && supports.is_none() =>
          {
            supports = Some(nested_text(input));
          }
          _ => {
            input.reset(&state);
            break;
          }
        }
      }

      let media_start = input.position();

      while input.next().is_ok() {}

      let media = input
        .slice_from(media_start)
        .trim()
        .trim_end_matches(';')
        .trim()
        .to_owned();

      Some(Self {
        url,
        layer,
        supports,
        media,
      })
    }

    /// Writes `sheet` to `out` inside the rules that apply this import's conditions.
    fn wrap(&self, sheet: String, out: &mut String) {
      let mut closing = 0;

      if !self.media.is_empty() {
        let _ = write!(out, "@media {} {{", self.media);
        closing += 1;
      }
      if let Some(supports) = &self.supports {
        let condition = if supports.trim_start().starts_with('(') {
          supports.clone()
        } else {
          format!("({supports})")
        };
        let _ = write!(out, "@supports {condition} {{");
        closing += 1;
      }
      if let Some(layer) = &self.layer {
        let _ = write!(out, "@layer {layer} {{");
        closing += 1;
      }

      out.push_str(&sheet);
      out.push_str(&"}".repeat(closing));
    }
  }

  /// [`EncodingSupport`] through `encoding_rs`, to decode a sheet as CSS Syntax picks its encoding.
  struct EncodingRs;

  impl EncodingSupport for EncodingRs {
    type Encoding = &'static Encoding;

    fn from_label(ascii_label: &[u8]) -> Option<Self::Encoding> {
      Encoding::for_label(ascii_label)
    }

    fn utf8() -> Self::Encoding {
      UTF_8
    }

    fn is_utf16_be_or_le(encoding: &Self::Encoding) -> bool {
      *encoding == UTF_16BE || *encoding == UTF_16LE
    }
  }

  /// Whether `a` and `b` name the same sheet once their fragments are dropped.
  fn same_ignoring_fragment(a: &Url, b: &Url) -> bool {
    a[..Position::AfterQuery] == b[..Position::AfterQuery]
  }

  /// The source text inside the block the parser just opened.
  fn nested_text(input: &mut Parser<'_>) -> String {
    input
      .parse_nested_block(|input| {
        let start = input.position();

        while input.next_including_whitespace_and_comments().is_ok() {}

        Ok::<_, ParseError<()>>(input.slice_from(start).trim().to_owned())
      })
      .unwrap_or_default()
  }
}
