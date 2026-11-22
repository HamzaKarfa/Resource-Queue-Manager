# v1.1.0 Release acceptance checklist — internal

**UNRELEASED.** Do not merge or publish before reviewing these gates. This file intentionally does not mark manual validation complete.

## Préversion v1.1.0-rc.1 — branche de validation

La branche `release/v1.1.0-rc.1` rassemble les commits empilés des PR #19 à #25 sans fusionner ces PR dans `main`. Son manifeste utilise `1.1.0-rc.1`; la branche stable et le tag `v1.0.0` ne changent pas.

- [ ] Tester **le SHA final de la branche RC** (Python 3.13/3.14, tests HA 2026.11, HACS/hassfest) et vérifier les notes `docs/releases/v1.1.0-rc.1.md`.
- [ ] Publier uniquement un tag `v1.1.0-rc.1` marqué **GitHub prerelease**, jamais « latest stable », et rattaché exactement au commit testé.
- [ ] Tester l'installation et le retour arrière sur une instance HA séparée, sans faire passer les essais CI pour des tests matériels.
- [ ] Poursuivre les revues et les fusions sur `main` indépendamment de la RC, après vérification des prérequis.

## Ordered PR dependency chain

- [ ] #19 classic provider foundations → `main`
- [ ] #20 weighted units → `main` after #19
- [ ] #21 Home Assistant capacity options → `main` after #20
- [ ] #22 recurrence counting → `main` after #21
- [ ] #23 action, sensor and event contract → `main` after #22
- [ ] #24 snapshot migration and recovery guards → `main` after #23
- [ ] Final documentation / release-readiness PR after #24

## Automated checks — at the final proposed merge SHA

- [ ] Python 3.13 and 3.14 unit tests: `python -m unittest discover -s tests -v`
- [ ] Home Assistant 2026.11 fixture integration suite: `python -m pytest -q tests/ha`
- [ ] HACS/Marketplace validation and hassfest
- [ ] Confirm all EN/FR JSON strings parse and keys match; confirm selector labels in Home Assistant
- [ ] No unrelated file changes, unstable dependencies or merge conflicts

## Manual HA checks — not verified by CI

- [ ] Fresh classic/ignore queue created in English and French, with legacy YAML request/release/cancel/resume.
- [ ] Update v1.0 populated queue, preserve original `active`/`waiting` and sensor IDs, remain paused until `resume`.
- [ ] Weighted setup: capacity 100, per-entity weights 30/40, one-request `engine_data.weight: 25`, then release restores exactly 25.
- [ ] Strict head-of-line: active 70, pending 40, pending 20; last request cannot pass the 40-unit head when only 30 units remain.
- [ ] Count mode: 3 pending identical resource IDs yield one waiting entry and `occurrences: 3`; active duplicates do not increment.
- [ ] Count + Priority FIFO + Weighted on the same queue without changes to ordering or weight.
- [ ] Confirm event payload fields and persistence-before-event; IDs must match the owning queue.
- [ ] Two independent queues, route every service by `config_entry_id`, no cross-queue grants.
- [ ] Stop/restart with active and waiting work; restore paused, no regrant until explicit safe resume.
- [ ] Reject invalid weights, mode switching with existing work, and removing bound entities; preserve saved state.
- [ ] Verify corrupted snapshot fails closed without lost active bookings and with a clear log.
- [ ] Test backup/restore rollback to v1.0 in a **separate** HA installation; do not attempt a code-only downgrade.

## Release procedure — requires explicit approval

- [ ] Capture maintainer approval, final PR SHA and backup/rollback plan.
- [ ] Merge PRs sequentially and inspect each diff on `main`.
- [ ] Update `manifest.json` version **1.1.0** only in the specifically approved release commit.
- [ ] Finalize `CHANGELOG.md` and `docs/releases/v1.1.0-draft.md` (rename to public release notes when approved).
- [ ] Confirm guarded release workflow supports v1.1.0; do not assume the v1.0 workflow is reusable without review.
- [ ] Create / publish release tag `v1.1.0` only after every gate and maintainer sign-off.
- [ ] Verify public HACS/Marketplace artifact matches signed-off commit; monitor error reports and prepare a patch if necessary.

**These gates intentionally remain unchecked until proven, including the live-HA tests.**
