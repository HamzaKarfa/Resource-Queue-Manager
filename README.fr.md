# Resource Queue Manager — Documentation française

[![Home Assistant](https://img.shields.io/badge/Home%20Assistant-Intégration%20personnalisée-41BDF5?logo=homeassistant&logoColor=white)](https://www.home-assistant.io/)
[![HACS Marketplace](https://img.shields.io/badge/HACS-Marketplace-41BDF5)](https://hacs.xyz/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)

[![Ajouter à Home Assistant](https://my.home-assistant.io/badges/marketplace_repository.svg)](https://my.home-assistant.io/redirect/marketplace_repository/?owner=HamzaKarfa&repository=Resource-Queue-Manager&category=integration)

[Documentation anglaise](README.md) · [Historique des versions](CHANGELOG.md) · [Migration v1.0 → v1.1](docs/MIGRATION_v1.0_to_v1.1.md)

**Resource Queue Manager (RQM)** gère plusieurs files d'attente indépendantes de **réservations logiques** dans Home Assistant : appareils, automatismes, annonces, ou toute autre ressource disponible sous forme d'entité Home Assistant.

Chaque file dispose de sa stratégie, de sa capacité, de ses entités supervisées, de son état persistant et de ses capteurs. Les automatisations demandent une réservation, attendent son attribution puis pilotent elles-mêmes les appareils.

> **Versions :** cette documentation est préparée pour la future **v1.1.0 stable**. Toutes les fonctionnalités décrites sont disponibles dans la [pré-release v1.1.0-rc.2](https://github.com/HamzaKarfa/Resource-Queue-Manager/releases/tag/v1.1.0-rc.2). Lors de la préparation de ces fichiers, la dernière version **stable** reste la [v1.0.0](https://github.com/HamzaKarfa/Resource-Queue-Manager/releases/tag/v1.0.0). Vérifie la version réellement installée avant de chercher les nouvelles options.
>
> **Sécurité :** l'intégration ne commande jamais les appareils directement et ne constitue ni un délesteur électrique certifié ni une protection thermique ou contre les surintensités. Les protections physiques restent indispensables.

## Les fonctionnalités de la v1.1

| Fonction | Choix | Comportement par défaut |
| --- | --- | --- |
| Ordonnancement | **FIFO**, **LIFO**, **FIFO prioritaire** | FIFO |
| Capacité | **Classique** ou **Pondéré** | Classique : 1 à 50 places |
| Budget pondéré | **1 à 100 000 unités** entières | Poids initial de chaque entité : 1 |
| Attribution | **Strict** ou **Backfill** | Strict : pas de dépassement de la première demande bloquée |
| Répétitions | **Ignorer** ou **Compter** | Ignorer les répétitions |
| Persistance | Réservations, poids et compteurs sauvegardés | Reprise en pause après redémarrage |
| Multi-files | Plusieurs instances indépendantes | Chaque file dispose de son budget |

La capacité **pondérée** utilise des unités arbitraires, **pas automatiquement des watts**. Il n'existe pas de plafond global entre plusieurs files : chacune possède sa propre capacité.

### FIFO, LIFO et FIFO avec priorité

- **FIFO :** la plus ancienne demande en attente est examinée en premier.
- **LIFO :** la plus récente demande en attente est examinée en premier.
- **FIFO prioritaire :** les demandes sont classées avec `strategy_data.priority` (entier de 1 à 10), puis selon leur ordre d'arrivée si la priorité est égale. Le réglage `priority_order` permet `highest_first` (10 avant 1, défaut) ou `lowest_first` (1 avant 10).

Aucune stratégie n'interrompt une réservation déjà active. L'ordonnancement définit **l'ordre des demandes** ; le mode d'attribution définit si les demandes suivantes peuvent utiliser les unités restantes.

### Strict ou Backfill

Prenons une file de **15 unités**. A utilise déjà 10 unités ; B (10 unités), C (3 unités) puis D (2 unités) arrivent dans cet ordre.

| Ressource | Poids | Strict | Backfill |
| --- | ---: | --- | --- |
| A | 10 | Active | Active |
| B | 10 | Attend | Attend |
| C | 3 | Attend | **Attribuée** |
| D | 2 | Attend | **Attribuée** |
| Total utilisé | — | **10/15** | **15/15** |

- **Strict** (défaut) : B bloque les demandes derrière elle tant que les 5 unités restantes ne suffisent pas.
- **Backfill** : C et D peuvent être attribuées avec les unités libres ; B conserve sa position, son poids et ses récurrences.
- Avec **FIFO prioritaire**, une demande moins prioritaire peut donc passer devant une demande plus prioritaire **qui ne rentre pas**. Une grosse demande peut alors rester longtemps bloquée si de petites demandes continuent d'arriver : **aucune garantie anti-famine** n'est fournie.

[Documentation détaillée de Backfill](docs/V1.2_BACKFILL.md)

### Poids des entités et override temporaire

En mode **Pondéré**, chaque entité supervisée dispose d'un poids par défaut, initialement 1. Il peut être modifié depuis les paramètres de la file.

La valeur `engine_data.weight` modifie le poids **d'une nouvelle demande seulement**, sans changer le poids enregistré de l'entité :

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "ID_DE_LA_FILE"
  resource_id: chauffage_salon
  entity_id: light.relais_chauffage_salon
  engine_data:
    weight: 25
```

Ce poids effectif est **figé** pour toute la durée de la demande, y compris si elle attend ou si Home Assistant redémarre. Il doit être entier, positif et inférieur ou égal au budget de la file. Le mode Classique consomme toujours une place par ressource ; il n'accepte pas l'override pondéré.

### Répétitions : Ignorer ou Compter

Si une demande possède déjà un `resource_id` **en attente** :

- **Ignorer** (défaut) : la demande reste unique, sans incrémentation.
- **Compter** : son compteur d'occurrences passe de 1 à 2, 3, etc., sans ajouter d'entrée supplémentaire, modifier la priorité, déplacer la demande ou consommer davantage d'unités.

Une demande déjà **active** n'incrémente plus son compteur. Une libération ou annulation efface le compteur. Les répétitions doivent conserver la même entité et les mêmes métadonnées de stratégie.

Les compteurs sont disponibles dans l'attribut `occurrence_counts` des capteurs et dans les événements d'attribution. **Compter trois occurrences ne lance pas trois exécutions automatiques**.

## Installation

**Prérequis : Home Assistant 2026.11.0 minimum.**

Pour une **version stable publiée**, ouvre **Paramètres → Marketplace**, recherche *Resource Queue Manager*, installe ou mets à jour puis redémarre Home Assistant. Si nécessaire, ajoute le dépôt :

```text
https://github.com/HamzaKarfa/Resource-Queue-Manager
```

**Attention à la version :** tant que la v1.1.0 stable n'est pas publiée, le canal stable Marketplace/HACS fournit toujours la v1.0.0. Les nouveaux réglages nécessitent la [RC2](https://github.com/HamzaKarfa/Resource-Queue-Manager/releases/tag/v1.1.0-rc.2), à tester de préférence sur une instance Home Assistant séparée.

Avant de mettre à niveau une installation existante, sauvegarde Home Assistant et ses données `.storage`. Évite de mélanger des fichiers de différentes versions dans `custom_components/resource_queue_manager/`. Consulte [la migration v1.0 → v1.1](docs/MIGRATION_v1.0_to_v1.1.md).

## Créer et configurer une file

Dans **Paramètres → Appareils et services → Ajouter une intégration → Resource Queue Manager**, l'assistant présente successivement :

1. **Nom et entités supervisées** : sélectionne les entités HA appartenant à cette file.
2. **Capacité** : Classique (1–50 places) ou Pondéré (1–100 000 unités) et sa limite.
3. **Ordonnancement et attribution** : FIFO, LIFO ou FIFO prioritaire ; Strict ou Backfill.
4. **Paramètres de la stratégie** : uniquement si nécessaires, notamment le sens des priorités.
5. **Demandes répétées** : Ignorer ou Compter.
6. **Poids par entité** : uniquement en mode Pondéré, lorsque des entités sont sélectionnées.

Une entité ne peut pas être supervisée par **deux files simultanément**. Pour créer une autre file indépendante, ajoute une nouvelle instance de l'intégration.

### Modifier une file existante

Clique sur la roue dentée **Configurer** de l'instance concernée. Le menu propose quatre rubriques :

| Rubrique | Paramètres |
| --- | --- |
| **Ressources supervisées** | Entités et poids par défaut si Pondéré |
| **Capacité** | Mode Classique/Pondéré et capacité |
| **Ordonnancement et attribution** | FIFO/LIFO/FIFO prioritaire, Strict/Backfill, paramètres de priorité facultatifs |
| **Demandes répétées** | Ignorer/Compter les occurrences en attente |

Les autres catégories conservent leurs valeurs. **Ouvrir le menu ne met pas la file en pause.** Une modification acceptée déclenche un rechargement : la file redémarre en `paused` et nécessite une commande `resume`.

Impossible de changer une politique (stratégie, capacité Classique/Pondéré, allocation, récurrences) tant qu'il reste des demandes actives ou en attente. Une entité liée à une demande ne peut pas être retirée ; une limite de capacité incompatible avec les poids des réservations est refusée.

[Guide de la nouvelle interface](docs/CONFIGURATION_UI_v1.1-rc2.md)

## Services Home Assistant

Quatre actions sont disponibles dans **Outils de développement → Actions** :

| Action | Champs requis | Champs facultatifs |
| --- | --- | --- |
| `resource_queue_manager.request` | `resource_id`, `entity_id` | `config_entry_id`, `strategy_data`, `engine_data` |
| `resource_queue_manager.release` | `resource_id` | `config_entry_id` |
| `resource_queue_manager.cancel` | `resource_id` | `config_entry_id` |
| `resource_queue_manager.resume` | Aucun | `config_entry_id` |

**Dès qu'il existe au moins deux files configurées, `config_entry_id` est obligatoire pour toutes les actions**. Il s'agit de l'identifiant de l'entrée de configuration Home Assistant, pas du nom de la file ou de la ressource. L'éditeur d'actions permet de sélectionner cette entrée.

### Reprendre une file après rechargement

Les files sont restaurées en pause pour permettre la vérification de leurs réservations et de leurs entités supervisées.

```yaml
action: resource_queue_manager.resume
data:
  config_entry_id: "ID_DE_LA_FILE"
```

Vérifie le capteur `status`, les listes `active` et `waiting`, ainsi que `recovery_issues` avant la reprise. Les attributions déjà actives ne déclenchent pas de nouvel événement à la restauration.

### Exemple : demande prioritaire pondérée

Une file paramétrée en FIFO prioritaire, Pondéré, Backfill et Compter reçoit :

```yaml
action: resource_queue_manager.request
data:
  config_entry_id: "ID_DE_LA_FILE"
  resource_id: lumiere_test
  entity_id: light.lumiere_test
  strategy_data:
    priority: 8
  engine_data:
    weight: 5
```

La priorité doit être fournie sur chaque **nouvelle** demande FIFO prioritaire. Pour répéter cette demande lorsqu'elle attend, conserve les mêmes métadonnées : l'override peut être omis et le poids déjà figé sera conservé.

### Libération et annulation

L'ordre pour un appareil ON/OFF est : **réserver → attendre l'attribution → allumer → éteindre → constater `off` → libérer**.

```yaml
action: resource_queue_manager.release
data:
  config_entry_id: "ID_DE_LA_FILE"
  resource_id: lumiere_test
```

`cancel` permet de retirer une demande en attente. Pour une réservation active associée à un appareil ON/OFF, l'annulation impose également de constater l'état `off`.

Ne considère jamais une simple demande `request` comme une autorisation immédiate : elle peut attendre. Lis l'attribut `active` du capteur de la bonne file ou écoute l'événement `resource_queue_manager_slot_granted`.

![Actions Resource Queue Manager dans Home Assistant](assets/resource-queue-manager-actions.webp)

## Supervision des entités

| Domaines Home Assistant | Contrôles | Condition de libération |
| --- | --- | --- |
| `light`, `switch`, `fan`, `input_boolean` | État `on`/`off` connu, refus de `on` sans réservation active | `off` observé |
| `binary_sensor`, `sensor`, `number`, `text`, `input_number`, `input_text` et autres | Entité présente, état différent de `unknown`/`unavailable` | État connu, **réservation logique uniquement** |

**Important :** même si un `binary_sensor` est binaire, RQM le traite ici comme une ressource logique, **pas** comme un actionneur électrique. Il ne prouve pas qu'un appareil est hors tension.

## Capteurs, événements et diagnostic

Chaque file dispose de **quatre capteurs**. Leurs identifiants réels dépendent du nom et du registre d'entités Home Assistant ; les anciens identifiants sont conservés après migration.

| Suffixe | Valeur |
| --- | --- |
| `_active` | Nombre de réservations actives |
| `_waiting` | Nombre de demandes en attente |
| `_available` | Places (Classique) ou unités (Pondéré) disponibles ; **0 en pause** |
| `_status` | `ready` ou `paused` |

Leurs attributs comprennent `active`, `waiting`, `strategy`, `config_entry_id`, `capacity_mode`, `capacity_unit`, `capacity_total`, `capacity_used`, `capacity_remaining`, `effective_weights`, `allocation_mode`, `recurrence_mode`, `occurrence_counts`, `monitored_entities` et `recovery_issues`.

L'événement `resource_queue_manager_slot_granted` est émis **après sauvegarde** à chaque nouvelle attribution ; il contient `resource_id`, `entity_id`, `config_entry_id`, `capacity_mode`, `allocation_mode`, `effective_weight` et `occurrences`. Il n'est pas rejoué pour les réservations déjà actives après redémarrage.

### Problèmes courants

| Symptôme | Vérification |
| --- | --- |
| Nouvelles options absentes | Vérifier la version installée : la v1.0.0 stable ne les possède pas |
| Menu sans intitulés | Redémarrer Home Assistant et actualiser le navigateur en forçant le rechargement des traductions |
| File en `paused` | Normal après rechargement : vérifier `recovery_issues` puis appeler `resume` |
| Action rejetée pour `config_entry_id` | Indiquer la bonne instance dans toutes les actions si plusieurs files existent |
| 5 unités libres mais aucune attribution | En **Strict**, une demande de poids 10 en tête peut bloquer celles de poids 3 et 2 |
| Priorité refusée | Utiliser `strategy_data.priority` entre 1 et 10 uniquement avec FIFO prioritaire |
| Demande répétée refusée | Vérifier que l'entité, la priorité et le poids figé restent identiques |
| Libération impossible | Pour les domaines ON/OFF supervisés, l'entité doit être réellement à `off` |

## Migration et préparation de la version stable

Les anciennes files v1.0 sont conservées : **Classique + Ignorer + Strict** par défaut en l'absence de nouveaux paramètres, mêmes services et mêmes identifiants de capteurs. Les snapshots contiennent les réservations existantes sans recréer les attributions au redémarrage.

Le retour à la v1.0 après utilisation des nouveaux modes n'est **pas garanti en remplaçant seulement le code** : restaure une sauvegarde cohérente des fichiers, entrées de configuration et données `.storage`.

[Migration détaillée v1.0 → v1.1](docs/MIGRATION_v1.0_to_v1.1.md) · [Historique des versions](CHANGELOG.md) · [Notes de sortie v1.1 préparatoires](docs/releases/v1.1.0-draft.md) · [Validation avant publication](docs/RELEASE_CHECKLIST_v1.1.md) · [Documentation développeur](docs/DEVELOPMENT.md)

**La publication stable v1.1.0 dépend encore de la validation et de l'approbation finales.** Ces README sont préparatoires et ne signifient pas qu'elle est déjà disponible.

Distribué sous [licence MIT](LICENSE).
