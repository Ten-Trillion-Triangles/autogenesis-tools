# pump-station SKILL.md needs refactor (over 100K char cap)

**Status as of 2026-07-10:** `pump-station/SKILL.md` is at 100,656 chars (limit 100,000). Cannot accept further `patch` actions until refactored.

**What was added 2026-07-10:**
- `references/sandbox-test-recipe.md` — direct kotlinc + JUnit Platform launcher recipe
- `references/new-pitfalls-2026-07-10.md` — three new pitfalls (#N+5 audit-class-vs-test-class, #N+6 read fixtures first, #N+7 JUnit 5 not JUnit 4)
- `scripts/verify-pumpstation-defect-fix.sh` — 10-check ad-hoc verification template
- `templates/pumpstation-defect-dispatch-context.md` — subagent dispatch context template

**What was NOT updated:** the `pump-station/SKILL.md` frontmatter `version: 1.16.0` should be `1.16.1` (or `1.17.0` if these are surfaced as a major change) and the frontmatter should mention the new references / scripts / templates. Could not apply because the file is over the char cap.

**Refactor plan (for the next session / curator):**

1. Move the long "Two-Scope Loop Structure" section body (lines ~80-130 in the existing file) into `references/loop-execution-and-goal-validation.md` — keep just a one-line pointer in SKILL.md.
2. Move the "Defect Catalog" section (the long table of Defect 8-26 with all the per-defect descriptions) into `references/defect-catalog.md` — keep just a one-line pointer in SKILL.md.
3. Move the "Magic Contracts" section into `references/magic-contracts.md` — keep just a one-line pointer in SKILL.md.
4. Bump version to `1.17.0` and update the frontmatter to list the new references/scripts/templates added in this refactor.

**Estimated savings:** ~60K chars moved out of SKILL.md into references — should bring SKILL.md down to ~40K chars and well under the cap, leaving room for future minor-version bumps.

**Action required:** the curator (or next session that has edit access) should `skill_manage(action='edit')` the SKILL.md, moving the long sections to references/ and updating the frontmatter. Without this refactor, the `pump-station` skill cannot accept further updates via the `patch` action.
