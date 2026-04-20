# LLD — MM001 (mmaker001)

## Objetivo técnico

Documentar a bajo nivel el flujo real de ejecución de `MM001` como motor de paper-trading de market making para mercados binarios YES/NO.

> Estado actual validado en código: **MM001 no permite fuente de orderbook simulada** en el factory (`ORDERBOOK_SOURCE` debe ser `api`).

---

## 1. Alcance funcional implementado

`MM001` ejecuta ciclos de quoting y PnL sobre datos de orderbook reales (CLOB) y sólo simula la contraparte de fills maker/taker para estimar economics.

### Incluido
- Lectura de orderbook YES/NO desde CLOB:
  - por REST (`get_order_book`),
  - con caché caliente alimentada por WebSocket cuando está disponible.
- Construcción de quotes (`YES/NO bid/ask`) por ciclo.
- Simulación de fills maker/taker para estimar:
  - `spread_pnl`, `merge_pnl`, `split_sell_pnl`,
  - `taker_fees`, `rebate_income`, `reward_income`,
  - KPIs agregados de riesgo/inventario.
- Ejecución por iteraciones desde `launcher` y exportación de artefactos.

### Excluido
- Source de orderbook sintético/simulado en runtime operativo.
- Colocación de órdenes live en exchange.

---

## 2. Arquitectura técnica (módulos y contratos)

## 2.1 Contrato de mercado
`MarketDataSource` (Protocol):
- `next_tick(cycle, previous_mid, rng) -> MarketTick`

Implementaciones productivas:
- `ClobOrderBookSource`: un par YES/NO.
- `MultiClobOrderBookSource`: N pares YES/NO con rotación round-robin y descarte de pares inválidos (404 orderbook).

## 2.2 Orquestación
- `factory.build_bot()`:
  - valida modo `api`, filtros y disponibilidad de orderbooks;
  - instancia `MM001Bot(data_source=...)` con `ClobOrderBookSource` o `MultiClobOrderBookSource`.
- `launcher.main()`:
  - parsea CLI,
  - ejecuta loop de runs,
  - escribe summary y logs agregados.

## 2.3 Núcleo de estrategia
- `strategy.py`:
  - `fee_equivalent`, `minimum_net_spread`, `reservation_price`, `build_quotes`.
- `bot.MM001Bot`:
  - `run_all(output_dir)` para ciclo completo,
  - `_simulate_fill_and_pnl(...)` para economía del ciclo.

---

## 3. Flujo de ejecución detallado

## 3.1 Construcción de bot
1. `build_bot()` valida `MM001_ORDERBOOK_SOURCE == "api"`; cualquier otro valor falla.
2. Evalúa filtros de mercado (`CURRENT_MARKET_CATEGORY`, `CURRENT_MARKET_SLUG`, include/exclude).
3. Si `YES_TOKEN_ID/NO_TOKEN_ID` válidos tienen orderbook: usa ese par.
4. Si no, resuelve pares desde mercados remotos (`get_simplified_markets`) y verifica orderbook por token.
5. Devuelve:
   - `MM001Bot(data_source=ClobOrderBookSource)` si hay 1 par.
   - `MM001Bot(data_source=MultiClobOrderBookSource)` si hay múltiples.

## 3.2 Obtención de tick (`ClobOrderBookSource.next_tick`)
1. `refresh_cache()` intenta mantener estado caliente:
   - si hay mids recientes vía WS (<2s), reutiliza caché.
   - si no, hace fetch paralelo REST de YES y NO (`asyncio.gather`).
2. `_book_mid(token)` calcula mid desde mejor bid/ask; si falta un lado, usa el disponible; si ambos faltan, error.
3. Retorna `MarketTick(cycle, yes_mid, no_mid, spread, market_id)`.

## 3.3 Gestión multi-mercado (`MultiClobOrderBookSource`)
1. `refresh_cache()` recorre fuentes activas.
2. Si una fuente devuelve error 404 de orderbook inexistente, se elimina del pool.
3. `next_tick()` rota con cursor round-robin.
4. Si todas se eliminan, error terminal: `no hay orderbooks configurados`.

## 3.4 Ciclo de negocio (`MM001Bot.run_all`)
Por cada ciclo:
1. Lee `tick` desde `data_source`.
2. Calcula quotes con `build_quotes(tick, inventory)`.
3. Ejecuta `_simulate_fill_and_pnl`:
   - registra órdenes abiertas/ejecutadas por market,
   - aplica maker fill,
   - opcionalmente aplica taker fill por `TAKER_FRACTION`,
   - evalúa edge de `merge` y `split sell`.
4. Actualiza métricas de ciclo (win/loss/breakeven).
5. Persiste fila en `ticks.csv`.

Al final de la corrida:
- calcula KPIs agregados (`win_rate`, `reward_to_fee_ratio`, `inventory_utilization_ratio`, etc.),
- arma `market_orderbooks` con open/executed/canceled/closed por `market_id`,
- retorna summary dict para serialización.

---

## 4. Modelo de datos interno

## 4.1 Estructuras principales
- `MarketTick`: `cycle`, `yes_mid`, `no_mid`, `spread`, `market_id`.
- `Inventory`: `yes`, `no`, `cash`, `net_yes`.
- `Fill`: `side`, `qty`, `price`, `maker`.
- `BotMetrics`: acumuladores de PnL y contadores de performance.

## 4.2 Invariantes operativos
- `MM001Bot` requiere `data_source` explícito.
- Cada ciclo ejecuta exactamente 1 maker fill (`fill_count += 1`) y 0..1 taker fill adicional.
- `maker_notional` y `fill_count` son no decrecientes.
- `market_orderbooks` se construye como unión de llaves de open/canceled/closed/executed.

---

## 5. Configuración crítica

Variables de mayor impacto:
- Fuente y mercado:
  - `MM001_ORDERBOOK_SOURCE` (debe ser `api`),
  - `MM001_YES_TOKEN_ID`, `MM001_NO_TOKEN_ID`,
  - filtros `CURRENT_MARKET_CATEGORY`, `CURRENT_MARKET_SLUG`, `MARKET_INCLUDE_ONLY`, `MARKET_EXCLUDED_PREFIXES`.
- Economía del modelo:
  - `SIMULATION_SIZE`, `TAKER_FRACTION`, `FEE_RATE_BPS`,
  - `ENABLE_PAIR_MERGE`, `MERGE_EDGE_MIN`,
  - `ENABLE_SPLIT_SELL`, `SPLIT_SELL_EDGE_MIN`.
- Ejecución:
  - `SIMULATION_CYCLES`, `SIMULATION_RANDOM_SEED`,
  - `MAX_SIMULTANEOUS_OB`, `MARKET_WS_URL`.

---

## 6. Persistencia y artefactos

No hay DB obligatoria en este módulo.
Salida de ejecución:
- `ticks.csv`: trazabilidad por ciclo.
- `simulation_summary.json`: snapshot de KPIs finales.
- `cycle_aggregates.jsonl` y logs `*.log`: observabilidad operacional.

---

## 7. Manejo de fallos y degradación

- WS caído/no disponible:
  - continúa con REST polling sin abortar proceso.
- Error 404 de orderbook en modo multi:
  - descarta par afectado y sigue con restantes.
- Sin pares válidos:
  - falla construcción o `next_tick` con error explícito.
- Orderbook vacío por token:
  - `ValueError` para cortar ciclo inválido.

---

## 8. Testing técnico recomendado (alineado al código)

- Unit:
  - funciones de `strategy.py`,
  - parseo/resolución de tokens en `factory.py`,
  - ramas de descarte 404 en `MultiClobOrderBookSource`.
- Integración local:
  - `launcher --all --max-runs 1` con doubles de CLOB.
- Regresión:
  - seed fija y verificación de shape de summary + archivos emitidos.
