# Polymarket Engine MVP — How to run (step by step)

Este documento describe una **ruta operativa mínima** para ejecutar el flujo del MVP de forma ordenada y reproducible:

1. Preparar entorno.
2. Descubrir mercados (Gamma).
3. Persistir catálogo local.
4. Descargar histórico (CLOB prices-history).
5. Construir features y señales offline.
6. Ejecutar backtest.
7. Ejecutar paper trading.
8. Preparar modo real con guardrails.

> Objetivo: que cualquier developer/operator pueda correr el pipeline sin ambigüedad y con controles básicos de seguridad.

---

## 0) Qué estás ejecutando

### Qué es
`polymarket_engine` es una capa MVP para workflows de trading sistemático encima de `py-clob-client`, separando:
- discovery/metadatos,
- histórico persistido,
- señal/riesgo/portfolio,
- ejecución paper/real,
- reporting.

### Para quién
- Developers que implementan estrategia.
- Quants/researchers que requieren datasets reproducibles.
- Operadores que necesitan playbook claro de paper → real.

### Principio operativo clave
- **Gamma** para discovery y metadatos.
- **CLOB** para precios/orderbook/histórico/trading.
- El histórico persistido **no** sale del feeder realtime.

---

## 1) Prerrequisitos

## 1.1 Sistema
- Python `>=3.9`.
- `pip` activo.
- Acceso de red a:
  - `https://gamma-api.polymarket.com`
  - `https://clob.polymarket.com`

## 1.2 Variables de entorno sugeridas
Crea `.env` (no commitear secretos):

```bash
POLY_CLOB_HOST=https://clob.polymarket.com
POLY_GAMMA_HOST=https://gamma-api.polymarket.com
POLY_CHAIN_ID=137
POLY_PRIVATE_KEY=<solo_si_real>
POLY_FUNDER=<solo_si_real>
POLY_SIG_TYPE=1
```

## 1.3 Instalación
Desde el root del repo:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

Si ejecutas tests locales del engine:

```bash
PYTHONPATH=. pytest -q tests/polymarket_engine/test_engine.py
```

---

## 2) Estructura de datos operativa

Directorio base recomendado:

```text
data/polymarket_engine/
├── catalog/
│   ├── market_catalog.csv
│   └── token_catalog.csv
├── historical/
│   └── 1h/
│       └── <token_id>.csv
├── execution/
│   ├── order_events.csv
│   └── fills.csv
└── reports/
    └── strategy_summary.csv
```

### Contratos mínimos de CSV

- `market_catalog.csv`: `market_id,event_id,slug,end_date,market_status,tag`
- `token_catalog.csv`: `token_id,market_id,event_id,outcome,yes_no_side,end_date,active`
- `historical/<interval>/<token>.csv`: `token_id,ts,price,interval,fetched_at`
- `execution/order_events.csv`: eventos de orden homogéneos
- `execution/fills.csv`: fills y fee

---

## 3) Paso a paso operativo

## Paso 1 — Discovery (Gamma)

### Objetivo
Descubrir mercados activos y construir catálogo local reusable.

### Flujo
1. Fetch de mercados desde Gamma.
2. Normalizar `market_id/event_id/slug/end_date/status/tag`.
3. Extraer tokens por outcome.
4. Deduplicar por `market_id` y `token_id`.
5. Persistir CSV de catálogo.

### Snippet de ejecución

```python
from ToTheMoon.strategies.polymarket_engine.discovery import GammaDiscoveryClient, discover_catalog
from ToTheMoon.strategies.polymarket_engine.storage import CsvStore

store = CsvStore("data/polymarket_engine")
client = GammaDiscoveryClient("https://gamma-api.polymarket.com")
raw_markets = client.fetch_markets("/markets")
result = discover_catalog(raw_markets)

store.write_rows("catalog/market_catalog.csv", [m.to_row() for m in result.markets])
store.write_rows("catalog/token_catalog.csv", [t.to_row() for t in result.tokens])
```

### Checklist rápido
- ¿Hay `market_catalog.csv` y `token_catalog.csv`?
- ¿No hay duplicados por ids?
- ¿Campos obligatorios no están vacíos?

---

## Paso 2 — Histórico (CLOB prices-history)

### Objetivo
Persistir series históricas reproducibles por token.

### Flujo
1. Cargar `token_catalog.csv`.
2. Llamar CLOB `prices-history` por token e intervalo.
3. Normalizar puntos (`token_id, ts, price, interval, fetched_at`).
4. Append incremental con clave única (`token_id, ts, interval`).

### Snippet

```python
from ToTheMoon.strategies.polymarket_engine.historical import HistoricalDownloader
from ToTheMoon.strategies.polymarket_engine.storage import CsvStore
from ToTheMoon.strategies.polymarket_engine.models import TokenCatalogEntry

store = CsvStore("data/polymarket_engine")
downloader = HistoricalDownloader(
    base_url="https://clob.polymarket.com",
    history_path="/prices-history",
    store=store,
)

# tokens de ejemplo; idealmente cargar desde token_catalog.csv
tokens = [
    TokenCatalogEntry(
        token_id="<token_id>",
        market_id="<market_id>",
        event_id="<event_id>",
        outcome="YES",
        yes_no_side="YES",
        end_date="<end_date>",
        active=True,
    )
]

downloader.download_for_tokens(tokens, interval="1h")
```

### Checklist rápido
- ¿Se crearon archivos por token en `historical/1h/`?
- ¿El append no duplica timestamps ya existentes?
- ¿`fetched_at` está presente?

---

## Paso 3 — Feature building (offline)

### Objetivo
Construir candidatos para:
- estrategia de incoherencias,
- estrategia de colas/extremos.

### Flujo
1. Cargar tokens y precios persistidos.
2. Calcular latest price por token.
3. Generar features:
   - `build_incoherence_features`
   - `build_tail_features`

### Snippet

```python
from ToTheMoon.strategies.polymarket_engine.features import build_incoherence_features, build_tail_features

incoherence_candidates = build_incoherence_features(tokens_yes_only, prices, threshold=0.08)
tail_candidates = build_tail_features(tokens_all, prices, threshold=0.92)
```

### Checklist rápido
- ¿Hay `reason` explícito en cada candidate?
- ¿El lado preferido cumple regla (extremo caro -> NO)?

---

## Paso 4 — Señal + riesgo + snapshot normalizado

### Objetivo
Evitar decisiones con datos inválidos/stale y filtrar por límites.

### Flujo
1. Normalizar snapshot (`midpoint`, `spread`, `stale`).
2. Construir señal (`build_signal`).
3. Evaluar riesgo (`evaluate_risk`).
4. Solo si aprobado, pasar a ejecución.

### Snippet

```python
from ToTheMoon.strategies.polymarket_engine.signal_engine import build_signal
from ToTheMoon.strategies.polymarket_engine.risk import evaluate_risk
from ToTheMoon.strategies.polymarket_engine.normalization import normalize_market_snapshot

snapshot = normalize_market_snapshot(raw_snapshot, stale_after_seconds=30)
signal = build_signal(candidate, strategy_config)
if signal:
    decision = evaluate_risk(order_request, current_positions, risk_config)
```

### Rechazos esperados
- cercano a resolución,
- threshold no superado,
- spread alto,
- snapshot stale,
- límites de riesgo excedidos.

---

## Paso 5 — Backtest offline

### Objetivo
Reproducir lógica core sobre dataset fijo y generar summary.

### Snippet

```python
from ToTheMoon.strategies.polymarket_engine.backtester import run_backtest

summary = run_backtest(candidates, snapshots_by_token, engine_config, store)
print(summary)
```

### Outputs
- `reports/strategy_summary.csv`
- y artefactos de ejecución paper cuando corresponda.

### Checklist reproducibilidad
- misma config + mismo dataset => mismo resultado.
- sin aleatoriedad no controlada.

---

## Paso 6 — Paper trading

### Objetivo
Simular ejecución con reglas conservadoras y persistencia homogénea.

### Snippet

```python
from ToTheMoon.strategies.polymarket_engine.execution import PaperExecutionAdapter

paper = PaperExecutionAdapter(store=store, fee_bps=10)
order_event, fill = paper.execute(order_request, best_bid=snapshot.best_bid, best_ask=snapshot.best_ask)
```

### Outputs esperados
- `execution/order_events.csv`
- `execution/fills.csv`

### KPI mínimos
- `net_pnl`
- `hit_rate`
- `avg_pnl_per_trade`
- `max_drawdown`

---

## Paso 7 — Preparación para modo real

### Objetivo
Cambiar únicamente adapter de ejecución, manteniendo lógica core.

### Estado actual del MVP
`RealExecutionAdapter` entrega payload homogéneo `ready_to_submit`; la integración de envío firmado final con CLOB es el siguiente incremento.

### Guardrails antes de activar real
- credenciales válidas y segregadas por entorno,
- whitelists de mercado/símbolos,
- límites de riesgo más estrictos que en paper,
- alerting en rechazos/errores,
- kill-switch manual.

---

## 4) Troubleshooting operativo

### Error: import de `polymarket_engine` en tests
Usar:

```bash
PYTHONPATH=. pytest -q tests/polymarket_engine/test_engine.py
```

### No llega histórico para token
- verificar token_id activo,
- revisar ventana/intervalo soportado,
- reintentar con backoff,
- registrar respuesta raw para diagnóstico.

### Duplicados en CSV
- confirmar `unique_by=(token_id, ts, interval)` en append,
- no mezclar zonas horarias en timestamps.

### Snapshot stale frecuente
- revisar latencia de feed/fuente,
- aumentar resiliencia de reconexión,
- reducir universo de mercados suscritos.

---

## 5) Seguridad y cumplimiento mínimo para ship interno

- Nunca guardar `PRIVATE_KEY` en CSV ni logs.
- Sanitizar logs de requests/responses.
- Separar `paper` y `real` por configuración explícita.
- Confirmación operativa antes de cualquier submit real.
- Auditoría de cambios de thresholds y límites.

---

## 6) Runbook rápido (orden recomendado)

1. `PYTHONPATH=. pytest -q tests/polymarket_engine/test_engine.py`
2. discovery + persistencia catálogo
3. descarga histórico incremental
4. build de features
5. backtest offline
6. paper trading en ventana controlada
7. revisión de KPIs / incidentes
8. (solo luego) preparar activación real

---

## 7) Qué viene después (next increments)

- script CLI formal para cada paso (`discover`, `download-history`, `backtest`, etc.),
- reconciliación de órdenes/fills para modo real,
- métricas completas de estrategia (incl. drawdown diario),
- scheduler/orquestación robusta,
- dashboard operativo.

