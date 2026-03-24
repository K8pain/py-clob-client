# ToTheMoon: inventario de programas, operación y cumplimiento de rate limits

## 1) Qué se está construyendo

Este documento describe **qué programas existen dentro de `ToTheMoon/`**, cuáles son realmente ejecutables hoy, cuáles son **read only / paper trading** y cuáles son **blueprints o componentes preparados para futuros flujos con autenticación**.

### Para quién es

- Developers que quieren ejecutar los scripts de `ToTheMoon` de forma segura.
- Quants que necesitan validar ideas sin usar capital real.
- Operadores que quieren entender qué piezas requieren credenciales y cuáles no.

### Problema que resuelve

- Evita lanzar scripts que no necesitan API key con configuraciones innecesarias.
- Aclara qué módulos son sólo de lectura y escriben únicamente en **JSON / SQLite / CSV / logs locales**.
- Deja explícito cómo mantener el sistema dentro de los **rate limits oficiales de Polymarket**.

### Cómo funciona esta guía

1. Filtra los programas por tipo de uso.
2. Explica cómo ejecutarlos sin API key cuando aplica.
3. Describe la estrategia técnica de rate limiting y retries.
4. Extiende la misma disciplina a los módulos que en el futuro usarán API privada o tokens.

---

## 2) Resumen ejecutivo: qué hay dentro de `ToTheMoon`

### Programas read only / paper trading / sin API key

| Programa | Estado | Necesita API key | I/O principal | Objetivo |
|---|---|---:|---|---|
| `ToTheMoon/strategies/mean_reversion.py` | Ejecutable | No | JSON local | Paper trading de mean reversion sobre mercados crypto Up/Down |
| `ToTheMoon/strategies/polymarket_autopilot/runner.py` | Ejecutable | No | SQLite + logs | Paper trading multi-señal sobre mercados de Polymarket |
| `ToTheMoon/strategies/polymarket_engine/discovery.py` + `historical.py` + `backtester.py` | Librería/flujo batch | No | CSV local | Discovery, descarga histórica y backtesting |
| `ToTheMoon/strategies/polymarket_mvp/core.py` | Librería analítica | No | Memoria / posible CSV aguas abajo | Detección de incoherencias y tail premium |
| `ToTheMoon/real_helpers/*.py` | Librerías auxiliares | No | Memoria | Validación, resiliencia, riesgo y PnL |

### Programas o componentes preparados para autenticación privada

| Programa | Estado | Necesita credenciales para operar de verdad | Nota |
|---|---|---:|---|
| `ToTheMoon/strategies/polymarket_engine/execution.py` (`RealExecutionAdapter`) | Blueprint | Sí | Hoy no envía órdenes reales; devuelve payload listo para submit |
| `ToTheMoon/strategies/mvp1_market_maker/` | Diseño/HLD | Sí para ejecución real futura | README y contratos; no hay runner real todavía |

### Artefactos de diseño, no runners completos

- `ToTheMoon/strategies/mvp1_market_maker/contracts.py`
- `ToTheMoon/strategies/mvp1_market_maker/README.md`
- `ToTheMoon/strategies/polymarket_mvp/core.py`

Estos archivos describen conceptos, contratos y scoring, pero **no constituyen por sí solos un bot listo para producción**.

---

## 3) UX / flujo de uso por programa

## A. `mean_reversion.py`

### Qué es

Una estrategia de **paper trading** que compra `YES` cuando el midpoint cae por debajo de `0.40` y vende cuando supera `0.60`.

### Para quién es

Para quien quiera un ejemplo mínimo, legible y de bajo riesgo.

### Qué problema resuelve

Permite probar un flujo completo de descubrimiento + señal + persistencia local **sin firmar órdenes reales**.

### Happy flow

1. Descubre mercados simplificados desde CLOB.
2. Filtra mercados crypto con patrón `Up / Down`.
3. Lee `midpoint` del token `YES`.
4. Simula compra o venta.
5. Guarda estado y trades en JSON.

### Alternative flows

- No hay mercados elegibles → no hace nada.
- No hay señal → no hace nada.
- Se activa el circuit breaker → deja de abrir nuevas operaciones.

### Ejecución sin API key

Ejemplo mínimo desde Python:

```python
from ToTheMoon.strategies.mean_reversion import MeanReversionPaperStrategy, StrategyConfig

strategy = MeanReversionPaperStrategy(StrategyConfig())
trades = strategy.run_once(page_limit=3)
print(trades)
```

### Efectos locales

- `ToTheMoon/state.json`
- `ToTheMoon/paper_trades.json`

No envía órdenes reales ni necesita claves.

---

## B. `polymarket_autopilot`

### Qué es

Un simulador de señales TAIL, BONDING y SPREAD con persistencia en SQLite.

### Para quién es

Para developers u operadores que quieren una versión más rica que el ejemplo de mean reversion.

### Happy flow

1. Descarga snapshots de mercados desde Gamma.
2. Genera señales.
3. Ejecuta paper trades en SQLite.
4. Rebalancea take profit.
5. Publica resumen diario en log.

### Alternative flows

- No hay snapshots válidos → no abre operaciones.
- No hay señal → persiste snapshots, pero no trades.
- No hubo actividad ayer → lo deja reflejado en el log diario.

### Ejecución sin API key

```bash
python -m ToTheMoon.strategies.polymarket_autopilot.runner
```

### Efectos locales

- `ToTheMoon/strategies/polymarket_autopilot/data/paper_trading.db`
- `ToTheMoon/strategies/polymarket_autopilot/logs/polymarket-autopilot.log`

No firma órdenes ni mueve fondos.

---

## C. `polymarket_engine`

### Qué es

Un conjunto modular para:

- descubrir mercados,
- descargar histórico,
- construir features,
- simular ejecución,
- evaluar riesgo,
- y producir reportes CSV.

### Para quién es

Para developers que quieren montar pipelines reproducibles de research o backtesting.

### Cómo hacerlo funcionar sin API key

#### Paso 1: discovery

```python
from ToTheMoon.strategies.polymarket_engine.discovery import GammaDiscoveryClient

client = GammaDiscoveryClient("https://gamma-api.polymarket.com")
markets = client.fetch_markets("/markets")
print(len(markets))
```

#### Paso 2: descarga histórica

```python
from pathlib import Path
from ToTheMoon.strategies.polymarket_engine.storage import CsvStore
from ToTheMoon.strategies.polymarket_engine.historical import HistoricalDownloader

store = CsvStore(Path("./tmp_engine_data"))
downloader = HistoricalDownloader(
    base_url="https://clob.polymarket.com",
    history_path="/prices-history",
    store=store,
)
```

#### Paso 3: backtest con paper execution

Usar `PaperExecutionAdapter`; no necesita autenticación.

### Efectos locales

- `catalog/*.csv`
- `historical/**/*.csv`
- `execution/*.csv`
- `reports/*.csv`

---

## D. `polymarket_mvp/core.py`

### Qué es

Una librería analítica para evaluar relaciones entre mercados y detectar señales como:

- `related_market_incoherence`
- `tail_premium`

### Necesita API key

No. El módulo solo define lógica, estructuras y scoring. Los datos se le inyectan desde fuera.

### Cómo usarlo sin API key

Consumir datos públicos de Gamma/CLOB y pasarlos a sus funciones puras. No requiere credenciales mientras la fuente de datos sea pública.

---

## E. `mvp1_market_maker`

### Qué es

Un HLD/MVP blueprint para un market maker de mercados crypto de 5 minutos.

### Estado

No hay runner real ni pipeline completo de ejecución todavía. Es una especificación con contratos.

### Necesita API key

- **No** para leer el diseño o implementar paper trading.
- **Sí** para cualquier futura ejecución real de órdenes.

---

## 4) Diseño técnico del cumplimiento de rate limits

## Fuente normativa usada

Se tomó como referencia la documentación oficial de Polymarket sobre rate limits: <https://docs.polymarket.com/api-reference/rate-limits>.

Puntos relevantes verificados en la documentación oficial:

- Gamma API general: **4,000 req / 10s**.
- Gamma `/markets`: **300 req / 10s**.
- CLOB general: **9,000 req / 10s**.
- CLOB `/midpoint`: **1,500 req / 10s**.
- CLOB `/prices-history`: **1,000 req / 10s**.
- Trading `POST /order`: **3,500 req / 10s burst** y **36,000 req / 10 min sustained**.

### Criterio aplicado en este repo

En lugar de acercarnos al máximo teórico, se aplican **límites locales conservadores** para dejar margen operativo:

| Uso local | Límite local | Límite oficial | Margen |
|---|---:|---:|---:|
| Mean reversion `get_simplified_markets` | 250 / 10s | muy por debajo del general CLOB | conservador |
| Mean reversion `get_midpoint` | 1,200 / 10s | 1,500 / 10s | ~20% margen |
| Autopilot Gamma `/markets` | 250 / 10s | 300 / 10s | ~16.7% margen |
| Engine `prices-history` | 800 / 10s | 1,000 / 10s | 20% margen |
| Real execution `POST /order` | 2,500 / 10s | 3,500 / 10s burst | margen operativo |

## Cambios proactivos implementados

### 1. Rate limiter local por endpoint

Se añadió `ToTheMoon/api.py` con:

- `RateLimitPolicy`
- `EndpointRateLimiter`
- `RetryPolicy`
- `PolymarketHttpClient`

### 2. Retries con `tenacity`

Se incorporó `tenacity` para:

- reintentos ante `429`,
- reintentos ante errores `5xx`,
- reintentos ante timeouts y fallos de red,
- backoff exponencial con jitter,
- respeto de `Retry-After` cuando esté presente.

### 3. Throttling previo incluso en flujos read only

Aunque varios scripts usan clientes o helpers locales, se les añadió limitación local antes de consumir endpoints públicos. Así evitamos ráfagas accidentales por bucles, cron solapado o expansiones de volumen.

---

## 5) Implementación concreta por programa

## A. `mean_reversion.py`

### Cumplimiento aplicado

- Throttle local antes de `get_simplified_markets`.
- Throttle local antes de `get_midpoint`.
- Persistencia solo en JSON local.

### Riesgos cubiertos

- cron demasiado agresivo,
- demasiados mercados evaluados en poco tiempo,
- ráfagas de midpoint cuando aumente el universo de mercados.

### Recomendación operativa

Mantener `page_limit` bajo para uso continuo. Para MVP, `1-3` páginas suele ser suficiente.

---

## B. `polymarket_autopilot/service.py`

### Cumplimiento aplicado

- Cliente HTTP con retry + backoff.
- Límite local conservador para Gamma `/markets`.
- Escritura únicamente en SQLite y logs locales.

### Recomendación operativa

Si se programa en scheduler frecuente, espaciar ciclos para que la estrategia tenga tiempo de procesar, persistir y cerrar archivos entre ejecuciones.

---

## C. `polymarket_engine/discovery.py`

### Cumplimiento aplicado

- `GammaDiscoveryClient` usa `PolymarketHttpClient`.
- Límite conservador local de 250 req / 10s para `/markets`.
- Reintentos con `tenacity` para 429/5xx/timeouts.

---

## D. `polymarket_engine/historical.py`

### Cumplimiento aplicado

- `HistoricalDownloader` usa `PolymarketHttpClient`.
- Tope local de 800 req / 10s para `/prices-history`.
- Reintentos con backoff y respeto de `Retry-After`.

### Recomendación operativa

Si se descargan muchos tokens, hacerlo por lotes pequeños y persistir entre lotes. El límite local ya ayuda, pero el batching facilita observabilidad y recuperación.

---

## E. `polymarket_engine/execution.py` (`RealExecutionAdapter`)

### Cumplimiento aplicado

Aunque hoy el adapter **no envía órdenes reales**, ya incorpora rate limiting local para la futura ruta de `POST /order`.

### Por qué esto importa

Tu punto 4 pide extender la disciplina de rate limits a los módulos que usarían API privada o tokens. Este adapter queda preparado para que, al conectar un cliente autenticado real, ya exista una barrera local de pacing.

### Qué faltaría para trading real

- firma/auth real del cliente,
- control de burst y sustained window por tipo de endpoint,
- cancel/replace pacing independiente,
- reconciliación con órdenes aceptadas/rechazadas,
- métricas operativas por wallet/API key.

---

## 6) Testing y seguridad

## Objetivos de cobertura

- Validar que los scripts existentes siguen funcionando en modo paper.
- Validar que los adapters y pipelines siguen produciendo artefactos locales.
- Validar que el nuevo rate limiter respeta ventanas simples.

## Seguridad

### Read only / paper trading

Todos los runners documentados para ejecución sin API key:

- leen datos públicos,
- no firman órdenes,
- no transfieren fondos,
- solo escriben JSON, CSV, SQLite o logs locales.

### Módulos privados

Para los módulos preparados para credenciales:

- no se debe guardar API key en código fuente,
- no se deben registrar secrets en logs,
- se debe añadir separación clara entre `paper` y `real`,
- la capa autenticada debe ser inyectable para testing.

---

## 7) Plan de trabajo / operación recomendada

## Requerido para usar hoy

1. Instalar dependencias.
2. Ejecutar solo `mean_reversion`, `polymarket_autopilot` o el pipeline paper de `polymarket_engine`.
3. Revisar salidas locales.
4. Mantener la frecuencia de ejecución moderada.

## Opcional / futuro

- Añadir métricas Prometheus o CSV de rate-limit waits.
- Añadir scheduler centralizado con locks para evitar solapes.
- Añadir WebSocket para reducir polling en algunos flujos.
- Añadir ventanas separadas para `cancel`, `post`, `batch post` y `account endpoints` cuando exista trading real completo.

---

## 8) Ripple effects

### Documentación actualizada

- README general de `ToTheMoon`.
- Esta guía operativa específica.

### Impacto en dependencias

Se añade `tenacity` como dependencia real para endurecer retries y backoff.

---

## 9) Contexto más amplio y limitaciones actuales

### Limitaciones

- `mean_reversion.py` depende del cliente CLOB existente; el rate limiting se aplica localmente antes de invocar sus métodos.
- `RealExecutionAdapter` sigue siendo un blueprint: no realiza submit real todavía.
- No hay aún telemetría centralizada de consumo de cuotas por proceso.

### Posibles extensiones futuras

- usar WebSocket para minimizar `GET` repetitivos,
- añadir circuit breaker específico de `429`,
- persistir métricas de espera por rate limiting,
- coordinar límites por proceso distribuido si se ejecutan varios workers.

### Moonshot ideas

- un scheduler común para todos los módulos ToTheMoon con presupuesto global de requests,
- switching inteligente entre polling y streams,
- degradación automática de frecuencia según latencia, 429s o carga histórica.
