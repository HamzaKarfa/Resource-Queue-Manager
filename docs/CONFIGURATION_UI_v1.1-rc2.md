# Resource Queue Manager — Interface de configuration v1.1

La nouvelle interface remplace l'ancien formulaire unique dans **Resource Queue Manager v1.1.0**. Elle avait été introduite dans la pré-release **v1.1.0-rc.2**.

## Modification d'une file existante

Depuis **Paramètres → Appareils et services → Resource Queue Manager → Configurer**, Home Assistant présente un menu natif de quatre rubriques (traduites en français et en anglais) :

1. **Ressources supervisées** : sélectionner les entités, puis configurer leurs poids par défaut **uniquement si** la file est pondérée.
2. **Capacité** : choisir Classique/Pondéré et la limite de capacité. Le formulaire des poids n'apparaît que lors du passage en mode Pondéré ou lorsque des poids existants dépassent la nouvelle limite.
3. **Ordonnancement et attribution** : FIFO/LIFO/FIFO prioritaire, Strict/Backfill. La direction des priorités ne se redemande que lorsqu'on change de stratégie ou qu'on coche « Modifier les paramètres de priorité ».
4. **Demandes répétées** : Ignorer les doublons / Compter les répétitions en attente.

Chaque rubrique enregistre toutes les options de l'entrée en **préservant les valeurs des autres rubriques**. Une nouvelle page n'est pas imposée pour un changement simple (par exemple 15 → 20 unités).

### Comportement lors des changements

- **Ouvrir le menu ou naviguer ne met pas la file en pause** ; seul un changement validé déclenche le rechargement prévu de Home Assistant.
- Les modifications de stratégie/paramètres, du mode d'attribution, du mode de capacité ou de la gestion des récurrences sont refusées quand des demandes actives/en attente existent.
- Une entité liée à une réservation active ou en attente ne peut être supprimée ; les poids effectifs déjà figés restent inchangés.
- Une limite de capacité qui ne peut plus accueillir les réservations actives ou les poids des demandes en attente est refusée.
- Après une modification validée, la file démarre en `paused`, vérifie les entités supervisées et attend un `resume` explicite, comme avant.

## Nouvelle file

La première configuration suit désormais un assistant :

1. Nom et entités supervisées.
2. Mode et limite de capacité.
3. Ordonnancement + mode Strict/Backfill.
4. Paramètres de priorité **si** FIFO prioritaire a été sélectionné.
5. Gestion des demandes répétées.
6. Poids par défaut **si** le mode Pondéré a été sélectionné et que des entités sont supervisées.

## Compatibilité

La fonctionnalité **ne change pas le moteur** : les paramètres stockés, `resource_id`, `strategy_data`, `engine_data`, les capteurs et les événements continuent de fonctionner comme précédemment. Les modes par défaut des installations historiques restent `classic`, `fifo`, `strict` et `ignore` en l'absence de configuration contraire.

Cette interface et Backfill font partie de la **v1.1.0**. Les tests automatisés de la RC2 ont validé leur fonctionnement ; la sauvegarde et la restauration réelle d'une installation restent à vérifier individuellement.
