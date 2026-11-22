# Resource Queue Manager — Guide en français

[![Add to My Home Assistant](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=HamzaKarfa&repository=Resource-Queue-Manager&category=integration)

[Documentation complète en anglais](README.md) · [Architecture v1](docs/V1_ARCHITECTURE.md) · [Migration v0.4 → v1](docs/MIGRATION_v0.4_to_v1.md) · [Notes de version](docs/releases/v1.0.0.md)

**Resource Queue Manager** permet de gérer plusieurs files de ressources indépendantes dans Home Assistant, avec les stratégies **FIFO, LIFO et FIFO avec priorité**, une capacité configurable et des réservations persistantes. Les files coordonnent les autorisations ; les automatisations restent responsables de la commande des appareils.

> **Versions :** Marketplace/HACS installe les versions publiées, pas automatiquement les branches de développement. Vérifier la version installée avant de suivre les exemples v1 ; tester toute modification non publiée sur un Home Assistant séparé.

> **Sécurité :** l'intégration ne commande jamais directement les relais. Tes automatisations décident d'allumer et d'éteindre les appareils après réservation. Ce logiciel n'est ni un délesteur électrique certifié, ni un système de protection thermique ; les sécurités matérielles restent indispensables.

## Aperçu de la v1.1 — candidate RC, non stable

> La branche `release/v1.1.0-rc.1` réunit les fonctionnalités de la v1.1 pour les essais. Le manifeste porte la version `1.1.0-rc.1`, distincte de la version stable `1.0.0`. Lire les [notes de préversion](docs/releases/v1.1.0-rc.1.md) et [la procédure de migration](docs/MIGRATION_v1.0_to_v1.1.md) avant toute installation.


La v1.1 sépare trois responsabilités indépendantes : **l'ordonnancement** (FIFO/LIFO/FIFO prioritaire), **la capacité** (places ou unités) et **le traitement des demandes répétées** (ignorées ou comptées).

| Paramètre | Par défaut, compatible v1.0 | Possibilité en v1.1 |
| --- | --- | --- |
| Stratégie | FIFO ou stratégie déjà choisie | FIFO, LIFO, FIFO prioritaire, sans modification |
| Capacité | `classic` : 1 à 50 places actives | `weighted` : 1 à 100000 unités, **sans deuxième limite de places** |
| Poids des entités | Une place par réservation | Une valeur entière par entité supervisée, initialement 1 |
| Récurrences | `ignore` : comportement idempotent | `count` : compter les répétitions d'un `resource_id` **en attente** |

Avec une capacité totale de **100 unités**, la valeur `engine_data.weight` permet d'utiliser 25 unités **pour cette nouvelle demande uniquement** et ne modifie pas le poids par défaut de l'entité :

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: ID_DE_L_ENTREE
  resource_id: chauffage_salon
  entity_id: light.relais_chauffage_salon
  engine_data:
    weight: 25
```

Le poids effectif reste figé pendant l'attente, l'exécution et après redémarrage. Seules les réservations actives consomment des unités. La file conserve un ordre strict : une petite demande ne peut pas dépasser la première demande en attente si celle-ci ne rentre pas dans la capacité restante.

En mode `count`, une demande démarre à `occurrences = 1`. Les répétitions avec le même `resource_id` **encore en attente** augmentent son compteur, sans dupliquer l'entrée, modifier son poids ni sa priorité. Les répétitions d'une demande déjà active sont ignorées. L'événement d'attribution fournit `occurrences`, `effective_weight` et `capacity_mode` ; les quatre capteurs existants conservent leurs identifiants et ajoutent les attributs de capacité, poids et récurrence.

**Compatibilité :** les anciennes files restent en `classic + ignore` et leurs automatisations YAML continuent de fonctionner. Toute file redémarre en `paused`, et le changement de mode nécessite une file vide. Le logiciel ne commande pas les équipements et ne mesure pas les watts.

Pour préparer la mise à niveau, consulter le [guide de migration v1.0 → v1.1](docs/MIGRATION_v1.0_to_v1.1.md), [la documentation des récurrences](docs/V1.1_RECURRENCE.md) et la [checklist de publication](docs/RELEASE_CHECKLIST_v1.1.md). **La v1.1 n'est pas encore publiée sur Marketplace/HACS** : utiliser un Home Assistant de test et conserver une sauvegarde.

## Les nouveautés de la v1

Chaque instance possède son **nom**, sa **capacité** (entre 1 et 50 réservations simultanées), ses **entités supervisées**, son **algorithme**, ses capteurs et sa sauvegarde. Il est possible de créer plusieurs gestionnaires depuis **Paramètres → Appareils et services → Ajouter une intégration**.

| Stratégie | Comportement |
| --- | --- |
| **FIFO** | Premier arrivé, premier servi |
| **LIFO** | Dernier arrivé parmi les demandes en attente, premier servi |
| **FIFO avec priorité** | Niveau de priorité (1 à 10), puis ordre d'arrivée en cas d'égalité |

Pour **FIFO avec priorité**, choisir le sens des priorités : `highest_first` (10 avant 1) ou `lowest_first` (1 avant 10).

Les stratégies n'interrompent **jamais** une réservation déjà active. Une priorité faible peut rester en attente indéfiniment si les demandes prioritaires s'enchaînent : il n'existe pas encore de mécanisme de vieillissement.

## Installation et tests

**Prérequis : Home Assistant 2026.11.0 ou version ultérieure.**

Pour installer une version stable, rechercher **Resource Queue Manager** dans **Marketplace**, ou utiliser le lien `https://github.com/HamzaKarfa/Resource-Queue-Manager`. Marketplace ne récupère pas automatiquement les changements non publiés des PR.

Pour tester une **branche de développement** avant qu'elle ne soit publiée :

1. Faire une sauvegarde complète ou, de préférence, utiliser un Home Assistant de test.
2. Récupérer le dossier complet `custom_components/resource_queue_manager` depuis la [branche de développement v1](https://github.com/HamzaKarfa/Resource-Queue-Manager/tree/docs/v1.1-regression-release-readiness/custom_components/resource_queue_manager), si elle existe encore, ou depuis la branche en cours de revue.
3. Le copier dans le répertoire `config/custom_components/` du Home Assistant de test, sans mélanger les fichiers de versions différentes.
4. Redémarrer Home Assistant puis ajouter l'intégration **Resource Queue Manager**.
5. Configurer un nom, une stratégie, une capacité et quelques entités Home Assistant **sans risque** (par exemple une lampe de test, `input_boolean`, `input_number`, `input_text`, `number` ou `text`).
6. Contrôler les états physiques et les capteurs avant de reprendre la file.

Une même entité ne peut pas être supervisée par deux files. Il n'existe **aucune limite globale de puissance** entre les différentes files. Les entités ON/OFF restent soumises à une vérification de l'état `off` avant la libération ; les helpers numériques et textuels sont des ressources logiques (vérification de disponibilité uniquement).

## Appels d'actions

Chaque action doit cibler l'entrée concernée avec `config_entry_id` lorsqu'au moins deux gestionnaires sont configurés. Il s'agit de l'**identifiant de l'entrée Home Assistant**, proposé dans le sélecteur des outils de développement, pas de son nom.

Les actions `request`, `release`, `cancel` et `resume` sont disponibles depuis **Outils de développement → Actions**. Voici leur présentation dans Home Assistant en français :

![Actions Resource Queue Manager dans Home Assistant : demander, libérer, annuler et reprendre une file](assets/resource-queue-manager-actions.webp)

**Test rapide avec une entité sans risque :** après vérification des relais supervisés, sélectionner la file de test puis exécuter `resume`. Envoyer une demande `request` avec un `resource_id` de test et une entité supervisée ; vérifier que son capteur `active` augmente. En laissant l'entité test à l'état `off`, effectuer `release` et confirmer que `active` diminue. Vérifier également `cancel` sur une demande en attente. Ne pas utiliser un radiateur réel pour le premier essai.

### Types d'entités supervisées

Les entités **natives et les helpers** sont acceptés : `number`, `text`, `sensor`, `input_number`, `input_text`, `input_select`, etc. Les entités utilisées par le chauffage restent les `light` et `switch` existants.

| Type d'entité | Contrôle | Libération d'une réservation active |
| --- | --- | --- |
| `light`, `switch`, `fan`, `input_boolean` | État `on` / `off` obligatoire ; refuse une entité allumée sans réservation | **État `off` confirmé obligatoire** |
| `number`, `text`, `input_number`, `input_text`, autres domaines | Vérifie que l'entité existe et que son état n'est ni `unknown` ni `unavailable` | État disponible suffisant pour la réservation logique |

**Important :** les valeurs des entités numériques ou textuelles ne prouvent **jamais** l'arrêt d'un appareil électrique. Utiliser une entité ON/OFF supervisée et des protections matérielles indépendantes pour des charges réelles.

### Reprendre une file après le démarrage

À chaque redémarrage, les gestionnaires reviennent en mode `paused`. Il faut contrôler les entités supervisées puis reprendre **chaque** file :

```yaml
action: resource_queue_manager.resume
data:
  config_entry_id: "ID_DE_L_ENTREE"
```

### Demander une place avec priorité

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "ID_DE_L_ENTREE"
  resource_id: chambre_1
  entity_id: switch.relais_chambre_test
  strategy_data:
    priority: 8
```

Pour FIFO et LIFO, **ne pas ajouter `strategy_data`** ; leurs providers n'acceptent aucune métadonnée. Pour FIFO avec priorité, le champ `priority` est obligatoire pour une nouvelle demande.

Une demande peut être accordée immédiatement ou placée en attente. **L'automatisation doit vérifier l'octroi de la réservation** via le capteur `active` de la bonne file (ou l'événement `resource_queue_manager_slot_granted`) avant d'allumer l'appareil.

### Libérer une place

Pour les entités ON/OFF (`light`, `switch`, `fan`, `input_boolean`), **attendre la confirmation de l'état `off` dans Home Assistant** :

```yaml
action: resource_queue_manager.release
data:
  config_entry_id: "ID_DE_L_ENTREE"
  resource_id: chambre_1
```

L'action `resource_queue_manager.cancel` retire une demande en attente ou libère une réservation active. Pour les entités ON/OFF, elle exige toujours l'état `off`. Pour les autres entités, elle exige uniquement un état connu et disponible.

## Capteurs et récupération

Chaque gestionnaire crée quatre capteurs : **active**, **waiting**, **available** et **status**. Leurs attributs présentent l'ordre des ressources, la stratégie, l'identifiant de configuration et les éventuels problèmes de récupération (`recovery_issues`).

Les installations provenant de la v0.4 conservent les identifiants uniques de leurs capteurs d'origine ; les nouvelles files prennent le nom configuré. Vérifier les véritables identifiants dans Home Assistant avant d'écrire les automatisations.

Si `resume` échoue, une entité peut être absente, indisponible ou (pour une entité ON/OFF) allumée sans réservation. **Ne jamais supprimer une sauvegarde de réservation pour contourner ce contrôle.**

## Migration v0.4 → v1

La migration conserve le domaine `resource_queue_manager`, les anciens noms d'actions et la file FIFO existante. Les anciennes sauvegardes restent lisibles et l'ancien gestionnaire reste configuré en FIFO.

**Point important : dès la création d'une deuxième entrée, les actions sans `config_entry_id` échouent volontairement.** Il faut donc ajouter cet identifiant aux automatisations d'origine **avant** de créer la deuxième file.

Une stratégie ou ses paramètres ne peuvent être modifiés que lorsque la file est entièrement vide. Tout rechargement laisse la file en pause jusqu'à une nouvelle reprise explicite.

Consulter impérativement le [guide complet de migration, avec procédure de retour arrière](docs/MIGRATION_v0.4_to_v1.md) avant de faire des essais sur une installation existante.

## Développement et publication

Les tests Python, les tests d'intégration Home Assistant, HACS et hassfest sont exécutés par GitHub Actions. La publication d'une version stable passe par un workflow manuel après revue de la PR.

La publication est manuelle, réservée à la branche `main` après validation : consulter [DEVELOPMENT.md](docs/DEVELOPMENT.md) et la [checklist de validation v1](docs/RELEASE_CHECKLIST_v1.md).

Licence : [MIT](LICENSE).
