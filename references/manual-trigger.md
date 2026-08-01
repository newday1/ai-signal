# Manual Trigger

When the user invokes `/ai-signal` or asks for their digest:
1. Skip cron — run immediately
2. Same fetch → remix → deliver flow
3. Tell the user you're fetching fresh content

When the user asks to expand YouTube items without a full digest refresh
(`展开 YT1` / `详细解释 YT2` / multi-id variants), skip the digest pipeline and
run `references/youtube-expand-translate.md` against the latest
`payload.youtube` / digest numbering.

---
