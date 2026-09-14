# Inherited Antigravity Rules

This workspace inherits the machine-level Antigravity/Gemini rules from:

- `/home/thomas/.gemini/config/rules/instruction-following.md`
- `/home/thomas/.gemini/config/rules/i-have-adhd.md`
- `/home/thomas/.gemini/config/rules/tech-notes.md`
- `/home/thomas/.gemini/antigravity-cli/settings.json`

## Working Style

- Stay tightly focused on the explicit task and named paths.
- Avoid broad disk scans or unrelated config/file inspection unless directly required.
- If the user says they will run commands, provide exact commands instead of running them.
- Do not run build or compilation commands autonomously; provide the command for the user to run.
- Never push to remotes unless explicitly instructed.

## Output Style

- Lead with the next action or direct answer.
- Use numbered steps for multi-step tasks.
- Keep lists to five items or fewer when possible.
- Restate progress in longer multi-step work.
- End with one concrete next action when anything remains open.
- Keep tone direct and matter-of-fact.

## Project Release Notes

- For internal beta releases, append the git commit count/number to the beta version string.
- For APK work, stamp `versionName` with the short git commit hash and `versionCode` with the commit count.
- Beta publishing stays isolated to the `beta` branch until the user explicitly promotes it.

## Libgen Benchmark Protocol

- Standard benchmark query: `Foundation`
- Maximum results: `5`
- Procedure: queue and download all five books.
- Report elapsed time, total size, bandwidth, and fastest CDNs.
- Keep benchmark data local with no external telemetry.

## Technical Notes

When the user says `note it` or `note`, or when a meaningful breakthrough/fix is achieved:

- Write terse Obsidian notes under `/home/thomas/Documents/tech/`.
- Use kebab-case filenames and YAML frontmatter with tags and date.
- Link notes from `Tech Index.md` and `New-Dots Backlog.md`.
- Update `Dashboard.md` when project status, daily activity, metrics, release state, or major learned concepts change.
- Update the relevant project tracker under `/home/thomas/Documents/tech/projects/` when present.
- Track resolved issues in a timeline file with attribution and running cumulative score.

## Antigravity CLI Context

- Color scheme: `solarized dark`
- Trusted workspace root: `/home/thomas`
