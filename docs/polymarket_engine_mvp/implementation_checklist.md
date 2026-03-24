# Checklist de implementación MVP

## Discovery y catálogo
- [ ] Consumir Gamma para eventos y mercados activos.
- [ ] Extraer `market_id`, `event_id`, `token_id`, `slug`, `end_date`, `status`, `tags`.
- [ ] Normalizar a `market_catalog.csv` y `token_catalog.csv`.
- [ ] Validar unicidad por `market_id` y `token_id`.
- [ ] Fallar explícitamente ante campos obligatorios ausentes.

## Histórico persistido
- [ ] Descargar `prices-history` desde CLOB por `token_id`.
- [ ] Persistir `token_id`, `ts`, `price`, `interval`, `fetched_at`.
- [ ] Soportar append incremental sin duplicados lógicos.
- [ ] Mantener datasets reproducibles.
- [ ] No usar el realtime feeder como fuente primaria de histórico.

## Realtime feeder
- [ ] Suscribirse solo a mercados elegibles.
- [ ] Mantener snapshot en memoria por mercado.
- [ ] Actualizar best bid, best ask, midpoint, spread y last trade.
- [ ] Marcar estado `stale` por timeout.
- [ ] Reconectar y restaurar suscripciones.

## Feature engineering
- [ ] Construir familias por activo, tipo, fecha y strike implícito.
- [ ] Calcular gaps de monotonicidad.
- [ ] Calcular implied yes/no y `extremeness_score`.
- [ ] Marcar candidatos de señal.

## Señal, riesgo y portfolio
- [ ] Compartir lógica entre paper, backtest y real.
- [ ] Rechazar señales con datos faltantes o cercanía a resolución.
- [ ] Aplicar límites por mercado, globales y por número de posiciones.
- [ ] Recalcular exposición, coste medio y PnL.

## Ejecución
- [ ] Adapter `paper` con fill model conservador.
- [ ] Adapter `real` usando CLOB para crear, firmar y enviar órdenes.
- [ ] Persistir order events, fills, posiciones y settlements.
- [ ] Mantener estructura homogénea de eventos entre modos.

## Backtester y reporting
- [ ] Reproducir cronológicamente la misma lógica de señal y riesgo.
- [ ] Generar `trades_simulated.csv`, `equity_curve.csv`, `strategy_summary.csv`.
- [ ] Garantizar reproducibilidad con config y dataset fijos.
- [ ] Reportar `net_pnl`, `hit_rate`, `avg_pnl_per_trade`, `max_drawdown`.
