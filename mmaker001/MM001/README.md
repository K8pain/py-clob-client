# MM001 (MVP) — Market Maker Paper Trading Simulator

MM001 es un motor **paper trading** orientado a validar una operativa de **market making en mercados binarios** (YES/NO), consumiendo orderbook real vía API CLOB. Si no hay token IDs configurados, intenta autodiscovery remoto de pares YES/NO con orderbook.

> Ejecuta así (loop continuo para los mercados/token IDs configurados; sin llaves privadas y sin requerir token IDs):
>
> ```bash
> python -m mmaker001.MM001.launcher --all --factory mmaker001.MM001.factory:build_bot
> ```

---

## 1) Qué es, para quién y qué problema resuelve

### Qué es
Un motor de paper trading determinista que cotiza dos lados (YES/NO), evalúa PnL por componentes y exporta reportes.

### Para quién
Para operador/quant/dev que quiere validar si el modelo de maker está capturando edge por:
- spread,
- full-set (merge / split-sell),
- rebates / rewards,
- control de inventario.

### Problema que resuelve
Evita tomar decisiones con PnL “mezclado”. Separa explícitamente:
- `spread_pnl`
- `merge_pnl`
- `split_sell_pnl`
- `taker_fees`
- `rebate_income`
- `reward_income`
- `directional_mtm`

Así puedes distinguir PnL de **proveer liquidez** versus PnL **direccional residual**.

---

## 2) Flujo de uso (step by step)

## Paso 0 — Requisitos
No requiere llaves privadas (modo público). Puede operar con token IDs YES/NO explícitos o resolverlos por autodiscovery remoto.

## Paso 1 — Ejecutar bot en loop continuo
```bash
python -m mmaker001.MM001.launcher --all --factory mmaker001.MM001.factory:build_bot
```

Para pruebas rápidas (una sola iteración):
```bash
python -m mmaker001.MM001.launcher --all --factory mmaker001.MM001.factory:build_bot --max-runs 1
```

## Paso 2 — Revisar salida en consola
El launcher imprime un JSON con métricas agregadas.

## Paso 3 — Revisar artefactos
Se generan en `var/mm001/reports/`:
- `ticks.csv`: trazabilidad ciclo a ciclo (mids, quotes, inventario neto)
- `run_summary.json`: resumen final de PnL por componente
- `cycle_aggregates.jsonl`: snapshot por iteración del loop (timestamp + summary)

Y logs operativos tipo Madawc:
- `var/mm001/mm001-launcher.log`: estado del loop y métricas clave por iteración
- `var/mm001/mm001-trades.log`: evolución ciclo a ciclo (mid, inventario neto, taker_trade, PnL acumulado)

### Métricas dinámicas recomendadas (plan operativo)
- **PnL de spread**: `spread_pnl` y `spread_pnl_cum`.
- **PnL de full-set**: `merge_pnl` y `split_sell_pnl` (acumulado por ciclo).
- **Actividad taker**: `taker_trades`, `taker_trade` por ciclo, `taker_fees`.
- **Inventario**: `net_yes_inventory` final y `net_yes` por ciclo.
- **Resultado neto**: `total_realized` y `total_realized_cum`.

## Paso 4 — Ajustar configuración
Todos los parámetros de la versión 3.0 están hardcodeados en `mmaker001/MM001/config.py`.

## Paso 5 — Re-ejecutar y comparar
Repetir corrida después de ajustes para evaluar sensibilidad de resultados.

---

## 3) Parámetros más importantes de configuración (prioridad de tuning)

> Todos viven en `mmaker001/MM001/config.py`.

## P0 — Economics core (impacto directo en rentabilidad)

### `FEE_RATE_BPS`
Fee base usada en `fee_equivalent = notional * feeRate * p * (1-p)`.
- Si sube, aumenta coste esperado de salidas taker.
- Afecta también estimación de rebates/rewards (vía mismo equivalente económico).

### `ADVERSE_SELECTION_BUFFER`
Margen extra para protegerte contra quotes viejos y flujo informado.
- Alto = menos fills, potencialmente mayor calidad.
- Bajo = más fills, mayor riesgo de edge negativo.

### `LATENCY_BUFFER`
Protección por riesgo de latencia/cancelación tardía.
- Útil cuando hay micro-movimientos más rápidos que la reposición.

### `REBATE_EXPECTED` y `REWARD_EXPECTED`
Se restan del spread mínimo neto requerido.
- Mayor valor esperado permite cotizar más tight manteniendo break-even.

### `MIN_SPREAD_FLOOR`
Piso absoluto de spread aunque el cálculo neto resulte menor.
- Evita “sobre-ajuste” por supuestos optimistas.

## P0 — Inventario y sesgo

### `INVENTORY_SKEW_FACTOR`
Controla cuánto mueve el reservation price ante desbalance inventario.
- Alto: rebalancea más agresivo.
- Bajo: inventario puede desviarse más tiempo.

### `MAX_ABS_INVENTORY`
Guardrail conceptual de riesgo inventario (en MVP aún no bloquea ejecución).
- Recomendado mantenerlo coherente con `SIMULATION_SIZE`.

## P0 — Full-set logic

### `ENABLE_PAIR_MERGE` + `MERGE_EDGE_MIN`
Activa captura de edge cuando `YES + NO < 1`.
- Umbral define cuándo considerar “mergeable edge”.

### `ENABLE_SPLIT_SELL` + `SPLIT_SELL_EDGE_MIN`
Activa lógica espejo cuando `YES + NO > 1` para inventario pre-split.

## P1 — Dinámica del loop

### `SIMULATION_CYCLES`
Cantidad de ciclos simulados.
- Más ciclos = mayor robustez de la muestra.

### `SIMULATION_VOLATILITY`
Rango de shock por ciclo.
- Subirlo incrementa stress de quotes y sensibilidad de inventario.

### `SIMULATION_SIZE`
Tamaño nocional por fill sintético.
- Escala directamente el impacto monetario por trade.

### `TAKER_FRACTION`
Fracción probabilística de salidas con coste taker.
- Mayor valor castiga más el PnL neto.

---

## 4) Funcionamiento detallado (internals)

## 4.1 Launcher y factory
- `launcher.py` parsea flags, exige `--all`, carga `factory` y ejecuta el loop en continuo (con `--max-runs` opcional para cortar).
- Añade logging operativo (`--log-file`, `--trades-log-file`, `--aggregate-log-file`, `--log-level`) para seguimiento dinámico estilo Madawc.
- `factory.py` retorna `MM001Bot` (contrato simple compatible con launcher).

## 4.2 Estado y modelos
- `Inventory`: posiciones YES/NO + cash
- `BotMetrics`: acumuladores de PnL por fuente
- `MarketTick`: snapshot por ciclo

## 4.3 Quoting engine (`strategy.py`)
1. Calcula fee equivalente en función de precio binario.
2. Calcula `minimum_net_spread`:
   - coste esperado de salida taker
   - + adverse buffer
   - + latency buffer
   - - rebate esperado
   - - reward esperada
   - con piso `MIN_SPREAD_FLOOR`
3. Calcula `reservation_price` con skew por inventario.
4. Construye quotes two-sided para YES/NO.

## 4.4 Simulación (`bot.py`)
Por ciclo:
1. Genera nuevo `mid` con shock controlado por volatilidad.
2. Construye quotes con estrategia.
3. Suma PnL por spread maker round-trip simulado.
4. Suma rebates/rewards esperados.
5. Aplica penalización de taker según `TAKER_FRACTION`.
6. Evalúa edge de merge/split y acumula cuando supera umbral.
7. Exporta tracking en `ticks.csv`.

Al final:
- calcula `directional_mtm` residual,
- arma `run_summary.json`,
- incluye `taker_trades` en el resumen.

---

## 5) Seguridad, testing y validación operativa

- No envía órdenes reales.
- No usa credenciales privadas.
- Suite de tests en `tests/MM001/test_mm001.py` cubre:
  - fórmulas core,
  - launcher,
  - flujo principal,
  - umbral de coverage >85% (módulos core).

Comandos recomendados:
```bash
pytest -q tests/MM001
python -m mmaker001.MM001.launcher --all --factory mmaker001.MM001.factory:build_bot

multitail -n 5 \
  var/mm001/mm001-launcher.log \
  var/mm001/mm001-trades.log \
  var/mm001/reports/cycle_aggregates.jsonl \
  var/mm001/reports/ticks.csv

---

## 6) Limitaciones actuales (MVP)

1. No hay matching real ni partial fills realistas de microestructura.
2. `MAX_ABS_INVENTORY` está definido pero no fuerza hard-stop aún.

---

## 7) Próximos pasos recomendados

1. Conectar book/trades reales (paper mode) manteniendo la contabilidad actual.
2. Activar guardas duras de inventario y emergency exit basado en riesgo.
3. Calibrar `INVENTORY_SKEW_FACTOR` y buffers con data real.
4. Añadir benchmark por mercado (rebate/reward efficiency por unidad de riesgo).
