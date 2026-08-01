# Podcast Translation Rules

Skill-local copy of the Podcast translation rules used when expanding YouTube
items (`展开 YT1` / `详细解释 YT2`) or producing full bilingual podcast-style
documents from a transcript.

When translating or saving podcast / YouTube transcripts and notes, always
follow these rules.

## Output Directory

Save podcast transcripts, translations, and notes under a **relative**
`podcast/` directory next to the current project (workspace) root — never a
hardcoded absolute path.

Resolution order:

1. If `<project-root>/podcast/` already exists (case-insensitive match on
   `podcast` / `Podcast` is fine), use that directory.
2. If it does not exist, create `<project-root>/podcast/` and use it.

Examples (project root = where the user is working):

- Project has `podcast/` → write to `podcast/ShowName_Topic_ZH.md`
- Project has no `podcast/` → `mkdir podcast` (or equivalent), then write there

Do not write into the AI Signal skill checkout unless that checkout *is* the
user's project root. Prefer the user's open workspace / project root.

## Document Structure (Exactly Three Sections)

Every translation document must contain **exactly three sections**, in this order:

### 第一部分：核心要点总结与段落索引 (Core Points Summary & Section References)

- Extract the most critical key points from the transcript.
- For each point, provide a reference to its specific location in the document.
- **References must use the original English quotes** (indicate the speaker and key sentences).
- **Provide clickable anchor links** (e.g. `[Heading](#heading-anchor)`) linking directly to the corresponding subsection in Section 2.

### 第二部分：英汉双语对照翻译 (Bilingual Translation)

- Perform a complete, word-for-word translation into Chinese **block-by-block**.
- **No sentence or paragraph can be omitted.**
- Format layout as:
  1. Original English paragraph first
  2. Immediately followed by its Chinese translation paragraph

### 第三部分：批判性思考与投资机会分析 (Critical Analysis & Investment Insights)

- Provide an analytical opinion on the content.
- Use critical thinking to challenge assertions; present a balanced pro-and-con debate on whether the core arguments are correct.
- Include a **dedicated investment-industry perspective** section detailing concrete investment opportunities revealed by the discussion (e.g. defense tech, cybersecurity, AI localization, regional market strategies, energy infrastructure, etc.).

## Naming & Quality Notes

- Prefer clear filenames that identify the show/episode and language (e.g. `ShowName_Guest_Topic_ZH.md`).
- Section 2 headings should be stable anchors so Section 1 links resolve correctly.
- Do not collapse or summarize Section 2; full bilingual coverage is mandatory.
