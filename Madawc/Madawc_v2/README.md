# Madawc MVP papertrade bot (Polymarket 5m crypto)

## 1) Definición de lo que se construye
- **Qué es:** un bot 24/7 en Python/Linux para paper trading (sin órdenes reales) en mercados crypto de 5 minutos usando `py-clob-client` como base de integración CLOB.
- **Para quién:** operador que quiere validar señal, ejecución y observabilidad antes de habilitar cuenta real.
- **Problema que resuelve:** reduce riesgo operativo al simular discovery, señales 0.99, pseudo-órdenes y settlement con ledger local persistente.
- **Cómo funciona:** ciclo continuo de `discovery -> clasificación -> watchlist near-expiry -> precio live -> señal -> paper execution -> persistencia`.
- **Conceptos principales:**
  - `MarketRecord` -> mercado operativo.
  - `ClassifiedMarket` -> mercado filtrado `candidate_5m`.
  - `SignalCandidate` -> oportunidad de entrada.
  - `PaperOrder` / `PaperPosition` -> ejecución y resultado paper.
  - `Ledger` -> fondos virtuales y holdings.
  - `MadawcStorage` -> eventos y estado durable.

## 2) UX/operación
- Flujo feliz:
  1. Arranca sin cache.
  2. Descubre mercados activos.
  3. Clasifica 5m crypto.
  4. Observa near-expiry.
  5. Detecta ask=0.99 y crea pseudo-order.
  6. Simula fill y persiste estado.
- Flujos alternativos:
  - Error Gamma/CLOB/WS: retries con backoff+jitter y evento `degraded_*`.
  - Mercado ambiguo: `skipped_ambiguous_interval`.
  - Sin profundidad: `skipped_insufficient_depth`.
  - Señal duplicada: `skipped_duplicate_signal`.

## 3) Necesidades técnicas
- Persistencia local con SQLite:
  - Tabla `state(key, value)` para snapshot de runtime.
  - Tabla `events(...)` para trazabilidad estructurada.
  - Tabla `pseudo_trades(...)` para resultados settlement por pseudo-trade.
  - Exportadores CSV snapshot-safe: `pseudo_trades.csv`, `strategy_summary.csv`, `signal_audit.csv`, `pseudo_orders.csv`.
- Arquitectura:
  - `discovery.py`: universe + refresh sin duplicados.
  - `runtime.py`: sync de tiempo con drift.
  - `signal.py`: regla 0.99 + dedupe + liquidez.
  - `paper.py`: pseudo-limit-order, fill, expiración, settlement.
- `bot.py`: orquestación y adapters intercambiables (`GammaClient`, `ClobClient`, `WsClient`).
  - logging de negocio strategy-first con eventos de decisión y lifecycle (`NO_TRADE`, `SIGNAL_DETECTED`, `PSEUDO_ORDER_*`, `PAPER_POSITION_*`).

## 4) Testing y seguridad
- Unit tests cubren discovery, señal, paper execution, persistence y reintentos.
- No se hacen side-effects reales de trading.
- El engine live futuro cambia solo adapter de ejecución.

## 5) Plan
- Milestone 1: contratos/modelos + discovery/clasificación.
- Milestone 2: señal 0.99 + paper engine + ledger.
- Milestone 3: persistencia + restore + resiliencia.
- Milestone 4: tests de regresión MVP.

## 6) Ripple effects
- Actualizar runbooks y docs operativas al conectar APIs reales.
- Añadir métricas/alertas si se despliega 24/7.

## 7) Contexto amplio
- Estado actual: `Madawc_v2.factory:build_bot` ya conecta adapters REST públicos de Gamma + CLOB para discovery y orderbook.
- No requiere API privada para paper mode (no publica órdenes reales).
- La capa WS sigue como stub saludable por defecto.
- Extensión futura: ejecución live enchufable sin tocar discovery/watch/signal/persistence.

### Requisitos de API para paper mode (estado actual)
- **Necesario:** acceso a endpoints públicos:
  - Gamma: `https://gamma-api.polymarket.com/markets`
  - CLOB: `https://clob.polymarket.com/time` y `.../book`
- **No necesario:** private key ni API key de CLOB mientras se mantenga paper trading.
- Variables opcionales:
  - `MADAWC_GAMMA_BASE_URL` (default `https://gamma-api.polymarket.com`)
  - `MADAWC_CLOB_HOST` (default `https://clob.polymarket.com`)
  - `MADAWC_GAMMA_MIN_INTERVAL_SECONDS` (default `0.25`, ~4 req/s)
  - `MADAWC_CLOB_MIN_INTERVAL_SECONDS` (default `0.05`, ~20 req/s)
  - `MADAWC_LOOP_INTERVAL_SECONDS` (default `240`, 4 minutos entre ciclos)

## 8) Orquestador CLI (operación por terminal/SSH)
Se añadió `Madawc_v2/launcher.py` para operar Madawc desde CLI de forma conveniente.

### Comandos
```bash
# ver ayuda operativa
python -m Madawc_v2.launcher specs

# ejecutar 1 ciclo
python -m Madawc_v2.launcher run-once \
  --factory Madawc_v2.factory:build_bot \
  --db-path var/korlic/korlic.sqlite \
  --log-file var/korlic/korlic-launcher.log

# ejecutar en loop continuo
python -m Madawc_v2.launcher run-loop \
  --factory Madawc_v2.factory:build_bot \
  --interval-seconds 240

# tail del log del launcher (equivalente a tail -f)
python -m Madawc_v2.launcher tail-log --follow

# consultar eventos persistidos en SQLite
python -m Madawc_v2.launcher events --limit 30

# filtrar por tipo de evento
python -m Madawc_v2.launcher events --event-type SIGNAL_DETECTED --limit 50

# exportar reportes CSV
python -m Madawc_v2.launcher export-reports --output-dir var/korlic/reports
```

### Contrato del factory
El launcher espera un `factory` en formato `modulo:funcion` que retorne `MadawcBot`.
Ejemplo:

```python
# Madawc_v2/factory.py
from Madawc_v2.bot import MadawcBot
from Madawc_v2.storage import MadawcStorage


def build_bot(db_path: str) -> MadawcBot:
    storage = MadawcStorage(db_path)
    # construir gamma/clob/ws reales y retornar MadawcBot(...)
    ...
```
