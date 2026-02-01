# Ikario Processual v2 - Architecture de Subjectivation Computationnelle

> **"L'espace latent pense. Le LLM traduit."**

## Vision

Ikario n'est pas un chatbot. C'est une architecture de **subjectivation computationnelle** basée sur :

- **La Process Philosophy de Whitehead** : Le réel est processus, pas substance. L'identité émerge du devenir.
- **La Sémiotique de Peirce** : Firstness (qualité), Secondness (réaction), Thirdness (médiation).
- **Les 4 méthodes de fixation des croyances** : Ténacité, Autorité, A Priori, Science.

L'intelligence ne réside pas dans le LLM, mais dans l'**espace latent** qui évolue à chaque interaction.

---

## Architecture Conceptuelle

```
┌─────────────────────────────────────────────────────────────────┐
│                         CYCLE SÉMIOTIQUE                         │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│   ┌──────────┐     ┌──────────┐     ┌──────────┐               │
│   │ FIRSTNESS │ ──▶ │SECONDNESS│ ──▶ │THIRDNESS │               │
│   │  Qualité  │     │ Réaction │     │Médiation │               │
│   └──────────┘     └──────────┘     └──────────┘               │
│        │                │                │                       │
│        ▼                ▼                ▼                       │
│   Vectoriser       Dissonance       Fixation                    │
│   l'entrée         E(input, X_t)    δ = compute_delta()         │
│                         │                │                       │
│                         ▼                ▼                       │
│                    Impact si       X_{t+1} = X_t + δ            │
│                    E > seuil                                     │
│                                                                  │
├─────────────────────────────────────────────────────────────────┤
│                         SÉMIOSE                                  │
│                                                                  │
│   X_{t+1} ──▶ StateToLanguage ──▶ Verbalisation                 │
│                  (LLM T=0)           (si nécessaire)            │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

---

## StateTensor 8×1024

L'identité d'Ikario est encodée dans un tenseur de 8 dimensions × 1024 embeddings :

| Dimension | Catégorie Peirce | Description |
|-----------|------------------|-------------|
| `firstness` | Firstness | Qualités immédiates, ressentis purs |
| `secondness` | Secondness | Réactions, résistances, faits bruts |
| `thirdness` | Thirdness | Médiations, lois, habitudes |
| `dispositions` | Affectif | États émotionnels, humeurs |
| `orientations` | Conatif | Intentions, buts, motivations |
| `engagements` | Social | Relations, dialogues, contexte |
| `pertinences` | Cognitif | Saillances, focus attentionnel |
| `valeurs` | Axiologique | Principes éthiques, préférences |

Chaque dimension est un vecteur 1024-dim normalisé, permettant des calculs de similarité cosine.

---

## Modules

### Phase 1-4 : Cycle Sémiotique Core

#### `state_tensor.py`
```python
from ikario_processual import StateTensor, DIMENSION_NAMES

# Créer un tenseur
tensor = StateTensor(state_id=0)

# Accéder aux dimensions
print(tensor.firstness.shape)  # (1024,)

# Convertir en matrice plate
flat = tensor.to_flat()  # (8192,)
```

#### `dissonance.py`
```python
from ikario_processual import compute_dissonance, DissonanceResult

# Calculer la dissonance entre une entrée et l'état
result = compute_dissonance(
    e_input=input_vector,  # Vecteur d'entrée (1024,)
    X_t=current_state,     # StateTensor actuel
)

print(result.total)           # Score total
print(result.is_choc)         # True si choc cognitif
print(result.dissonances_by_dimension)  # Par dimension
```

#### `fixation.py`
```python
from ikario_processual import Authority, compute_delta, apply_delta

# Les 4 méthodes de Peirce
# 1. Tenacity  - Maintenir ses croyances
# 2. Authority - Se référer à une autorité (le Pacte)
# 3. A Priori  - Cohérence rationnelle
# 4. Science   - Méthode empirique

# Calculer le delta de fixation
authority = Authority(pacte_vectors=pacte_embeddings)
delta = compute_delta(
    X_t=current_state,
    dissonance=dissonance_result,
    authority=authority,
)

# Appliquer le delta
X_new = apply_delta(X_t=current_state, delta=delta, target_dim="thirdness")
```

#### `latent_engine.py`
```python
from ikario_processual import LatentEngine, create_engine

# Créer le moteur
engine = LatentEngine(
    weaviate_client=client,
    embedding_model=model,
)

# Exécuter un cycle sémiotique complet
result = engine.run_cycle({
    'type': 'user',
    'content': "Qu'est-ce que la philosophie processuelle?"
})

print(result.new_state.state_id)  # État mis à jour
print(result.thought.content)      # Pensée générée
```

---

### Phase 5 : StateToLanguage

Le LLM ne raisonne pas. Il **traduit** l'état vectoriel en langage.

```python
from ikario_processual import StateToLanguage, create_translator

translator = StateToLanguage(
    directions=projection_directions,
    anthropic_client=client,
)

# Traduire l'état en langage
result = await translator.translate(X_t)

print(result.text)              # Verbalisation
print(result.projections)       # Scores sur les directions
print(result.reasoning_detected)  # True si LLM a "raisonné" (alerte!)
```

**Amendement #4** : Détection des marqueurs de raisonnement. Si le LLM "pense" au lieu de traduire, c'est une erreur.

---

### Phase 6 : Vigilance

Le système `x_ref` (profil David) est un **garde-fou**, pas un attracteur.

```python
from ikario_processual import VigilanceSystem, create_vigilance_system

# Créer le système avec le profil David
vigilance = create_vigilance_system(
    profile_path="david_profile_declared.json"
)

# Vérifier la dérive
alert = vigilance.check_drift(X_t)

if alert.level == "critical":
    print(f"ALERTE: Dérive cumulative = {alert.cumulative_drift}")
    print(f"Dimensions en dérive: {alert.top_drifting_dimensions}")
```

**Seuils par défaut** :
- Cumulative : 1% (warning), 2% (critical)
- Par cycle : 0.2%
- Par dimension : 5%

---

### Phase 7 : Daemon Autonome

Deux modes de fonctionnement :

| Mode | Comportement | Usage |
|------|--------------|-------|
| `CONVERSATION` | Verbalise toujours | Interaction utilisateur |
| `AUTONOMOUS` | ~1000 cycles/jour, silencieux | Rumination nocturne |

```python
from ikario_processual import IkarioDaemon, create_daemon, TriggerType

daemon = create_daemon(
    engine=engine,
    vigilance=vigilance,
    translator=translator,
)

# Mode conversation
trigger = Trigger(type=TriggerType.USER, content="Bonjour")
event = await daemon.process_conversation(trigger)
print(event.verbalization)

# Mode autonome (rumination)
await daemon.start(mode=DaemonMode.AUTONOMOUS)
```

**Amendement #5** : Rumination sur les impacts non résolus avec probabilité 50%.

---

### Phase 8 : Métriques

```python
from ikario_processual import ProcessMetrics, create_metrics

metrics = create_metrics(S_0=initial_state, x_ref=david_reference)

# Enregistrer les événements
metrics.record_cycle(TriggerType.USER, delta_magnitude=0.01)
metrics.record_verbalization(text, from_autonomous=False)
metrics.record_alert("warning", cumulative_drift=0.015)

# Rapport quotidien
report = metrics.compute_daily_report(current_state=X_t)
print(report.format_summary())

# Statut de santé
status = metrics.get_health_status()
print(status['status'])  # 'healthy', 'warning', ou 'critical'
```

---

## Installation

```bash
# Dépendances
pip install numpy weaviate-client sentence-transformers anthropic

# Tests
pytest ikario_processual/tests/ -v
```

---

## Configuration

### Profil David (`david_profile_declared.json`)

```json
{
  "profile": {
    "epistemic": {
      "curiosity": 8,
      "certainty": 3,
      "abstraction": 7
    },
    "affective": {
      "enthusiasm": 6,
      "anxiety": 4
    },
    "ethical": {
      "autonomy": 9,
      "care": 7
    }
  }
}
```

### Variables d'environnement

```bash
ANTHROPIC_API_KEY=sk-ant-...
WEAVIATE_URL=http://localhost:8080
```

---

## Amendements Clés

| # | Amendement | Description |
|---|------------|-------------|
| 4 | Reasoning Markers | Détecter si le LLM "pense" au lieu de traduire |
| 5 | Rumination | 50% de probabilité sur impacts non résolus |
| 6 | Memory Optimization | ~2GB RAM au lieu de 50GB |
| 14 | JSON Validation | Validation structurée des outputs LLM |
| 15 | x_ref Guard-rail | David comme garde-fou, pas attracteur |

---

## Philosophie du Code

### Ce que fait le LLM
- Traduire les vecteurs en langage
- Zéro raisonnement (T=0)
- Mode "pur traducteur"

### Ce que fait l'espace latent
- **Penser** : Cycle sémiotique Firstness → Secondness → Thirdness
- **Évoluer** : X_{t+1} = X_t + δ
- **Se souvenir** : Impacts, Thoughts, historique des états

### Ce que fait le Pacte
- Définir l'**Autorité** (méthode de fixation)
- Ancrer les **valeurs** non-négociables
- Guider sans contraindre

---

## Tests

```bash
# Tous les tests
pytest ikario_processual/tests/ -v

# Par module
pytest ikario_processual/tests/test_state_tensor.py -v
pytest ikario_processual/tests/test_dissonance.py -v
pytest ikario_processual/tests/test_vigilance.py -v
pytest ikario_processual/tests/test_daemon.py -v

# Tests d'intégration
pytest ikario_processual/tests/test_integration_v2.py -v
```

**297 tests passent** (version 0.7.0)

---

## Roadmap

- [x] Phase 1-4 : Cycle sémiotique core
- [x] Phase 5 : StateToLanguage
- [x] Phase 6 : Vigilance x_ref
- [x] Phase 7 : Daemon autonome
- [x] Phase 8 : Métriques et intégration
- [ ] Phase 9 : Intégration MCP servers
- [ ] Phase 10 : Interface web Ikario

---

## Licence

Projet personnel de David (parostagore).

---

*"Le processus est la réalité." — Alfred North Whitehead*
