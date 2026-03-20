# Pergola Bioclimatique — Home Assistant Blueprint

Blueprint Home Assistant pour piloter automatiquement les lames d'une pergola
bioclimatique selon la position du soleil, avec détection d'ensoleillement par
puissance PV et calibration mécanique quotidienne.

## Import rapide

[![Open your Home Assistant instance and show the blueprint import dialog with a specific blueprint pre-filled.](https://my.home-assistant.io/badges/blueprint_import.svg)](https://my.home-assistant.io/redirect/blueprint_import/?blueprint_url=https%3A%2F%2Fgithub.com%2Fqelanhari%2Fha-pergola%2Fblob%2Fmain%2Fblueprints%2Fpergola_bioclimatique.yaml)

Ou manuellement : **Paramètres → Automatisations → Blueprints → Importer un blueprint**.

---

## Logique

### Mode Hiver

L'objectif est de **capter le maximum de lumière directe**.

Le `profile_angle` encode la géométrie complète (élévation + azimut relatif à
la face de la pergola) : il atteint son pic quand le soleil est le plus
directement en face, puis redescend.

En appliquant `max(solar_percent, position_actuelle)` à chaque cycle, la
pergola **monte avec le profil** le matin et **tient naturellement sa position
maximale** l'après-midi quand le soleil repasse derrière — sans aucune condition
sur l'azimut.

```
Matin  : profile_angle croît  →  15% → 30% → 60% → 80%
Pic    : profile_angle atteint son max  →  80%
Après-midi : profile_angle décroît → max() tient  →  80% → 80% → 80%
Soleil trop bas (< seuil standby) : 60%
```

### Mode Été

L'objectif est de **bloquer totalement le rayonnement direct**.

Les lames s'orientent en opposition au soleil (+90°). La course complète
(0 → 100%) est utilisée avant bascule. Dès que 100% ne suffit plus à bloquer
le soleil (`s_raw > max_opening_angle`), les lames repartent à l'autre
extrémité (~0%) sans descente progressive.

```
Matin  : s_raw ≤ 135°  →  ~67% → 100%
Pic    : s_raw = 135°  →  100%
Bascule (s_raw > 135°) : profil − 90° + offset  →  ~0%
Standby / couvert : 60%
```

### Détection ensoleillement

L'ensoleillement est détecté via la **puissance PV lissée** (filtre exponentiel
α = 0,4) comparée à un seuil dynamique calculé selon l'angle d'incidence des
rayons. Un verrou de 15 minutes évite les oscillations en cas de passages
nuageux rapides.

### Calibration quotidienne

Chaque matin (au premier cycle avec une cible valide), les lames se ferment
complètement (référence mécanique à 0°), attendent 45 s, puis reprennent leur
position calculée. La calibration n'est pas re-déclenchée si elle a déjà eu
lieu aujourd'hui.

---

## Prérequis

### Composant Sun

L'intégration **Sun** doit être active (activée par défaut dans HA). Elle fournit
`sensor.sun_solar_azimuth` et `sensor.sun_solar_elevation` utilisés par défaut.

### Helpers à créer

Créer ces helpers dans **Paramètres → Appareils et services → Helpers** :

| Nom suggéré | Type | Paramètres |
|---|---|---|
| `input_select.mode_pergola` | Sélecteur | Options : `Hiver`, `Été`, `Manuel` |
| `input_number.pergola_pv_smooth` | Nombre | Min 0, Max 5000, Step 0.1, unité W |
| `input_boolean.pergola_en_soleil` | Interrupteur | — |
| `input_text.pergola_last_calibration` | Texte | — |
| `input_boolean.pergola_pret` | Interrupteur | — |
| `sensor.pergola_priority_lock_originator` | Template sensor | Voir ci-dessous |

**Exemple de sensor de verrou prioritaire** (template) :

```yaml
template:
  - sensor:
      - name: pergola_priority_lock_originator
        state: >
          {% if states('binary_sensor.pluie') == 'on' %}
            rain
          {% elif states('sensor.temperature_exterieure') | float < 2 %}
            temperature
          {% else %}
            none
          {% endif %}
```

### Automations compagnon

Copier les deux fichiers du dossier `automations/` dans
`config/automations/` (ou les importer via l'UI) :

| Fichier | Rôle |
|---|---|
| `pergola_reset_verrou_matinal.yaml` | Remet `pergola_pret` à `off` à minuit |
| `pergola_deblocage_apres_calibration.yaml` | Active `pergola_pret` une fois la calibration validée et le soleil > 20° |

> Ces deux automations utilisent les noms d'entités du tableau ci-dessus.
> Adapter si vos entités ont des noms différents.

---

## Installation

1. Créer tous les helpers listés ci-dessus.
2. Importer le blueprint (bouton en haut ou URL manuelle).
3. Créer une automation depuis le blueprint et remplir le formulaire.
4. Copier les deux automations compagnon et les adapter si besoin.
5. Activer toutes les automations.

---

## Paramètres du blueprint

### Géométrie

| Paramètre | Défaut | Description |
|---|---|---|
| Azimut de la face | `130°` | Direction vers laquelle les lames font face à 100%. 130° ≈ Sud-Est. |
| Angle max des lames | `135°` | Angle physique correspondant à 100% d'ouverture. |
| Offset de calibration | `-10°` | Correction pour l'imprécision mécanique. Ajuster après observation. |
| Marge de sécurité été | `10°` | Sur-compensation en mode Été pour garantir l'ombre à la bascule. |

### Comportement

| Paramètre | Défaut | Description |
|---|---|---|
| Pas de réglage | `5%` | Résolution des positions. Évite les micro-mouvements. |
| Position standby/couvert | `60%` | Position par temps couvert ou soleil trop bas. |
| Seuil standby | `9%` | En dessous, le soleil est trop bas pour être utile. |
| Seuil humidité de blocage | `80%` | Protection pluie. |
| Élévation solaire minimale | `5°` | Sous cette élévation, l'automation ne s'exécute pas. |
| Puissance PV max | `3000 W` | Puissance crête du capteur PV par ciel dégagé. |

---

## Calibration de l'offset

Après installation, observer la pergola un matin ensoleillé :

- Les lames semblent **trop fermées** → augmenter `calibration_offset` (moins négatif).
- Les lames semblent **trop ouvertes** → diminuer `calibration_offset` (plus négatif).

La procédure : modifier l'offset dans le blueprint, relancer une automation
manuellement, observer. Répéter jusqu'à ce que les lames soient perpendiculaires
aux rayons solaires à mi-journée.

---

## Dépannage

**La pergola ne bouge pas du tout**
→ Vérifier que `input_boolean.pergola_pret` est `on`. Si non, l'automation de
déblocage n'a pas encore tourné (attendre que le soleil passe > 20°).

**La pergola reste à 60% même en plein soleil**
→ La puissance PV ne dépasse pas le seuil dynamique. Vérifier l'entité capteur PV
et ajuster `pv_max_w` à la hausse pour abaisser le seuil.

**La pergola oscille en mode Été**
→ Normal lors de la bascule si `s_raw` oscille autour de `max_opening_angle`.
Augmenter `summer_safety_offset` de 5° pour décaler la bascule.

**La calibration échoue** (pergola ne descend pas à 0)
→ Vérifier que rien ne bloque mécaniquement et que la cover entity répond bien
au service `cover.close_cover_tilt`.

---

## Structure du repo

```
ha-pergola/
├── blueprints/
│   └── pergola_bioclimatique.yaml     # Blueprint principal (import HA)
└── automations/
    ├── pergola_reset_verrou_matinal.yaml
    └── pergola_deblocage_apres_calibration.yaml
```
