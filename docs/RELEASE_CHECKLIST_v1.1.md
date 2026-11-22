# v1.1.0 Release acceptance checklist — internal

**UNRELEASED.** Do not merge or publish before reviewing these gates. This file intentionally does not mark manual validation complete.

## Stable integration approach — one consolidation PR

The feature stack is already represented by published `v1.1.0-rc.2`. To avoid duplicate/partial merges of stacked PR branches, prepare **one consolidated PR against `main`**, based on the RC2 tag plus the v1.1 stable-ready documentation.

- [x] Feature code and documentation in the RC2 snapshot; the RC2 guarded CI passed Python 3.13/3.14, HA integration, HACS and hassfest.
- [x] Individual implementation issues #12–#17, #27 and #29 completed in the pre-release.
- [ ] Approve/merge the consolidated PR **once**, after final review, instead of merging the RC1/RC2 release PRs (which carry pre-release versions) or merging each stacked feature PR separately.
- [ ] Before merging to main, update the manifest from `1.1.0-rc.2` to `1.1.0` in an explicitly approved stable version-bump commit and verify all final checks again.
- [ ] After the consolidated merge, close the now-redundant stacked PRs as **superseded by the actual merged consolidation PR**; do not falsely mark them merged.
- [ ] Keep tracking issue #11 and release-readiness issue #18 open until the stable tag is published and manual acceptance is complete.

**Do not close or merge implementation PRs prematurely:** they still provide code review context and the stable integration has not reached `main`. The existing v1.0 stable publication workflows are version-pinned and require a dedicated v1.1 stable workflow.

## Préversion v1.1.0-rc.2 — Backfill et configuration organisée

**Autorisation de pré-release RC2 :** le mainteneur a demandé d'intégrer la refonte des paramètres à la prochaine candidate. La publication de `v1.1.0-rc.2` reste conditionnée aux contrôles CI du workflow dédié ; aucune validation manuelle n'est implicitement considérée comme réussie.



La branche `release/v1.1.0-rc.2` regroupe les PR #28 (Backfill) et #30 (interface en quatre catégories) au-dessus de la pré-release précédente. La publication doit créer un **nouveau tag**, sans déplacer `v1.1.0-rc.1`, fusionner dans `main` ni marquer la candidate comme stable.

- [ ] Vérifier les tests Python 3.13 et 3.14, Home Assistant 2026.11, HACS et hassfest **sur le commit final autorisant la RC2**.
- [ ] Publier uniquement `v1.1.0-rc.2` comme **GitHub pre-release**, jamais « latest stable », après ces vérifications.
- [ ] Vérifier que les quatre rubriques apparaissent en français et en anglais et qu'une seule rubrique peut être modifiée sans ressaisir les autres.
- [ ] Vérifier que l'ouverture des menus ne met pas en pause une file active, mais que tout changement accepté conserve la reprise explicite après rechargement.
- [ ] Tester Strict et Backfill sur une file pondérée avec une demande bloquée devant deux petites demandes.
- [ ] Vérifier sur HA réel la migration de la RC1 vers RC2, la reprise après redémarrage et un retour arrière sur sauvegarde cohérente.

**Aucune de ces validations manuelles n'est réputée acquise grâce aux seuls tests CI.**

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
