# Madawc - SIMPLEST market making form

## Operativa (MVP)

- Bot derivado de `Madawc_v2`, copiado en `Madawc/`.
- En cada mercado **nuevo** elegible, publica **dos limit BUY orders** a **5c (0.05)**:
  - 1 orden para el outcome `UP`.
  - 1 orden para el outcome `DOWN`.
- Tamaño por orden: **20 shares** (stake de **$1** por orden).
- No se ejecutan ventas manuales: **solo BUY** y las órdenes no llenadas se dejan expirar localmente (igual que Madawc).
- Filtro de mercados: solo se opera si el título contiene `Up or Down` usando `ONLY_TRADE_THIS_MARKETS` en `config.py`.
- Salida opcional de posiciones (`EXIT_AT_FLAT`):
  - `MADAWC_EXIT_AT_FLAT_ENABLED=true` activa una salida temprana de posiciones ya llenadas.
  - `MADAWC_EXIT_AT_FLAT=<N>` define el múltiplo sobre el precio de entrada para vender.
  - La salida se evalúa como **limit SELL simulada**: si no hay profundidad bid suficiente al target, queda esperando fill.
  - Ejemplo: entrada a `0.01` y `MADAWC_EXIT_AT_FLAT=10` -> target de salida `0.10` (si hay bid disponible).

## 1) Qué estamos construyendo

Un bot de market making mínimo para mercados binarios tipo “Up or Down”. Está pensado para pruebas rápidas de comportamiento de ejecución/settlement con una regla única y simple.

## 2) UX / Flujo de usuario

1. Iniciar bot.
2. El bot descubre mercados activos.
3. Si el mercado coincide con el filtro `Up or Down`, crea dos órdenes BUY límite a 5c (una por token).
4. Durante el cierre, las órdenes pueden llenarse parcial o totalmente.
5. Al resolverse mercado, se actualizan métricas de PnL en runtime/reportes.

## 3) Necesidades técnicas

- Reutiliza la arquitectura de Madawc (discovery, signal, paper execution, storage).
- Cambios mínimos:
  - precio de entrada fijo en 0.05,
  - stake máximo por trade en 1.0,
  - hasta 2 trades por mercado,
  - filtro `ONLY_TRADE_THIS_MARKETS`.

## 4) Testing y seguridad

- Tests mínimos de regresión del ciclo del bot.
- Riesgo principal: comportamiento de fill/settlement cuando ambos lados llenan en el mismo mercado (limitación heredada del modelo base).

## 5) Plan de trabajo (ejecutado)

1. Copia de `Madawc_v2` a `Madawc`.
2. Documentación de operativa en este README.
3. Ajuste de config y filtros.
4. Ajuste de señal para publicar limit fija a 5c por token (sin SELL).

## 6) Ripple effects

- Nuevo árbol `Madawc/` para ejecución separada.
- Nuevas variables de entorno/config para filtrar mercados por título.

## 7) Contexto y extensión futura

- Versión actual prioriza simplicidad absoluta (MVP).
- Futuro: separación de posiciones por token dentro de un mismo mercado para settlement totalmente correcto si ambos lados llenan.


## Cómo correrlo

Desde la raíz del repo:

```bash
cd Madawc
python -m Madawc_v2.launcher run-loop \
  --factory Madawc_v2.factory:build_bot \
  --db-path var/madawc/runtime.db \
  --interval-seconds 240
```

Para una sola iteración:

```bash
cd Madawc
python -m Madawc_v2.launcher run-once --factory Madawc_v2.factory:build_bot
```
