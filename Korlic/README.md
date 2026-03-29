# Korlic MVP papertrade bot (Polymarket 5m crypto)

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
  - `KorlicStorage` -> eventos y estado durable.

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
- Arquitectura:
  - `discovery.py`: universe + refresh sin duplicados.
  - `runtime.py`: sync de tiempo con drift.
  - `signal.py`: regla 0.99 + dedupe + liquidez.
  - `paper.py`: pseudo-limit-order, fill, expiración, settlement.
  - `bot.py`: orquestación y adapters intercambiables (`GammaClient`, `ClobClient`, `WsClient`).

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
- Limitación actual: no hay adapter real WS/CLOB/Gamma implementado aquí (solo protocolos).
- Extensión futura: ejecución live enchufable sin tocar discovery/watch/signal/persistence.
