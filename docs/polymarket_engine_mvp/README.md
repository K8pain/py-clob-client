# MVP blueprint: Polymarket Engine para incoherencias y colas

## 1) Qué estamos construyendo

### Aplicación / feature
Un paquete mínimo de arquitectura, workflows y contratos de datos para implementar un bot de Polymarket con dos estrategias:
- **Incoherencias** entre mercados relacionados.
- **Colas/extremos** en mercados con pricing desalineado cerca de 0 o 1.

### Para quién es
Para developers que quieren construir un stack correcto y mantenible encima de `py-clob-client`, separando discovery, research, paper trading, backtesting y ejecución real.

### Problema que resuelve
Evita mezclar responsabilidades y elimina un anti-pattern frecuente: usar el feeder realtime como fuente principal del histórico o duplicar la lógica entre paper y real trading. El objetivo es dejar explícito qué usa **Gamma** y qué usa **CLOB**, cómo se persiste el histórico y cómo se comparte la lógica core.

### Cómo va a funcionar
1. **Discovery** consulta Gamma y genera un catálogo local reusable.
2. **Historical downloader** consulta CLOB prices-history y guarda CSV reproducibles por token.
3. **Normalization + feature builder** transforman catálogo e histórico en datasets aptos para research, backtest y señal.
4. **Realtime feeder** consume WebSocket de CLOB solo para mercados elegibles y mantiene snapshots en memoria.
5. **Signal engine** usa datos normalizados y emite señales compartidas por paper y real.
6. **Risk + portfolio** validan límites y mantienen estado coherente.
7. **Execution adapters** cambian solo la capa de ejecución: `paper` o `real`.
8. **Reporting** resume trades, PnL, drawdown y motivos.

### Conceptos principales y relaciones
- **Event**: grupo lógico de mercados descubierto en Gamma.
- **Market**: mercado operable con metadatos, estado y fecha de resolución.
- **Token**: outcome negociable en CLOB; unidad mínima para market data e histórico.
- **Catalog**: vista local normalizada de eventos, mercados y tokens.
- **Market snapshot**: estado realtime de bid/ask/mid/spread/last trade por token.
- **Historical series**: CSV persistido por token e intervalo.
- **Feature family**: agrupación de mercados hermanos para detectar monotonicidad o extremos.
- **Signal**: propuesta operativa con motivo, dirección y confianza.
- **Order / Fill / Position**: eventos y estado operativos persistidos.
- **Execution mode**: `paper` y `real`, ambos consumiendo la misma señal.

### Criterios rectores del diseño
- Diseñar e implementar en paralelo, empezando por un **MVP de bajo acoplamiento**.
- Quitar complejidad innecesaria: **solo Gamma + CLOB** como APIs externas mínimas.
- Priorizar funciones pequeñas, módulos explícitos y contratos CSV estables.
- Mantener separadas las rutas **discovery**, **histórico**, **realtime**, **backtest** y **trading**.

---

## 2) UX / Developer experience

Aunque el repo actual no expone una UI final, sí necesita una experiencia clara para el developer y operador.

### Historias de usuario principales
1. **Discovery happy path**
   - Como developer, quiero ejecutar un comando de discovery para generar el catálogo local sin depender del feeder realtime.
2. **Historical data happy path**
   - Como researcher, quiero descargar histórico por `token_id` e intervalo para reconstruir datasets idénticos.
3. **Paper trading happy path**
   - Como operador, quiero correr el bot en modo paper con la misma señal y riesgo del modo real.
4. **Backtesting happy path**
   - Como quant/dev, quiero correr un backtest offline sobre CSV persistidos y obtener outputs reproducibles.
5. **Real trading happy path**
   - Como operador, quiero cambiar solo el adapter de ejecución para pasar de `paper` a `real`.

### Flujos alternativos / edge flows
- Si Gamma falla, discovery no debe contaminar el catálogo anterior; debe fallar de forma explícita.
- Si CLOB WebSocket se desconecta, el feeder debe reconectar y marcar snapshots como `stale`.
- Si faltan datos mínimos, el motor de señal debe rechazar la oportunidad con un motivo persistido.
- Si el mercado está demasiado cerca de resolución, riesgo o señal deben bloquear la orden.

### Propuesta de interfaz operativa mínima
No hace falta una UI visual para el MVP. Basta con una interfaz por comandos/scripts:
- `discover_markets`
- `download_history`
- `build_features`
- `run_realtime_feeder`
- `run_paper_bot`
- `run_backtest`
- `run_real_bot`
- `generate_report`

### Wireframe textual de navegación
```text
polymarket_engine_app/
 ├── config/
 ├── data/
 │   ├── raw/
 │   ├── catalog/
 │   ├── historical/
 │   ├── execution/
 │   └── reports/
 ├── core/
 ├── execution/
 ├── storage/
 ├── backtester/
 └── scripts/
```

La “UX” del developer se centra en que cada workflow tenga:
- inputs explícitos,
- outputs persistidos,
- logging estructurado,
- y una sola responsabilidad.

---

## 3) Necesidades técnicas

### Principios técnicos
- **Gamma**: discovery y metadatos.
- **CLOB**: market data, prices-history, order book y trading.
- **CSV**: almacenamiento inicial.
- **Datos normalizados**: requisito obligatorio antes de decidir señal o riesgo.
- **Core compartido**: señal, riesgo y portfolio deben ser comunes a paper, backtest y real.

### Árbol propuesto para implementar
```text
polymarket_engine_app/
├── README.md
├── config/
│   ├── settings.py
│   ├── markets.py
│   └── thresholds.py
├── data/
│   ├── raw/
│   │   ├── gamma/
│   │   └── clob/
│   ├── catalog/
│   │   ├── market_catalog.csv
│   │   └── token_catalog.csv
│   ├── historical/
│   │   └── prices/
│   │       └── <interval>/<token_id>.csv
│   ├── execution/
│   │   ├── order_events.csv
│   │   ├── fills.csv
│   │   ├── positions.csv
│   │   └── settlements.csv
│   └── reports/
│       ├── trades_simulated.csv
│       ├── equity_curve.csv
│       └── strategy_summary.csv
├── discovery/
│   ├── gamma_client.py
│   ├── models.py
│   ├── normalizer.py
│   └── service.py
├── market_data/
│   ├── clob_snapshot_client.py
│   ├── websocket_feeder.py
│   ├── state_store.py
│   └── freshness.py
├── historical/
│   ├── clob_history_client.py
│   ├── downloader.py
│   └── partitioning.py
├── normalization/
│   ├── catalog_loader.py
│   ├── market_mapper.py
│   ├── price_series.py
│   └── validators.py
├── features/
│   ├── family_builder.py
│   ├── incoherence_features.py
│   └── tail_features.py
├── core/
│   ├── signal_engine.py
│   ├── risk_manager.py
│   ├── portfolio.py
│   ├── models.py
│   └── enums.py
├── execution/
│   ├── base.py
│   ├── paper.py
│   ├── real.py
│   ├── order_mapper.py
│   └── fee_model.py
├── storage/
│   ├── csv_store.py
│   ├── catalog_store.py
│   ├── history_store.py
│   ├── execution_store.py
│   └── report_store.py
├── reporting/
│   ├── metrics.py
│   ├── summary.py
│   └── exporters.py
├── backtester/
│   ├── runner.py
│   ├── replay.py
│   ├── fills.py
│   └── result_writer.py
└── scripts/
    ├── discover_markets.py
    ├── download_history.py
    ├── build_features.py
    ├── run_paper_bot.py
    ├── run_backtest.py
    ├── run_real_bot.py
    └── generate_report.py
```

### Relación entre módulos
- `discovery` produce catálogo persistido.
- `historical` usa `token_catalog.csv` como entrada y produce series CSV.
- `normalization` carga catálogo + histórico y valida integridad.
- `features` construye datasets para estrategias.
- `core` decide señal/riesgo/estado de portfolio.
- `execution` materializa órdenes en paper o real.
- `storage` define contratos de persistencia CSV.
- `backtester` reusa `core` y `storage` sobre datasets offline.

### Contratos CSV mínimos

#### `market_catalog.csv`
Campos sugeridos:
- `market_id`
- `event_id`
- `slug`
- `question`
- `market_status`
- `accepting_orders`
- `end_date`
- `tag`
- `outcome_count`
- `updated_at`

#### `token_catalog.csv`
Campos sugeridos:
- `token_id`
- `market_id`
- `event_id`
- `outcome`
- `yes_no_side`
- `min_tick_size`
- `min_order_size`
- `active`
- `end_date`
- `updated_at`

#### Histórico por token
Campos obligatorios:
- `token_id`
- `ts`
- `price`
- `interval`
- `fetched_at`

#### Ejecución
- `order_events.csv`: `event_id`, `order_id`, `token_id`, `status`, `side`, `price`, `size`, `created_at`, `reason`
- `fills.csv`: `fill_id`, `order_id`, `token_id`, `price`, `size`, `fee`, `ts`
- `positions.csv`: `position_id`, `token_id`, `net_qty`, `avg_cost`, `realized_pnl`, `unrealized_pnl`, `updated_at`
- `settlements.csv`: `token_id`, `resolved_price`, `resolved_at`, `gross_pnl`, `net_pnl`

### Algoritmos / lógica clave

#### Estrategia de incoherencias
- Agrupar mercados hermanos por activo, tipo, fecha y strike implícito.
- Ordenar por strike/threshold esperado.
- Calcular monotonía esperada y gaps observados.
- Señalizar solo si el gap supera `threshold_incoherence`.
- Identificar lado favorecido y persistir motivo exacto.

#### Estrategia de colas
- Calcular `implied_prob_yes` y `implied_prob_no`.
- Medir `time_to_resolution`.
- Asignar `bucket` o `extremeness_score`.
- Marcar candidatos donde el extremo esté “caro”.
- Preferir `NO` cuando un escenario extremo esté sobrepagado.

### Diseño de tipos
Se recomienda usar `dataclasses` y `Enum` para evitar estados inválidos:
- `SignalType`, `SignalSide`, `OrderStatus`, `ExecutionMode`, `MarketFreshness`
- `SignalCandidate`, `ApprovedSignal`, `RiskDecision`, `PositionSnapshot`, `MarketSnapshot`

### Dependencias externas mínimas
- **Ya disponible**: `py_clob_client` para CLOB. La librería del repo ya cubre autenticación, order book, precios y órdenes. `README.md` y `setup.py` muestran que este repo es el cliente Python del CLOB y que expone operaciones read-only y de trading. 【F:README.md†L1-L5】【F:README.md†L18-L33】【F:setup.py†L1-L25】
- **Nueva dependencia externa mínima**: cliente HTTP simple para Gamma si todavía no existe wrapper local.
- **Evitar** agregar bases de datos, colas, orquestadores o frameworks pesados en el MVP.

### Edge cases a documentar
- reconexión WS,
- snapshots stale,
- duplicados en catálogo,
- append incremental con timestamps repetidos,
- mercados cerrados o muy cerca de resolución,
- órdenes rechazadas/canceladas parcialmente,
- inconsistencias entre fills y posición.

---

## 4) Testing y seguridad

### Objetivo de cobertura
Cobertura razonable sobre la lógica core y contratos CSV; no perseguir 100% en integración externa.

### Tipos de tests necesarios
- **Unit tests**
  - normalización de catálogo,
  - detección de duplicados,
  - feature builders,
  - signal engine,
  - risk manager,
  - portfolio math.
- **Regression tests**
  - datasets de ejemplo para incoherencias y colas.
- **Integration tests**
  - parsing de respuestas Gamma,
  - lectura/escritura CSV,
  - mapping de `token_id` ↔ outcome,
  - adapter paper.
- **End-to-end smoke tests**
  - discovery → history → features → backtest.

### Checks de seguridad / ship criteria
- Secrets fuera del repo.
- Validación estricta de modo `paper` vs `real`.
- Confirmar host, chain id y credenciales antes de enviar órdenes reales.
- Logging estructurado sin exponer private keys ni API creds.
- Guard-rails para impedir operar en mercados cerrados o sin datos frescos.

### Posibles side effects
- Si se modifica el formato CSV, backtester y reporting pueden romperse.
- Si cambia el mapping Gamma/CLOB, las señales pueden degradarse silenciosamente.
- Si el adapter real no comparte exactamente la lógica core, paper deja de ser proxy útil del bot real.

---

## 5) Plan de trabajo

### Estimación de alto nivel
- **Fase 1 — Fundaciones (2-3 días)**
  - config,
  - storage CSV,
  - discovery Gamma,
  - validadores de catálogo.
- **Fase 2 — Datos históricos (2 días)**
  - downloader CLOB prices-history,
  - append incremental,
  - validación de integridad.
- **Fase 3 — Normalización + features (2-4 días)**
  - familias,
  - monotonicidad,
  - tail buckets.
- **Fase 4 — Core operativo (2-3 días)**
  - signal,
  - risk,
  - portfolio.
- **Fase 5 — Paper + backtester (3-4 días)**
  - adapter paper,
  - replay offline,
  - métricas y reports.
- **Fase 6 — Real bot (2-3 días)**
  - adapter real,
  - manejo de estados/fills,
  - hardening operativo.

### Milestones
1. **M1**: catálogo persistido y validado.
2. **M2**: histórico descargable y reproducible.
3. **M3**: features y señales offline.
4. **M4**: paper trading funcional.
5. **M5**: backtester reproducible.
6. **M6**: adapter real conectado a CLOB.

### Riesgos principales
- Mapping correcto entre discovery Gamma y `token_id` de CLOB.
- Calidad/completitud de prices-history para algunos mercados.
- Reconexión y frescura del WS en producción.
- Modelado realista de fills paper sin sobreajustar.

### Rutas alternativas
- Si la agrupación avanzada por familias resulta costosa, arrancar con reglas deterministas simples por `slug`, fecha y outcomes.
- Si el paper fill model es demasiado complejo, empezar con una versión conservadora basada en bid/ask y añadir profundidad luego.
- Si reporting completo toma tiempo, priorizar `strategy_summary.csv` y `equity_curve.csv`.

### Definition of Done
**Requerido**
- discovery,
- histórico persistido,
- normalización,
- features para ambas estrategias,
- señal compartida,
- riesgo compartido,
- paper bot,
- backtester reproducible,
- adapter real base,
- reporting mínimo.

**Opcional**
- parquet/db,
- dashboard UI,
- múltiples modelos de fill,
- optimización automática de thresholds.

---

## 6) Ripple effects

### Documentación a actualizar
- README principal del repo con enlace a esta arquitectura.
- Ejemplos de uso para Gamma discovery y workflows de bot.
- Guía operativa de paper vs real.

### Comunicación a usuarios existentes
- Aclarar que este repo sigue siendo el cliente CLOB base, y que el bot MVP vive como capa superior reusable.
- Explicar que el histórico persistido no proviene del realtime feeder.

### Otros sistemas / procesos
- Gestión de secrets y `.env`.
- CI para tests unitarios + smoke tests.
- Rotación/retención de logs y artefactos CSV.

---

## 7) Contexto más amplio

### Limitaciones del diseño actual
Este repositorio está centrado en el **cliente Python del CLOB**, no en una aplicación completa de trading. El README y el packaging muestran foco en acceso a precios, order books y órdenes, pero no incluyen una arquitectura integral de bot con discovery Gamma, histórico persistido, backtester y reporting. 【F:README.md†L1-L5】【F:README.md†L79-L93】【F:setup.py†L1-L25】

### Extensiones futuras posibles
- Migrar de CSV a Parquet/DuckDB.
- Motor de features incremental.
- Ejecución multi-estrategia.
- Soporte para múltiples intervalos y resampling.
- Servicio de reconciliación de fills/posiciones.
- Dashboard operativo y notebooks de research.

### Moonshot ideas
- Ranking automático de familias con mayor probabilidad de incoherencia.
- Sistema de etiquetado histórico de régimen de mercado.
- Aprendizaje supervisado para priorizar señales, manteniendo reglas duras de riesgo.

### Restricciones de presupuesto / complejidad
Para el MVP conviene mantener:
- pocas dependencias,
- almacenamiento simple,
- trazabilidad máxima,
- y reemplazar complejidad por contratos de datos explícitos.

---

## Workflow E2E resumido

```text
Gamma discovery
  -> market_catalog.csv / token_catalog.csv
  -> CLOB prices-history downloader
  -> historical CSV dataset
  -> normalization + features
  -> signal engine
  -> risk manager
  -> execution adapter (paper | real)
  -> execution CSVs
  -> reporting / backtester outputs
```

## Decisiones no negociables del MVP
- No usar el feeder realtime como fuente primaria de histórico.
- No duplicar lógica entre `paper` y `real`.
- No permitir decisiones con datos sin normalizar.
- No mezclar discovery/metadatos con operativa realtime.
- No introducir almacenamiento pesado antes de validar el workflow.
