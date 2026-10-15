# Existing documents

| Found | Do |
| --- | --- |
| ADRs or design documents in another format or place | Leave them where they are. Put their paths and numbering in `repo-map.json` `artifact_paths`, so new ones continue the series. File format differences as `style` findings. |
| Requirements, plans, certifications or other per-piece-of-work documents (an `intents/` folder, specs, tickets in the repo) | Move them to the plugin's artifact-path defaults, as if the convention had always been used: `docs/requirement/`, `docs/plans/`, `docs/verify/`, named `<date>-<normalized-title>.md` (add the slug suffix only when the work had a Studio intent slug). Update every citation of the old paths in the same PR and list the moves in its description. |
| `CLAUDE.md`, `.cursor/rules`, `.github/copilot-instructions.md` or similar | Mine their conventions into the inventory. Once the rules hold them, reduce the file to one line pointing at `AGENTS.md`. |
| An existing `AGENTS.md` | Rewrite it as the index. Every convention it held lands in a rule; the PR description lists where each went. |
| dbt YAML descriptions and doc blocks | Leave them. Take `CONTEXT.md` terms from them. |
| README, CONTRIBUTING and other human documents | Leave them unchanged, including broken links. Add `notes_for_agents` in `repo-map.json` saying agents do not read them for build tasks. Broken links or stale content are `gap` findings. |
| Code comments citing decisions that have no document (`ADR 0004`) | Write the ADR only if the user confirms the decision; otherwise a `gap` finding. |
