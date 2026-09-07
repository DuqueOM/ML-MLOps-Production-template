# ADR-003: Feast Integration Pattern (External Feature Repo)

## Status

Accepted

## Date

2026-04-19

## Context

ADR-001 defers feature stores with rationale: *"Single-team templates don't need
cross-team feature sharing. Feast/Tecton add significant operational burden."*

However, users eventually reach scale where they **do** need Feast. When they do,
two anti-patterns emerge:

1. **Forking the template** to bake Feast into `templates/service/`. Creates
   divergence from upstream, breaks `new-service.sh` cleanly.
2. **Adding Feast inside the service repo**, mixing feature definitions with
   service code. Couples the release cycle of features to the service.

This ADR defines the **correct integration pattern** when Feast becomes necessary,
without modifying the core template.

## Decision

**Feast lives in a separate repository** (`<org>/feature-repo`). Services in this
template consume Feast as a **client library**, not as embedded infrastructure.

```text
┌──────────────────────────────┐       ┌──────────────────────────────┐
│  <org>/feature-repo          │       │  <org>/<service-name>        │
│  (Feast feature repository)  │       │  (scaffolded from template)  │
│                              │       │                              │
│  - feature_store.yaml        │       │  src/<service>/              │
│  - feature_views/            │       │    ├── schemas.py (Pandera)  │
│    ├── user_features.py      │───────│    └── training/             │
│    └── transaction_fvs.py    │  feast│        └── features.py       │
│  - data_sources.py           │  API  │                              │
│                              │       │  app/main.py                 │
│  Registry: GCS/S3/Postgres   │       │  (uses FeatureStore client)  │
└──────────────────────────────┘       └──────────────────────────────┘
         ▲                                       │
         │                                       │
         └── feast apply ──┐                     │
                           │                     │
                 Feast Online Store              │
                 (Redis / DynamoDB)<─────────────┘
                                  get_online_features()
```

## Rationale

### Why separate repo, not a subdirectory

| Concern | Subdirectory | Separate Repo |
| --- | --- | --- |
| Release cadence | Coupled to service | Independent — features ship on their own cycle |
| Access control | Whoever owns service owns features | Feature team has their own RBAC |
| Reusability across services | Hard (cross-service imports) | Natural — multiple services are Feast clients |
| Fork surface of this template | Must merge Feast into every scaffold | Zero — template untouched |
| CI complexity | Service CI must know Feast | Service CI only calls Feast API |

### Why preserve Pandera instead of replacing with Feast validation

Feast provides **retrieval consistency** (same features train/serve).
Pandera provides **schema validation** (types, ranges, distributions).

They solve different problems. Keep both:

```python
# In src/<service>/training/features.py
from feast import FeatureStore
from <service>.schemas import TrainingSchema  # Pandera schema

store = FeatureStore(repo_path=os.environ["FEAST_REPO_PATH"])
entity_df = pd.read_parquet("entities.parquet")

# Feast retrieval (offline store for training)
training_df = store.get_historical_features(
    entity_df=entity_df,
    features=["user_features:age", "user_features:tenure_days",
              "transaction_fvs:last_7d_amount"],
).to_df()

# Pandera still validates — Feast doesn't know your business rules
TrainingSchema.validate(training_df)
```

### Why serving uses Feast online store, not the training pipeline output

```python
# In app/main.py
from feast import FeatureStore

store = FeatureStore(repo_path=os.environ["FEAST_REPO_PATH"])

@app.post("/predict")
async def predict(request: PredictRequest):
    # Pull the latest features for this entity from the online store
    features = store.get_online_features(
        features=["user_features:age", "user_features:tenure_days"],
        entity_rows=[{"user_id": request.user_id}],
    ).to_dict()

    # Convert to model input (wrap with ThreadPoolExecutor per invariant)
    loop = asyncio.get_event_loop()
    prediction = await loop.run_in_executor(EXECUTOR, model.predict_proba,
                                              features_to_df(features))
    return PredictResponse(score=prediction[0][1])
```

**Invariants from AGENTS.md still apply**: `ThreadPoolExecutor`, single worker,
CPU-only HPA. Feast only changes **where features come from**, not **how inference
runs**.

## Migration Checklist

For a service currently using local `features.py` to migrate to Feast:

### Phase 1 — External feature repo

- [ ] Create `<org>/feature-repo` repository
- [ ] `feast init` inside it; configure `feature_store.yaml` with offline
      (BigQuery/Snowflake/Parquet) and online (Redis/DynamoDB) stores
- [ ] Define Entity objects (e.g., `user = Entity(name="user_id")`)
- [ ] Define FeatureView from existing data source
- [ ] `feast apply` — registers features, creates infra
- [ ] Run `feast materialize-incremental` for first backfill

### Phase 2 — Service client integration

- [ ] Add `feast~=0.40` to `requirements.txt` (compatible release per invariant)
- [ ] Add `FEAST_REPO_PATH` to `.env.example`
- [ ] Update `training/features.py` to use `get_historical_features()`
- [ ] Update `app/main.py` to use `get_online_features()`
- [ ] **Keep Pandera validation** on the DataFrame returned by Feast
- [ ] Add Feast connectivity check to `/health` endpoint
- [ ] Update `tests/` to mock `FeatureStore` (don't require Redis in unit tests)

### Phase 3 — Deployment

- [ ] Add Feast online store connection string to Secret
- [ ] Update `templates/k8s/overlays/*/` to mount the secret
- [ ] Add Feast materialization CronJob (separate from drift CronJob)
- [ ] Grafana dashboard: Feast retrieval latency (critical for P95 SLA)

### Phase 4 — Observability (critical — Feast adds a network hop)

- [ ] Add `feast_retrieval_duration_seconds` Prometheus histogram
- [ ] Alert: P95 retrieval latency > 50ms (online store should be fast)
- [ ] Alert: Feast materialization failure (freshness SLO)
- [ ] Dashboard panel: feature freshness per FeatureView

## Consequences

### Positive

- Core template is unchanged. `new-service.sh` still produces the same scaffold.
- Users opt into Feast when they reach the scale that justifies it (revisit
  trigger from ADR-001: "When the template supports >5 models sharing features")
- Multiple services can share the same feature repo without duplication
- Feature team can operate independently (own repo, own CI, own release cadence)
- Pandera + Feast compose cleanly — no replacement, only addition

### Negative

- Services using Feast become **stateful clients** of an external system. Latency
  depends on online store health. This is a legitimate cost of the pattern.
- Unit tests need to mock `FeatureStore` — adds test complexity
- Feast infrastructure (Redis/DynamoDB) must be operated. Cost and on-call burden.
- Training-serving skew is now a **Feast responsibility**, not a code invariant.
  Must monitor retrieval consistency separately.

### Mitigations

- The migration checklist above explicitly calls out the new SLIs to track
- Service `/health` endpoint must include Feast connectivity — deployments that
  can't reach Feast fail liveness and don't receive traffic
- Grafana panels for Feast retrieval latency and materialization success are
  required (not optional)

## Alternatives Considered

### Alternative 1: Embed Feast in `templates/service/`

**Rejected.** Bakes Feast as a required dependency for all services, violating
ADR-001's Engineering Calibration Principle. Users with 1 model shouldn't need
Feast infrastructure.

### Alternative 2: Templatize a `feature-repo/` alongside `templates/service/`

**Rejected.** Still couples feature repo lifecycle to template releases. Users
benefit more from a pattern document than a template that ages.

### Alternative 3: Use a simpler feature store (e.g., Redis + custom code)

**Rejected.** Misses the point — once you need cross-service feature sharing,
you need Feast's offline/online consistency, point-in-time joins, and materialization.
Rolling your own reproduces a subset poorly.

## Revisit When

- **Feast is replaced by a successor** (Tecton OSS, Hopsworks). Pattern should
  update; principle stays: external feature repo, service as client.
- **Template adds a second example** (multi-model), in which case a shared
  feature repo might belong alongside the examples as a reference implementation.

## References

- ADR-001: Template Scope Boundaries — feature store deferral rationale
- [Feast documentation](https://docs.feast.dev/)
- Invariants preserved from AGENTS.md:
  - `ThreadPoolExecutor` for CPU-bound inference
  - Single uvicorn worker + CPU-only HPA
  - `~=` compatible release pinning for `feast`
