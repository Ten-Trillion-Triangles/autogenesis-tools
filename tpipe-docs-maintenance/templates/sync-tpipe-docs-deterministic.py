#!/usr/bin/env python3
"""
TPipe -> ttt-site deterministic docs sync.

Replaces scripts/sync-tpipe-docs.cjs when the user demands zero null prev/next
on middle docs. The .cjs script uses TPipe's "## Next Steps" links to derive
chains, which produces orphan docs (no inbound + no outbound link) and shows
up as prevDoc/nextDoc=null on the live site. The user has been explicit:
"null is not an ok value for anywhere other than the very first doc or the
very last one." This script enforces that by alphabetizing each section and
chaining deterministically -- no orphan docs, no nulls in the middle.

Behavior:
- Wipes the destination and regenerates everything from TPipe docs
- For each section (and each subdir like p2p/, specs/), sorts files
  alphabetically and chains: 1st doc -> prevDoc=null, last doc -> nextDoc=null,
  everyone else has both
- Handles p2p/ and superpowers/specs/ subdirs as their own sub-chains
- Writes HYPHENATED slugs (core-concepts-pipe-class) -- see references/ttt-site-docs-sync.md
  gotcha #10 for why path format breaks the site code
- Escapes descriptions with embedded quotes (the .cjs script crashed on
  reasoning-pipes.md which contains a literal "thinking")
- Rewrites internal .md links to /docs/<full-slug> using a basename -> fullSlug
  map (mirrors the rewriter behavior in the .cjs)
- Skips maestro/ (internal planning docs)

Usage:
    # Edit REMOTE and SITE constants at the top, then:
    python3 scripts/sync-tpipe-docs-deterministic.py
"""
import os
import re
import shutil

REMOTE = "/home/cage/Desktop/Workspaces/TPipe/TPipe/docs"
SITE = "/home/cage/Desktop/Workspaces/ttt-site/src/content/docs"

SECTION_MAP = {
    "getting-started": "Getting Started",
    "core-concepts": "Core Concepts",
    "containers": "Containers",
    "advanced-concepts": "Advanced Concepts",
    "api": "API Reference",
    "bedrock": "AWS Bedrock",
    "ollama": "Ollama",
    "openrouter": "OpenRouter",
    "comparison": "Comparisons",
    "case-studies": "Case Studies",
    "superpowers": "Superpowers",
}


def to_hyphen(slug):
    return slug.replace("/", "-")


def extract_title(content, fallback):
    for pattern in [r"^#\s+(.+)$", r"^##\s+(.+)$", r"^###\s+(.+)$"]:
        m = re.search(pattern, content, re.MULTILINE)
        if m:
            return m.group(1).strip()
    return fallback


def extract_description(content):
    lines = content.split("\n")
    found_heading = False
    for line in lines:
        trimmed = line.strip()
        if trimmed.startswith("#"):
            found_heading = True
            continue
        if not found_heading:
            continue
        if trimmed and not trimmed.startswith("---") and 20 < len(trimmed) < 200:
            return re.sub(r"\*+", "", trimmed)[:200]
    for line in lines:
        if line.strip() and len(line.strip()) > 30:
            return line.strip()[:200]
    return ""


def yaml_escape(s):
    """Escape a string for use in a YAML double-quoted scalar."""
    if s is None:
        return None
    return s.replace("\\", "\\\\").replace('"', '\\"')


def estimate_reading_time(content):
    words = len(content.split())
    return f"~{max(1, words // 200)} min"


def classify_doc_type(title, content):
    t = title.lower()
    if any(k in t for k in ("api", "reference", "package", "interface")):
        return "reference"
    if any(k in t for k in ("getting started", "setup", "installation", "first steps", "quick start")):
        return "how-to"
    if any(k in t for k in ("overview", "introduction")):
        return "overview"
    if any(k in t for k in ("error", "troubleshoot", "debug", "exception")):
        return "troubleshooting"
    if re.search(r"\n1\.\s", content) or re.search(r"\n##\s+Step\s", content) or re.search(r"\n##\s+How\s+to", content):
        return "how-to"
    return "concept"


def has_howto(content):
    return bool(re.search(r"\n1\.\s", content) or re.search(r"\n##\s+Step\s", content) or re.search(r"\n##\s+How\s+to", content) or re.search(r"\n###\s+Step\s", content))


def has_faq(content):
    return bool(re.search(r"##\s+Q[?\s]", content) or re.search(r"💡\s+\*\*[\w\s]+\*\*", content))


def find_all_docs(root):
    out = []
    for r, dirs, fnames in os.walk(root):
        if "/maestro" in r or r.endswith("/maestro"):
            continue
        for f in fnames:
            if f.endswith(".md"):
                abs_path = os.path.join(r, f)
                rel = os.path.relpath(abs_path, root).replace(".md", "")
                out.append((rel, abs_path))
    return out


def group_by_subpath(slugs):
    """Group slugs by their parent subdirectory within a section.
    For 'advanced-concepts' returns {'': [...], 'p2p': [...]}.
    For 'superpowers' returns {'specs': [...]}.
    """
    groups = {}
    for slug in slugs:
        parts = slug.split("/")
        if len(parts) == 2:
            groups.setdefault("", []).append(slug)
        else:
            sub = parts[1]
            groups.setdefault(sub, []).append(slug)
    return groups


def chain_deterministically(slugs):
    """Sort alphabetically and chain: first -> prev null, last -> next null, middle -> both."""
    sorted_slugs = sorted(slugs)
    result = []
    for i, slug in enumerate(sorted_slugs):
        prev_slug = sorted_slugs[i - 1] if i > 0 else None
        next_slug = sorted_slugs[i + 1] if i < len(sorted_slugs) - 1 else None
        result.append((slug, prev_slug, next_slug))
    return result


def rewrite_links(content, full_set, basename_map):
    """Rewrite [text](file.md) -> [text](/docs/section/file) using basename map."""
    def repl(m):
        text, href = m.group(1), m.group(2)
        if href.startswith(("http://", "https://", "//", "mailto:", "#")):
            return m.group(0)
        path_part, anchor = (href.split("#", 1) + [None])[:2]
        if not path_part:
            return m.group(0)
        if path_part.startswith("/docs/"):
            return m.group(0)
        t = path_part.replace(".md", "").replace("./", "").replace("../", "")
        base = t.split("/")[-1]
        if t in full_set:
            slug = t
        elif base in basename_map:
            slug = basename_map[base]
        else:
            return m.group(0)
        anchor_suffix = f"#{anchor}" if anchor else ""
        return f"[{text}](/docs/{slug}{anchor_suffix})"
    return re.sub(r"\[([^\]]+)\]\(([^)]+)\)", repl, content)


def main():
    if os.path.exists(SITE):
        shutil.rmtree(SITE)
    os.makedirs(SITE, exist_ok=True)

    docs = find_all_docs(REMOTE)
    print(f"Found {len(docs)} doc files\n")

    full_set = {slug for slug, _ in docs}

    basename_map = {}
    for slug, _ in docs:
        base = slug.split("/")[-1]
        if base not in basename_map:
            basename_map[base] = slug

    by_section = {}
    for slug, _ in docs:
        section = slug.split("/")[0]
        by_section.setdefault(section, []).append(slug)

    # Build chains: per section, per subpath, alphabetical
    slug_links = {}
    for section, slugs in by_section.items():
        sub_groups = group_by_subpath(slugs)
        for sub, sub_slugs in sub_groups.items():
            for slug, prev, nxt in chain_deterministically(sub_slugs):
                slug_links[slug] = (
                    to_hyphen(prev) if prev else None,
                    to_hyphen(nxt) if nxt else None,
                )

    for slug, abs_path in docs:
        with open(abs_path) as fh:
            content = fh.read()

        parts = slug.split("/")
        section = parts[0]
        basename = parts[-1]
        section_title = SECTION_MAP.get(section, section.title())
        title = extract_title(content, basename.replace("-", " ").title())
        description = extract_description(content)
        reading_time = estimate_reading_time(content)
        doc_type = classify_doc_type(title, content)
        prev_doc, next_doc = slug_links.get(slug, (None, None))

        out_path = os.path.join(SITE, slug + ".md")
        os.makedirs(os.path.dirname(out_path), exist_ok=True)

        if len(parts) == 2:
            order = sorted(s for s in by_section[section] if s.count("/") == 1).index(slug) + 1
        else:
            sub = parts[1]
            sub_slugs = [s for s in by_section[section] if s.startswith(f"{section}/{sub}/")]
            order = sorted(sub_slugs).index(slug) + 1

        prev_str = f'"{prev_doc}"' if prev_doc else "null"
        next_str = f'"{next_doc}"' if next_doc else "null"
        fm_lines = [
            "---",
            f'title: "{yaml_escape(title)}"',
            f'description: "{yaml_escape(description)}"',
            f'section: "{section}"',
            f'sectionTitle: "{section_title}"',
            f'docType: "{doc_type}"',
            f'order: {order}',
            f'readingTime: "{reading_time}"',
            f'prevDoc: {prev_str}',
            f'nextDoc: {next_str}',
            f'hasHowTo: {str(has_howto(content)).lower()}',
            f'hasFAQPage: {str(has_faq(content)).lower()}',
            "---",
            "",
        ]

        body = rewrite_links(content, full_set, basename_map)

        with open(out_path, "w") as fh:
            fh.write("\n".join(fm_lines))
            fh.write(body)
        print(f"  {slug}  prev={prev_doc or 'NULL'}  next={next_doc or 'NULL'}")

    print(f"\nDone! {len(docs)} docs written to {SITE}")


if __name__ == "__main__":
    main()
