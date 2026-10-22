# Refactoring the model

Use when the model's structure or a definition changes: splitting, folding, renaming, a grain change, a business-rule change, an aggregate's lifecycle, or a star's retirement. Everyday edits do not need this file.

The model is not append-only. These moves are normal work, each validated across every file afterwards, with no dual sources of truth left behind:

- **New standalone model.** An object that serves no star (bridge, rate table, direct-consumption mart) gets its own document named after what it models, one dataset, its own `physical_tables` entry, and a `note` saying why it stands alone. Never park it in a star it cannot join.
- **Fold a standalone model into a star.** When a join key lands, move the dataset into the consuming document, add the relationship and its `physical_joins` entry there, delete the standalone document, and correct every stale statement about the object wherever it lives — its `note`, description, `ai_context`, and any rule the new path invalidates. Relationships cannot cross documents, so leaving both is a second source of truth, not caution.
- **Split the model across documents.** Partition by whole stars, as the atomic-stars rule in `SKILL.md` requires; each document keeps every dataset its own facts need, and shared dims are copied so their identity matches.
- **Move or rename a dataset.** Update every relationship, `physical_join`, and `logical_sources[].physical_table` that names it in the same change; leave no dangling reference for validation to find.

Name new relationships and joins after the existing pattern in the target document; when you are creating the document there is no pattern yet, so follow the example beside this file (`trips_to_<target>`, `fct_<fact>_to_<table>`, `LTS<n>_<purpose>`).

### Aggregate source or standalone document

Population, never the presence of a `where`, decides the disposition. An aggregate source may carry the report window in `where` when its grain is the star's grain rolled up and its population is still the star's population — every `agg_*` rollup is this case. A table whose population is narrower or different — a changed measure definition (billable, payment class), a truncation (`HAVING count >= 25`), an inner join that silently drops rows — is a standalone document, because its counts answer a different question. A table constructed from, or consumed by, two stars is standalone too. A standalone document has no relationships and therefore always raises `table-unjoined`; that is expected there.

### Fact-grain change

When a fact's grain changes, the primary key, the detail `content_grain`, and every count metric change together: a `SUM(CASE ...)`-style count silently becomes a finer-grained count, so count metrics need the distinct rollup key while additive money metrics stay sums. Then establish — by reading each aggregate's SQL, never by assumption — whether that aggregate was rebuilt at the old grain or the new one; if the answer is not available, that is a blocked-mapping question (`references/reverse-engineering.md`), not a default. A metric whose grain disagrees with the aggregate source supplying it is the most expensive silent error in the model.

### Business-rule change

When a definition changes (billable, active, in-window), withdraw — do not merely annotate — every binding whose source computes the old rule; a note alone leaves the stale column bindable, and a priority-0 aggregate outranks the already-correct detail. Withdraw the whole dependency chain: a field whose only supplier is withdrawn cannot stay declared, and a metric whose expression names a withdrawn field is a lie, so the field and metric go with the mapping. One source-level `note` covers a partial withdrawal: name every withdrawn binding and its exact restore condition in it. Correct any `ai_context` that states the old rule, move the rule itself into the source's `where` and the repo's decision record when it is standing, and record the restore as one tracked follow-up per change (decision-record revision or issue), never as memory. An empty `column_map` is a tombstone and must carry that note.

### Aggregate lifecycle

- **Added**: register the table, its join, and its source at honest grain.
- **Rebuilt at a different grain**: re-derive that source's `content_grain` and `column_map` as a grain change.
- **Absorbed by detail** (detail now answers everything the aggregate did): drop the mappings and the handle once nothing names it; a dead aggregate is a stale definition waiting to be trusted.
- **Retired**: delete the handle, its joins, and every source naming it in the same change.

### Star decommission

Deleting a fact star means deleting its document and the handles only it used, after moving the decisions and reasons it carried into the repo's decision record. A document left behind holding half a star is worse than no document: it still validates.

Business rules ride the model, not a footnote to it: a threshold, filter, or bound that changes the answer belongs in the logical source's `where` and (when it is a standing business answer) in the repo's decision record. When a refactor makes a stated rule wrong on one path, that is a business ruling — ask under the blocked-mapping rule in `references/reverse-engineering.md`; never quietly rewrite the rule to fit the new shape.
