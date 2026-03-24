# Tech Dev Sheet — HLD — MVP1

## Bot market maker básico para nuevos mercados crypto de 5 minutos en Polymarket

## 1) Qué estamos construyendo

- **Aplicación / feature**: un blueprint de estrategia de *paper trading* para un bot de provisión de liquidez pasiva en mercados crypto de 5 minutos recién creados en Polymarket.
- **Para quién es**: para developers y traders cuantitativos que quieren validar si existe edge en mercados nuevos sin tocar todavía el flujo de ejecución real.
- **Problema que resuelve**: convierte una idea de market making discrecional en un diseño modular, medible y testeable, centrado en descubrimiento, quoting pasivo, control de inventario y análisis post-trade.
- **Cómo va a funcionar**:
  1. Descubrir mercados nuevos elegibles.
  2. Esperar una ventana corta de estabilización.
  3. Calcular una referencia simple de precio.
  4. Publicar quotes limit *post-only* a ambos lados.
  5. Cancelar/reponer por movimiento, compresión del spread, inventario o cercanía a resolución.
  6. Simular fills y liquidación dentro de un *paper engine*.
  7. Persistir eventos y métricas para análisis posterior.

### Principios de diseño

- **MVP primero**: priorizar el ciclo de vida correcto por encima de cualquier optimización.
- **Zoom out / zoom in**: primero asegurar el flujo completo, luego endurecer cada componente.
- **Distill the model**: el fair value inicial puede ser simplemente `midpoint`.
- **Refactor = quitar complejidad**: evitar ML, hedging y simulación microestructural sofisticada en esta fase.

## 2) User experience / flujo operativo

### Usuario principal

Un developer o quant que ejecuta el sistema en modo paper para responder una pregunta simple:

> “¿Hay EV neto positivo al hacer liquidity provision pequeña y conservadora en mercados crypto nuevos de 5 minutos?”

### Happy path

1. El sistema detecta un mercado nuevo elegible.
2. El mercado entra en estado `STABILIZING`.
3. Tras `stabilization_delay_sec`, se valida libro, spread y frescura de datos.
4. El `signal_engine` genera una decisión de quote.
5. El `inventory_risk_manager` permite o bloquea la exposición.
6. El `paper_execution_engine` registra órdenes resting.
7. Si el libro toca o atraviesa nuestro nivel, se simula fill.
8. A resolución, el sistema liquida posiciones y produce métricas.

### Alternative flows

- **Mercado no elegible**: se descarta en discovery.
- **Libro inmaduro**: permanece en `STABILIZING` o pasa a `NO_QUOTE_WINDOW`.
- **Underlying stale**: no se quotea.
- **Inventario agotado**: se cancela o deja de quote-ar.
- **Falta poco para resolver**: se cancelan órdenes y no se reemplazan.

### UI / visualización MVP

No se propone una UI compleja todavía. La experiencia mínima es:

- salida por consola enriquecida o CSV,
- tablas de mercados operados, órdenes, fills y resumen diario,
- logs detallados para reconstruir decisiones.

### Wireframe textual

```text
+--------------------------------------------------------------+
| MVP1 Session Summary                                          |
+--------------------------------------------------------------+
| markets_seen | markets_quoted | markets_filled | net_pnl      |
| win_rate     | avg_pnl_market | max_drawdown   | cancel_rate  |
+--------------------------------------------------------------+

+--------------------------------------------------------------+
| Active / Resolved Markets                                     |
+--------------------------------------------------------------+
| market_id | asset | state | fills | inventory | pnl | reason |
+--------------------------------------------------------------+

+--------------------------------------------------------------+
| Orders / Fills                                                |
+--------------------------------------------------------------+
| order_id | market_id | side | price | status | cancel_reason |
| fill_id  | market_id | side | price | ts     | resolved_pnl  |
+--------------------------------------------------------------+
```

## 3) Necesidades técnicas

## Arquitectura lógica

```text
market_discovery_service
        ↓
market_candidate
        ↓
market_state_service + underlying_price_service
        ↓
signal_engine
        ↓
inventory_risk_manager
        ↓
paper_execution_engine
        ↓
trade_store
        ↓
post_trade_view
```

### Componentes y responsabilidades

#### A. `market_discovery_service`
- Consulta feed oficial de mercados.
- Detecta `new_market`.
- Filtra mercados:
  - `market_type == crypto`
  - `duration == 5m`
  - `status == active`
  - `accepting_orders == true`
  - `resolved == false`
- Produce `market_candidate`.

#### B. `market_state_service`
- Consume market data websocket.
- Mantiene `best_bid`, `best_ask`, `midpoint`, `last_trade`, `spread`, profundidad y frescura.
- Produce `market_state_snapshot`.

#### C. `underlying_price_service`
- Consume RTDS del subyacente.
- Mantiene precio actual, ancla del quote y movimiento en bps.
- Produce `underlying_state_snapshot`.

#### D. `signal_engine`
- Aplica estabilización.
- Valida libro mínimo.
- Calcula `seed_fair_value`.
- Emite `quote_decision`.

#### E. `inventory_risk_manager`
- Limita exposición por mercado y agregada.
- Limita fills por lado.
- Bloquea quoting si el inventario está desbalanceado.

#### F. `paper_execution_engine`
- Registra órdenes resting.
- Simula fills con enfoque conservador.
- Cancela, expira y liquida a resolución.

#### G. `trade_store`
- Persistencia mínima con `sqlite3`.
- Guarda mercados, snapshots, órdenes, fills, posiciones, resoluciones y métricas.

#### H. `post_trade_view`
- Consola enriquecida o export CSV.
- Resume PnL, fill rate, adverse selection y cancel reasons.

## Reglas funcionales clave

### Elegibilidad

Un mercado es elegible si cumple:

- `market_type == crypto`
- `duration == 5m`
- `status == active`
- `accepting_orders == true`
- `resolved == false`

### Estabilización

No se quotea hasta cumplir:

- `seconds_since_market_open >= stabilization_delay_sec`
- `book_updates_count >= min_book_updates`
- `best_bid != null`
- `best_ask != null`

### Quoting

Se quotea solo si:

- `spread_ticks >= min_spread_ticks`
- `seconds_to_resolution > no_quote_last_sec`
- `inventory_open < max_inventory_per_market`
- `underlying_data_fresh == true`

### Cancel / replace

Cancelar si:

- `abs(underlying_price_now - underlying_price_at_quote) >= cancel_on_move_threshold`
- `spread_ticks < min_spread_ticks`
- `book_stale == true`
- `seconds_to_resolution <= no_quote_last_sec`

### Inventario

- máximo 1 fill por lado por mercado,
- máximo X exposición nominal por mercado,
- máximo Y exposición agregada simultánea.

## Seed fair value del MVP1

### Versión recomendada para arrancar

```text
seed_fair_value = midpoint
yes_quote_price = seed_fair_value - quote_offset
no_quote_price  = (1 - seed_fair_value) - quote_offset
```

### Versión extensible

```text
seed_fair_value =
    w_midpoint * midpoint +
    w_last_trade * normalized_last_trade +
    w_underlying_bias * underlying_direction_bias
```

## Modelo de datos base

La carpeta incluye contratos tipados en `contracts.py` para fijar estados y entidades principales:

- `Mvp1Config`
- `MarketCandidate`
- `MarketStateSnapshot`
- `UnderlyingStateSnapshot`
- `QuoteDecision`
- `PaperOrder`
- `PaperPosition`
- `MarketResult`
- `MarketLifecycleState`
- `SystemState`

## Dependencias propuestas

### Runtime
- Python 3.11+

### Librerías mínimas
- `requests`
- `websocket-client`
- `sqlite3`
- `logging`
- `dataclasses`
- `typing`
- `time`
- `json`
- `threading` o `asyncio`

### Opcionales
- `rich`
- `pydantic`

## 4) Testing y seguridad

### Estrategia de testing

Objetivo: garantizar consistencia de estado, reglas de quoting y simulación conservadora antes de integrar ejecución real.

#### Tests unitarios
- filtros de elegibilidad,
- transición de estados por mercado,
- cálculo de `seed_fair_value`,
- reglas de cancelación,
- límites de inventario,
- criterio conservador de fills.

#### Tests de integración
- flujo end-to-end en paper:
  - market discovery,
  - snapshots,
  - quote decision,
  - resting orders,
  - fills,
  - resolution,
  - PnL final.

#### Tests de regresión
- fixtures con mercados históricos o snapshots grabados,
- validación de KPIs esperados por configuración.

### Objetivos de cobertura

- alta cobertura en lógica de decisión y risk gates,
- cobertura razonable en persistencia y métricas,
- sin obsesión por 100% mientras el diseño siga evolucionando.

### Seguridad para ship interno

- sin firma ni ejecución real en MVP1,
- no almacenar claves privadas,
- validar payloads externos antes de persistir,
- timeouts y reconexión defensiva para websockets,
- usar Enums/dataclasses para evitar estados inválidos.

### Side effects / riesgos

- simulación de fills imperfecta,
- sesgo optimista si el simulador no es conservador,
- alta adverse selection en mercados muy cortos,
- dependencia fuerte de calidad de datos y timestamps.

## 5) Plan de trabajo

## Estimación MVP

- **Diseño + contratos**: 0.5–1 día
- **Discovery + market state + underlying state**: 1–2 días
- **Signal + risk + paper execution**: 2–3 días
- **Storage + metrics + reporting**: 1–2 días
- **Testing + hardening**: 1–2 días

**Total estimado**: ~5.5 a 10 días efectivos para un MVP1 funcional en paper trading.

## Milestones

### Milestone 1 — Skeleton ejecutable
- estructura de módulos,
- config central,
- estados tipados,
- logging base.

### Milestone 2 — Discovery + live state
- descubrir mercados nuevos,
- conectar market data,
- conectar underlying feed,
- detectar stale data.

### Milestone 3 — Quoting core
- estabilización,
- fair value simple,
- creación y cancelación de quotes,
- inventario por mercado.

### Milestone 4 — Paper engine + store
- resting orders,
- fills conservadores,
- liquidación a resolución,
- persistencia sqlite.

### Milestone 5 — Analytics
- KPIs,
- export CSV / consola,
- comparación de configuraciones.

## Definition of Done

### Requerido
- descubre mercados nuevos 5m correctamente,
- quotea solo cuando pasan las reglas,
- registra órdenes/fills/resoluciones sin inconsistencias,
- calcula `net_pnl`, `fill_rate`, `cancel_rate`, `inventory_peak` y `adverse_selection_after_fill`,
- permite variar `stabilization_delay_sec`, `quote_offset_ticks`, `cancel_on_move_bps` y `no_quote_last_sec`.

### Opcional
- dashboards bonitos,
- calibración automática,
- skew dinámico,
- multi-market optimization avanzada.

## Riesgos principales y rutas alternativas

- **Riesgo**: feed de discovery no expone “new market” de forma limpia.
  - **Alternativa**: polling frecuente + deduplicación por `market_id`.
- **Riesgo**: RTDS no es suficientemente estable.
  - **Alternativa**: fallback temporal a fuente secundaria de precio spot.
- **Riesgo**: simulación de fills demasiado burda.
  - **Alternativa**: introducir un `strict_fill_mode` adicional para acotar optimismo.

## 6) Ripple effects

- añadir documentación nueva para la estrategia,
- definir esquema sqlite y política de retención de snapshots,
- preparar ejemplos de ejecución paper para onboarding,
- documentar claramente que MVP1 no realiza trading real,
- si más adelante se activa live trading, revisar firma, custodia de claves y auditoría operativa.

## 7) Contexto más amplio

### Limitaciones actuales del diseño

- fair value muy simple,
- sin hedging,
- sin modelado avanzado de microestructura,
- sin soporte sofisticado para mercados correlacionados,
- sin optimización automática de parámetros.

### Extensiones futuras

- `MVP1.1`: skew por inventario, quote offset dinámico, filtros de calidad de libro.
- `MVP1.2`: agrupación por mercados hermanos, filtro microestructural, cancelación más inteligente.
- `MVP2`: modelo probabilístico simple, evaluación cross-market y simulador de fills mejorado.

### Moonshot ideas

- fair value híbrido entre order book y underlying micro-trend,
- clasificación de mercados “tradeable vs non-tradeable” al nacer,
- simulación contrafactual para comparar múltiples configuraciones sobre el mismo stream.

## Estructura sugerida de implementación futura

```text
src/
  config.py
  main.py
  discovery.py
  market_ws.py
  rtds_ws.py
  signal_engine.py
  risk_manager.py
  paper_execution.py
  storage.py
  metrics.py
  view_console.py
  models.py
```

## Directriz final

Prioridad absoluta de implementación:

1. exactitud del ciclo de vida de mercado,
2. consistencia del estado interno,
3. paper execution conservador,
4. medición robusta,
5. mínima complejidad.

No optimizar demasiado pronto. Primero demostrar que el bot:

- detecta bien,
- quotea bien,
- cancela bien,
- mide bien.

## Implementación inicial en `bin/`

Esta carpeta ya incluye un runtime funcional de referencia en modo paper dentro de `bin/`:

- `bin/services.py`: discovery, estado de mercado, estado de underlying, señal y risk gates.
- `bin/paper_engine.py`: creación de órdenes, fill conservador, cancelación y resolución.
- `bin/storage.py`: persistencia SQLite para mercados, snapshots, decisiones, órdenes, fills y resultados.
- `bin/runner.py`: orquestador end-to-end (`Mvp1MarketMakerBot`) y ciclo demo.
- `bin/main.py`: entrypoint ejecutable para validar el flujo MVP con datos mock.

Ejemplo rápido:

```bash
python -m ToTheMoon.strategies.mvp1_market_maker.bin.main
```
