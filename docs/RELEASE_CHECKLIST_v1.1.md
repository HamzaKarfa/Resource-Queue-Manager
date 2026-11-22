# Resource Queue Manager v1.1.0 — Stable release checklist

This checklist records **what automation proves** and what still requires manual verification. Closing issues or publishing a prerelease is not evidence that a real Home Assistant migration and rollback were executed.

## Feature delivery and integration

- [x] Capacity providers: Classic and Weighted, with frozen per-request effective weights.
- [x] Independent Strict / Backfill allocator and FIFO / LIFO / Priority FIFO strategies.
- [x] Ignore / Count recurrence provider; waiting repeats preserve order and costs.
- [x] Home Assistant four-category configuration menu, guided initial setup and EN/FR translations.
- [x] Save-before-grant event semantics and persisted paused recovery.
- [x] Complete feature candidate released as [v1.1.0-rc.2](https://github.com/HamzaKarfa/Resource-Queue-Manager/releases/tag/v1.1.0-rc.2). The RC2 guarded workflow passed Python 3.13/3.14, Home Assistant fixture tests, HACS and hassfest.
- [x] Feature issues #12–#17, #27 and #29 closed as completed in RC2.
- [x] One [consolidation PR #32](https://github.com/HamzaKarfa/Resource-Queue-Manager/pull/32) targets `main`; do not merge the stacked feature or old RC staging PRs individually.

## Stable publication gates

- [x] Manifest staged as `1.1.0`, with version-matching public notes `docs/releases/v1.1.0.md`.
- [x] README.md, README.fr.md and provider README files describe the final stable features and migration.
- [x] Dedicated `publish-v1.1-approved-merge.yml` workflow checks for exact PR #32 merge authorization, two-parent merge, manifest/notes, unique tag, and the same final commit for the published release.
- [ ] All PR #32 tests pass on its **final head SHA**: Python 3.13 and 3.14, Home Assistant 2026.11 integration, HACS and hassfest.
- [ ] PR #32 reviewed and made **Ready for review**.
- [ ] Explicit merge authorization from maintainer and actual two-parent PR #32 merge into `main`. Squash and rebase will not activate the stable workflow.
- [ ] Workflow tests pass on **the actual `main` merge SHA**; publication proceeds automatically only after all these tests pass.
- [ ] Confirm GitHub release `v1.1.0` is **stable/latest** (not a prerelease), its tag equals the tested merge SHA, and previous RC tags are unchanged.
- [ ] Close superseded stacked implementation PRs with a reference to the merged PR #32; close tracking issues #11 and #18 only after release verification.

## Manual Home Assistant acceptance — not demonstrated by CI

The maintainer should explicitly validate these with a backup and noncritical test entities. **Leave unchecked unless actually observed.**

- [ ] Full Home Assistant backup saved, including `.storage/resource_queue_manager.*` and config entries.
- [ ] Upgrade an existing v1.0 populated queue and verify exact `active`/`waiting` IDs, original four sensor IDs, defaults Classic + Strict + Ignore, and no duplicate grant events.
- [ ] Confirm every queue restores `paused`, inspect `recovery_issues`, resume only after supervising entity state.
- [ ] Weighted (capacity 15): defaults 10 + 10, verify blocked waiting request, then effective override 5 permits two simultaneous reservations without changing its configured default.
- [ ] Backfill (capacity 15): active 10, blocked head 10, later requests 3 and 2 are granted while the head remains waiting; Strict blocks them.
- [ ] Priority FIFO ordering and FIFO ties across three or more distinct resources (including Backfill).
- [ ] Count repeated pending request ID three times; verify one pending entry and `occurrences: 3` on grant; active repeats do not increase it.
- [ ] Change only one of the four Configure categories; other settings, weights, priorities and counts remain unchanged.
- [ ] Opening a Configure menu does not pause a running queue; accepted edits trigger reload and paused recovery.
- [ ] Two queues do not share reservations, budgets or events; actions target `config_entry_id` explicitly.
- [ ] Corrupt snapshots, invalid weights and policy changes with nonempty queues fail closed, without losing stored reservations.
- [ ] Restore the matching full **v1.0 backup** in a separate test instance to confirm rollback. A code-only downgrade after Weighted/Count data is **not** guaranteed.

## Publication safety and rollback

The stable workflow triggers only from a **push to `main` whose head merge commit subject** is exactly `release: authorize v1.1.0 stable (PR #32)`. It validates that the commit is a two-parent merge and is GitHub PR #32's actual merge commit. A nonmatching push is inert.

The publishing job refuses an existing tag/release and uses `--target "$GITHUB_SHA" --latest` to publish **v1.1.0 stable** on the exact commit tested.

A failure before publication must leave v1.0.0 as the latest stable; review the GitHub Actions logs and fix the release branch/PR rather than moving or overwriting existing tags. After publication, rollback on a specific Home Assistant installation requires restoring the pre-upgrade full backup, not merely installing an old version of the integration.

**The automated CI checks do not certify real electrical safety or real-HA rollback success.**
