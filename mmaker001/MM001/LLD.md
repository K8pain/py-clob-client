# LLD — MM001 (mmaker001)

## Idea general (práctica y concisa)

MM001 debe usarse como un **motor de decisión operativa**, no solo como simulador: en cada corrida, decidir **seguir, pausar o ajustar** usando pocas métricas clave.

### Uso práctico con métricas clave
- **`total_realized`**: semáforo principal de rentabilidad neta por iteración.
- **`net_capture_per_unit_notional`**: eficiencia de captura por notional (comparabilidad entre corridas).
- **`adverse_taker_ratio`** + **`taker_fees`**: presión de costo por salidas taker/adverse flow.
- **`inventory_utilization_ratio`** + `current_inventory_state.unpaired_*`: riesgo de inventario atascado.
- **`reward_to_fee_ratio`**: qué tanto rebates/rewards compensan fricción de fees.

### Failsafe approach (operación)
1. **Modo degradado inmediato:** si CLOB/WS falla, correr `simulated` para no perder continuidad analítica.
2. **Kill-switch operativo:** si `total_realized` cae por debajo de umbral interno o `inventory_utilization_ratio` sube de límite, pausar iteraciones y revisar parámetros.
3. **Reanudación controlada:** retomar con `--max-runs 1` y validar que mejoren `net_capture_per_unit_notional` y `adverse_taker_ratio` antes de volver a loop continuo.

## 1) Define what we are building

### Qué es
`MM001` es un bot de **paper trading** para market making en mercados binarios YES/NO, con dos modos de datos:
- **API/CLOB real** (order book de Polymarket CLOB).
- **Simulado** (fallback/simulación determinista).

El entrypoint operativo es el launcher (`python -m mmaker001.MM001.launcher --all --factory ...`).

### Para quién es
- Operador cuantitativo que necesita validar economics de maker antes de live.
- Dev de estrategia que requiere medición reproducible por componente de PnL.

### Qué problema resuelve
Separa explícitamente los componentes del PnL para evitar decisiones con señales mezcladas:
- `spread_pnl`, `merge_pnl`, `split_sell_pnl`
- `taker_fees`, `rebate_income`, `reward_income`
- `directional_mtm` (residual de inventario)

### Cómo funciona (alto nivel)
1. `launcher.py` valida flags, construye bot vía factory y ejecuta loop de iteraciones.
2. `factory.py` decide si usar fuente simulada o CLOB (single o multi market).
3. `MM001Bot.run_all()` corre N ciclos, genera quotes, simula fills/economics y exporta reportes.
4. Se escriben artefactos (`ticks.csv`, `simulation_summary.json`, logs JSONL).

### Conceptos principales y relaciones
- **`MarketTick`**: snapshot de mercado por ciclo (`yes_mid`, `no_mid`, `spread`, `market_id`).
- **`Inventory`**: estado inventario/caja (`yes`, `no`, `cash`, `net_yes`).
- **`BotMetrics`**: acumuladores de PnL y KPIs.
- **`QuotePlan`**: precios bid/ask de YES y NO.
- **`MarketDataSource` (Protocol)**: contrato para `next_tick(...)`.
- **`SimulatedOrderBookSource` / `ClobOrderBookSource` / `MultiClobOrderBookSource`**: implementaciones de datos.
- **`MM001Bot`**: orquesta simulación y reporte.

> Aplicando “distill the model”: el diseño actual ya favorece módulos simples, flujo explícito y separación clara entre **crear** (`factory`) y **usar** (`launcher`/`bot`) dependencias.

---

## 2) Design the user experience

### User stories (happy + alternativos)

1. **Como operador**, quiero correr una simulación completa con un comando.
   - Happy flow: `--all` + `--factory` válido => corre iteración(es) y genera reportes.
   - Alternativo: falta `--all` => aborta con mensaje explícito.

2. **Como analista**, quiero ver evolución por ciclo y resumen agregado.
   - Happy flow: `ticks.csv` + `simulation_summary.json` + `cycle_aggregates.jsonl`.
   - Alternativo: fallo puntual de iteración => se loguea excepción y el loop continúa.

3. **Como dev**, quiero poder cambiar entre fuente simulada y CLOB por config.
   - Happy flow: `MM001_ORDERBOOK_SOURCE=simulated` usa fuente sintética.
   - Alternativo: en API mode sin token IDs válidos/mercado resoluble => error explícito de factory.

### Impacto UI / navegación
No hay UI gráfica. La UX está en CLI + archivos de salida/log:
- CLI: flags de ejecución.
- Observabilidad: logs tabulares + JSONL + CSV.

### Mockup textual (wireframe CLI)
- Comando: `python -m mmaker001.MM001.launcher --all --factory mmaker001.MM001.factory:build_bot`
- Salidas esperadas:
  - `var/mm001/reports/ticks.csv`
  - `var/mm001/reports/simulation_summary.json`
  - `var/mm001/reports/cycle_aggregates.jsonl`
  - `var/mm001/mm001-launcher.log`

---

## 3) Understand the technical needs

### Componentes y responsabilidades

- `config.py`
  - Parámetros de simulación, economics, filtros de mercados, endpoints CLOB/WS y estados del flujo.

- `models.py`
  - DTOs/dataclasses del dominio (`MarketTick`, `Inventory`, `Fill`, `BotMetrics`).

- `strategy.py`
  - Núcleo de pricing:
    - `fee_equivalent(notional, price, bps)`
    - `minimum_net_spread(price)`
    - `reservation_price(mid, inventory)`
    - `build_quotes(...)`

- `bot.py`
  - Fuentes de mercado (simulada/CLOB) + loop de ciclos + cálculo de métricas + generación de summary.

- `factory.py`
  - Composición/DI: instancia `MM001Bot` con data source correcta según config.

- `launcher.py`
  - Orquestación operacional: parseo args, loop infinito/cotado, persistencia de logs agregados.

### Algoritmo clave
Por ciclo en `run_all()`:
1. Obtiene `tick` desde `data_source.next_tick`.
2. Construye quotes con reservation price + spread mínimo neto.
3. Simula maker round-trip (buy+sell) y suma `spread_pnl`.
4. Modela rebates/rewards esperados sobre fee equivalent.
5. Con probabilidad `TAKER_FRACTION`, agrega costo taker.
6. Evalúa condiciones de edge para `merge_pnl` y `split_sell_pnl`.
7. Actualiza KPIs de performance/inventario y persiste fila CSV.

### Datos persistidos (DB)
No se crean tablas nuevas en este módulo; persistencia actual es por archivos:
- `ticks.csv`
- `simulation_summary.json`
- logs `*.jsonl` y `*.log`

### Dependencias de terceros
- `py_clob_client`: consulta markets/orderbooks en API mode.
- `tenacity`: retry en fetch de orderbook.
- `websockets` (opcional): stream de updates de market.

### Edge cases documentados
- Websocket no disponible/falla: fallback a polling de orderbook vía REST.
- Orderbook vacío para token: lanza `ValueError`.
- Sin `--all`: `SystemExit` controlado.
- Filtros de mercado/token IDs no resolubles: `ValueError` en factory.

---

## 4) Implement testing and security measures

### Testing objetivo
- Cobertura funcional sobre:
  - fórmulas de strategy,
  - construcción de bot por factory,
  - flujo launcher,
  - simulación end-to-end.

### Tipos de test recomendados
- **Unit tests**: `fee_equivalent`, `minimum_net_spread`, `reservation_price`, parseo token IDs/filtros.
- **Regression tests**: run determinista con seed fija (`SIMULATION_RANDOM_SEED`).
- **CLI smoke tests**: ejecución `--all --max-runs 1` y validación de artefactos.

### Seguridad para ship (alcance actual)
- No envía órdenes live desde MM001 (simulación).
- No requiere llaves privadas para funcionamiento base.
- Riesgo operativo principal: dependencia de disponibilidad CLOB/WS en API mode.

### Side effects potenciales
- Aumentar frecuencia del loop o mercados simultáneos puede elevar llamadas a CLOB.
- Cambios en filtros de mercado pueden alterar universo de token IDs elegibles.

---

## 5) Plan the work

### Estimación incremental (LLD -> ejecución)
- **Fase 1 (0.5d):** consolidar requerimientos y límites (simulated vs api).
- **Fase 2 (1d):** hardening de tests de regresión/factory con casos de mercados múltiples.
- **Fase 3 (0.5d):** observabilidad adicional de errores por token/market.
- **Fase 4 (0.5d):** documentación operativa y handoff.

### Milestones
1. LLD aprobado.
2. Regression suite estable y determinista.
3. Runbook operativo actualizado.
4. Validación final de DoD.

### Riesgos y alternativas
- **Riesgo principal:** APIs externas (latencia, 404, payloads cambiantes).
  - **Ruta alternativa:** ejecutar en modo `simulated` para continuidad.
- **Riesgo secundario:** datos WS inconsistentes.
  - **Ruta alternativa:** fallback automático a REST polling.

### Definition of Done
**Requerido**
- Ejecución estable con `--all`.
- Reportes y logs completos por iteración.
- Tests MM001 en verde.

**Opcional**
- Extender métricas por market en modo multi-orderbook.
- Exportar reportes en formato adicional (parquet/sqlite).

---

## 6) Identify ripple effects

### Fuera del código
- Actualizar documentación de operación (`README`, runbook interno).
- Comunicar a usuarios internos cuándo usar `api` vs `simulated`.
- Alinear monitoreo de archivos de salida en pipelines externos.

### Sistemas externos impactados
- Integración con CLOB (disponibilidad y límites de API).
- Dashboards o scripts que consumen `simulation_summary.json`/`ticks.csv`.

---

## 7) Understand the broader context

### Limitaciones actuales
- Modelo de fills simplificado (no microestructura ni parcialidades realistas).
- Inventario no tiene hard-stop estricto por `MAX_ABS_INVENTORY`.
- Persistencia en archivos (no event store transaccional).

### Extensiones futuras
- Motor de matching/fills más realista.
- Adaptador websocket robusto con reconciliación incremental.
- Policy optimizer multi-mercado con asignación de capital.

### Consideraciones de costo/tiempo
- La mayor incertidumbre está en integraciones externas (CLOB/WS), no en la lógica local.
- Prioridad MVP: mantener simplicidad y reproducibilidad por encima de complejidad prematura.

### Moonshot ideas
- Optimización de quoting con calibración Avellaneda-Stoikov por régimen de volatilidad.
- Coordinación cross-market para capturar full-set arbitrage inter-mercado.
