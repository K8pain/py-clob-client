# HLD — MM001 (mmaker001)

## 0) Resumen ejecutivo
MM001 es un motor de **paper trading de market making binario (YES/NO)** orientado a validar economics de provisión de liquidez sobre CLOB (simulado o API real), separando explícitamente el PnL por fuente para evitar decisiones con señal mezclada.

## 0.1) Idea general (práctica): métricas clave + failsafe
- **Objetivo operativo:** correr MM001 en loop corto y decidir rápido si la estrategia está “sana” o debe frenarse.
- **Métricas clave (prioridad):**
  1. `total_realized` (resultado neto real del modelo).
  2. `adverse_taker_ratio` (qué tanto te castiga la salida taker).
  3. `inventory_utilization_ratio` + `net_yes_inventory` (riesgo de inventario atascado).
  4. `win_rate` y `average_pnl_per_cycle` (estabilidad del edge).
- **Failsafe approach (simple):**
  - Si `total_realized` cae de forma sostenida, **detener iteraciones** y volver a modo simulado.
  - Si `inventory_utilization_ratio` sube demasiado, **reducir size** y subir skew/buffers.
  - Si `adverse_taker_ratio` sube, **ensanchar spread mínimo** (`MIN_SPREAD_FLOOR`) antes de reanudar.
  - Reanudar solo después de validar mejora en 2–3 corridas consecutivas.

---

## 1) Define what you’re building

### Qué es la aplicación/feature
MM001 es un bot MVP que ejecuta ciclos de cotización two-sided, simula fills, acumula métricas de desempeño y exporta artefactos operativos (`ticks.csv`, `simulation_summary.json`, logs) en cada iteración del launcher.

### Para quién es
- Trader cuantitativo que quiere validar hipótesis de captura de spread.
- Dev de estrategia que necesita iteración rápida sin capital real.
- Operaciones que requieren observabilidad por ciclo y métricas acumuladas.

### Qué problema resuelve
- Distingue PnL de maker vs PnL direccional residual.
- Permite evaluar impacto de fees/rebates/rewards/inventory skew sin enviar órdenes reales.
- Provee un loop operativo continuo para tuning de parámetros.

### Cómo va a funcionar (vista de alto nivel)
1. `launcher.py` levanta el loop (`--all`), inicializa logs y carga bot vía factory.
2. `factory.py` resuelve el origen de mercado (simulado o CLOB real con uno o varios pares).
3. `bot.py` corre `run_all()` por N ciclos: obtiene tick, construye quotes, simula fills y actualiza métricas.
4. Se persisten reportes y agregados para monitoreo en runtime.

### Conceptos principales y relaciones
- **MarketDataSource (Protocol)**: contrato de mercado para producir `MarketTick`.
  - Implementaciones: `SimulatedOrderBookSource`, `ClobOrderBookSource`, `MultiClobOrderBookSource`.
- **MM001Bot**: orquesta ciclo completo de simulación.
- **Strategy (`strategy.py`)**: calcula spread mínimo neto, reservation price y quotes YES/NO.
- **Inventory / BotMetrics (`models.py`)**: estado y contabilidad.
- **Config (`config.py`)**: parámetros de economics, riesgo, simulación y filtros de mercado.

### Notas de diseño (paralelo, distill, MVP)
- Diseño e implementación ya están acoplados al MVP: configuración central y motor pequeño.
- Distilling del modelo: mantener separación mínima de responsabilidades (launcher/factory/strategy/bot/models).
- Zoom out: robustez de pipeline de simulación y observabilidad.
- Zoom in: exactitud de fórmula de spread neto y penalización taker por ciclo.

---

## 2) Design the user experience

### User stories
#### Happy path A — simulación local
- Como operador, ejecuto `python -m mmaker001.MM001.launcher --all --factory mmaker001.MM001.factory:build_bot --max-runs 1`.
- Obtengo resumen JSON, `ticks.csv`, logs y métricas de PnL por componente.

#### Happy path B — modo API real
- Como operador, configuro token IDs YES/NO (o slug/categoría para autodiscovery).
- El bot consume orderbooks reales y mantiene el mismo esquema de reportes.

#### Alternative flows
- Si el slug/categoría configurado está bloqueado por filtros, la factory ignora ese target y autodiscovera mercados válidos hasta `MAX_SIMULTANEOUS_OB`.
- Si no hay token IDs y no puede resolver ningún par YES/NO con orderbook remoto, la factory corta con `ValueError`.
- Si falla una iteración del loop, `launcher` registra excepción y continúa siguiente iteración.

### Impacto de UI/estructura
No hay UI web (ni se contempla para MM001); el bot corre como servicio remoto en Linux usando CLI + archivos de reporte + logs operativos.
- Navegación funcional: `launcher` → artefactos en `var/mm001/`.
- “Pantalla” principal del usuario: tabla de métricas en log y JSON summary por iteración.

### Mockup/wireframe (operativo CLI)
- Entrada: flags de launcher (`--all`, `--max-runs`, rutas de logs/reports).
- Proceso: iteración continua + `sleep` con `refresh_cache`.
- Salida: `simulation_summary.json` + `cycle_aggregates.jsonl` + `ticks.csv` + logs launcher/trades.

---

## 3) Understand the technical needs

### Detalles técnicos clave
- `net_yes_inventory` = `Inventory.yes - Inventory.no` (posición neta en YES). No existe campo `net_no`; para lectura de lado NO se usa `unpaired_no_qty_total` o las posiciones brutas `yes/no`.
- **Algoritmo de spread neto mínimo**:
  `taker_exit + adverse_buffer + latency_buffer - rebate_expected - reward_expected`, con piso `MIN_SPREAD_FLOOR`.
- **Algoritmo de reservation price**:
  `mid - (inventory.net_yes * INVENTORY_SKEW_FACTOR)` con clamp `[0.01, 0.99]`.
- **Quotes simétricas YES/NO** alrededor del reservation price.
- **Contabilidad por ciclo**: spread, fees taker, incentivos, merge/split, estado de inventario.

### DB/tablas
- No hay persistencia transaccional activa en DB para MM001 MVP.
- `db_path` existe por compatibilidad de contrato de factory/launcher, pero la salida actual es por archivos.

### Diseño general de módulos
- `launcher.py`: ciclo operativo, resiliencia, logging, append de agregados.
- `factory.py`: composición del bot y resolución de fuentes de mercado.
- `bot.py`: simulación de ciclos, integración con data source y cálculo de KPIs agregados.
- `strategy.py`: pricing/quoting puro y reusable.
- `models.py`: dataclasses fuertemente tipadas para estado/métricas.

### Dependencias de terceros
- `tenacity`: retries en pull de orderbook.
- `websockets` (opcional): stream de mercado en tiempo real.
- `py_clob_client`: cliente CLOB para orderbook/discovery.

### Mantenibilidad
- Predomina enfoque de funciones y dataclasses simples.
- Separación de “crear la cosa” (`factory`) de “usar la cosa” (`launcher`/`bot`).
- Uso de `Protocol` para desacoplar fuente de mercado.
- Edge cases cubiertos a nivel de flujo: orderbook vacío, fallo de refresh, fallos por filtros de mercado.

---

## 4) Implement testing and security measures

### Objetivos de cobertura
- Objetivo recomendado MVP: >80% en `strategy.py`, `factory.py`, `bot.py` (paths de negocio).

### Tipos de tests
- Unit tests:
  - fórmulas de `fee_equivalent`, `minimum_net_spread`, `reservation_price`.
  - parser/filtros de mercados y resolución de token IDs.
- Integration tests (sin red real):
  - ejecución de `run_all()` con `SimulatedOrderBookSource`.
  - verificación de generación de artefactos en output dir temporal.
- Regression tests:
  - snapshot de `simulation_summary` con semilla fija.

### Side-effects potenciales
- Ajustes en config pueden cambiar baseline histórico de PnL comparado con corridas anteriores.
- Cambios en discovery API pueden impactar modo autodiscovery de tokens.

### Security checks para ship
- Mantener modo paper (sin envío de órdenes) como comportamiento por defecto.
- Validar que logs no incluyan secretos (token IDs son identificadores públicos de mercado).
- Manejo defensivo de errores de red sin crash total del loop.

### Auditoría de seguridad
- No crítica como trading live, pero sí recomendable para:
  - dependencia de endpoints externos,
  - robustez ante payloads malformados de WS/API.

---

## 5) Plan the work

### Estimación total
- HLD + validación técnica + ajustes menores de doc: **0.5–1 día**.
- Implementación de mejoras posteriores (si se aprueba roadmap): **3–7 días** según alcance.

### Pasos propuestos
1. **Baseline & alineación** (0.5 día)
   - Confirmar objetivos de negocio (captura spread vs inventario).
2. **Testing hardening MVP** (1–2 días)
   - Completar batería unit/integration en módulos core.
3. **Risk controls operativos** (1–2 días)
   - Hard-stop real por `MAX_ABS_INVENTORY` + reglas de emergency exit.
4. **Data quality & observabilidad** (1 día)
   - Métricas de latencia, stale-book ratio y calidad de fills simulados.
5. **Piloto controlado** (1–2 días)
   - Corridas comparativas por mercado/categoría.

### Milestones
- M1: HLD aprobado + criterios DoD.
- M2: test suite estable y reproducible.
- M3: guardrails de inventario en producción de paper mode.
- M4: reporte operativo semanal de desempeño.

### Migraciones
- No requiere migraciones DB en estado actual.
- Si se agrega persistencia histórica estructurada, planificar esquema de eventos por ciclo.

### Riesgos y rutas alternativas
- Riesgo mayor: dependencia de datos externos (API/WS).
- Fallback: modo simulado y cache refresh periódico.

### Definition of Done
**Requerido**:
- Corrida determinista reproducible.
- Métricas separadas por fuente de PnL.
- Artefactos operativos consistentes.

**Opcional**:
- Múltiples mercados simultáneos optimizados.
- Dashboard externo sobre archivos de salida.

---

## 6) Identify ripple effects

### Fuera del código
- Actualizar documentación operativa (`README`, runbook).
- Comunicar a usuarios internos cambios de defaults de configuración.
- Alinear expectativas sobre interpretación de KPIs (ej. `total_realized` vs `directional_mtm`).

### Sistemas externos
- Si se conecta a pipelines de analítica/BI, adaptar parser de `summary_prints.jsonl` y `cycle_aggregates.jsonl`.
- Si se integra con alerting, definir umbrales en `win_rate`, `adverse_taker_ratio`, `inventory_utilization_ratio`.

---

## 7) Understand the broader context

### Limitaciones actuales
- Simulación simplificada de microestructura (sin matching real/partial fills complejos).
- `MAX_ABS_INVENTORY` sirve como referencia de riesgo, no como bloqueo estricto hard-stop en toda ruta.
- Dependencia de salud de endpoints externos para modo API.

### Extensiones futuras
- Motor híbrido paper/live con capa de ejecución real desacoplada.
- Modelado de fill probability por book depth + queue position.
- Optimización automática de parámetros (bandit/Bayesian tuning) sobre métricas históricas.

### Consideraciones de presupuesto/capacidad
- Bajo costo inicial para operar en paper.
- Coste principal está en calibración, monitoring y evolución de modelo de riesgo.

### Moonshot ideas
- Portfolio maker multi-mercado con budget/risk allocator centralizado.
- RL policy para skew dinámico condicionado a régimen de mercado.
- “What-if simulator” interactivo para escenarios extremos de volatilidad/latencia.

---

## Arquitectura lógica (diagrama textual)
`CLI Launcher` -> `Factory` -> `MM001Bot`

`MM001Bot` -> `MarketDataSource` (Simulado | CLOB single | CLOB multi)

`MM001Bot` -> `Strategy` (pricing/quoting) -> `Inventory + Metrics`

`MM001Bot` -> `Reports/Logs` (`ticks.csv`, `simulation_summary.json`, `cycle_aggregates.jsonl`, `summary_prints.jsonl`, launcher/trades logs)
