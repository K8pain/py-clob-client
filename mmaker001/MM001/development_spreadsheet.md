# MM001 — Development Spreadsheet (MVP Market Maker Paper Trading)

## 1) Definition (qué se construye)

| Campo | Definición |
|---|---|
| Aplicación/feature | `MM001`: simulador paper trading orientado a market making en mercados binarios (YES/NO), con evaluación detallada de PnL por spread, merge/split, rebates, rewards y riesgo de inventario. |
| Usuario objetivo | Quant/dev que necesita validar si la estrategia de maker es rentable antes de pasar a live trading. |
| Problema | Evitar confundir PnL direccional con PnL de provisión de liquidez; medir la economía real del maker en Polymarket-like CLOB. |
| Funcionamiento | State machine `idle -> quote -> partial_fill -> paired_fill -> merge_or_requote -> inventory_rebalance -> emergency_exit` con simulación multi-ciclo y reporte. |
| Conceptos núcleo | `MarketTick`, `QuotePlan`, `Inventory`, `Fill`, `BotMetrics`, `fee_equivalent`, `minimum_net_spread`, `reservation_price`. |

## 2) UX / user stories

| Prioridad | User story | Happy flow | Flujos alternos |
|---|---|---|---|
| P0 | Como operador quiero lanzar un comando único para correr toda la simulación. | `python -m mmaker001.MM001.launcher --all --factory mmaker001.MM001.factory:build_bot` genera resultados. | Si falta `--all`, el launcher corta con mensaje explícito. |
| P0 | Como analista quiero un resumen de PnL por fuente económica. | Se exporta `simulation_summary.json` con breakdown completo. | Si hay edge insuficiente en merge/split, los componentes quedan en 0. |
| P1 | Como dev quiero trazabilidad por ciclo para revisar inventario y skew. | Se exporta `ticks.csv` con mids, quotes y net inventory. | Si inventario deriva, se refleja en `net_yes`. |
| P2 | Como PM quiero priorización clara de roadmap. | Este spreadsheet ordena MVP vs siguiente fase. | N/A |

## 3) Technical design

| Área | Decisión MVP | Evolución futura |
|---|---|---|
| Arquitectura | Módulos simples (`config.py`, `models.py`, `strategy.py`, `bot.py`, `launcher.py`, `factory.py`). | Integrar adapters reales Gamma/CLOB + websocket. |
| Configuración | Todo hardcodeado en `config.py` v3.0. | Migrar a env/flags en v3.1 sin romper contrato. |
| Algoritmo de quoting | Reservation price con inventory skew y spread mínimo neto dinámico. | Avellaneda-Stoikov calibrado por volatilidad real/tiempo a evento. |
| PnL engine | Spread + merge + split-sell + fees/rebates/rewards + MTM residual. | Añadir slippage model, latency model, fills parciales realistas. |
| Persistencia | CSV + JSON de salida en `var/mm001/reports`. | SQLite + event sourcing de decisiones. |
| Dependencias | Solo stdlib Python para MVP portable. | Añadir conectores py_clob_client en modo paper real-data. |

## 4) Testing & security

| Tipo | Objetivo MVP | Estado |
|---|---|---|
| Smoke CLI | Confirmar comando end-to-end y artefactos. | Implementado (manual). |
| Regression deterministic | Seed fija para reproducir resultados. | Implementado en `config.py`. |
| Unit tests | Validar fórmulas (`fee_equivalent`, spread mínimo, reservation skew), launcher y simulación. | Implementado en `tests/MM001`. |
| Coverage gate | Mantener cobertura mínima >85% en módulos core MVP (`bot/strategy/launcher/factory`). | Implementado con test de umbral local sin dependencias externas. |
| Seguridad | No órdenes live, no llaves privadas, sin side-effects de trading real. | Cumplido en MVP. |

## 5) Work plan (priorizado)

| Pri | Tarea | Estimación | Entregable | DoD |
|---|---|---:|---|---|
| P0 | Crear paquete `MM001` y contrato launcher/factory | 0.5d | Comando `--all` operativo | Corre en local y genera reportes |
| P0 | Implementar economics core de market maker | 0.5d | `strategy.py` + `bot.py` con PnL breakdown | `simulation_summary.json` con componentes |
| P0 | Spreadsheet técnico completo | 0.5d | Este documento | Cobertura 1–7 solicitada |
| P1 | Tests unitarios y regresión | 0.5d | `tests/MM001/*` | Fórmulas y run determinista verificados |
| P2 | Integración con datos reales CLOB/Gamma | 1–2d | adapter mode paper-live-data | Sin trading real, con snapshots reales |

## 6) Ripple effects

| Área externa | Impacto |
|---|---|
| Docs operativas | Añadir runbook de MM001 y comparación contra v2. |
| Comunicación interna | Alinear que v3 prioriza MM economics, no señal direccional. |
| Observabilidad | Definir dashboard de `total_realized` vs `directional_mtm`. |

## 7) Broader context / límites y moonshots

| Tema | Estado actual | Futuro |
|---|---|---|
| Limitación principal | Simulación sintética de precios (no orderbook real aún). | Ingesta de book/trades reales por websocket. |
| Riesgo principal | Sobreestimar fills y subestimar adverse selection. | Motor de matching y latencia más realista. |
| Extensiones | Optimización de rebates/rewards ya modelada en fórmula. | Policy optimizer multi-mercado y asignación de capital. |
| Moonshot | Internalizador de full-set con pricing auxiliar LMSR para mercados ilíquidos. | Research track paralelo v4. |

## Backlog funcional por approach profesional

| Pri | Approach | Estado MVP | Próximo incremento |
|---|---|---|---|
| P0 | Spread capture clásico | ✅ Base implementada | Añadir fills parciales reales |
| P0 | Full-set / merge maker | ✅ Edge modelado | Ejecutar merge/split sobre inventario explícito |
| P0 | Inventory-aware adaptive maker | ✅ Reservation + skew | Calibrar skew por volatilidad/tiempo |
| P1 | Reward/rebate optimizer | ✅ término económico incluido | Objetivo por mercado con score de reward real |
