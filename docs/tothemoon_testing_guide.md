# Guía de instalación, configuración y pruebas de los scripts de ToTheMoon

## 1. Qué es ToTheMoon

ToTheMoon es el espacio de este repositorio donde viven varias estrategias y prototipos para Polymarket. El objetivo principal hoy no es ejecutar trading real de forma automática, sino validar ideas de estrategia, procesamiento de mercados y flujos de paper trading usando el cliente Python del CLOB incluido en este mismo repo.

### Para quién es

- Developers que necesitan entender cómo correr y probar los distintos módulos.
- Quants o traders técnicos que quieren validar features antes de tocar dinero real.
- Personas que necesitan saber qué configuración previa hace falta para cada script.

### Qué problema resuelve

En el repo conviven varios enfoques:

- acceso al CLOB de Polymarket mediante `py_clob_client`,
- descubrimiento de mercados y datos históricos desde Gamma,
- estrategias paper-only dentro de `ToTheMoon`,
- ejemplos de autenticación y de operaciones reales en `examples/`.

Sin una guía, es fácil no tener claro:

- qué archivo configurar primero,
- cuándo hace falta clave privada o API key,
- cuándo Gamma es solo una API externa y cuándo habría que instalar algo adicional,
- cómo probar cada feature sin mezclar paper trading con trading real.

---

## 2. Mapa rápido de componentes y cómo interactúan

### Relación entre piezas

1. **`py_clob_client/`**
   - Es la librería base del repo para hablar con el CLOB de Polymarket.
   - Sirve tanto para consultas read-only como para autenticación, firma y envío de órdenes reales.

2. **`ToTheMoon/strategies/mean_reversion.py`**
   - Estrategia de **paper trading**.
   - Descubre mercados vía CLOB simplificado, toma midpoint del token `YES` y guarda estado/trades en JSON.

3. **`ToTheMoon/strategies/polymarket_autopilot/`**
   - Simulador de estrategias **paper-only**.
   - Consume mercados desde la API de Gamma y persiste snapshots/operaciones simuladas en SQLite.

4. **`ToTheMoon/strategies/polymarket_engine/`**
   - Toolkit modular para discovery, descarga histórica, features, riesgo, ejecución paper/real y reporting.
   - Usa **Gamma** para catálogo de mercados y **CLOB** para histórico/precios.

5. **`ToTheMoon/strategies/polymarket_mvp/`** y **`mvp1_market_maker/`**
   - Son artefactos de diseño, scoring y pruebas de lógica de estrategia.
   - Se usan sobre todo a través de tests y de integración con otros módulos.

6. **`examples/`**
   - Scripts del cliente CLOB para autenticación, market data, órdenes, allowances y RFQ.
   - Son la referencia principal cuando quieras verificar credenciales reales.

### Interacción entre Gamma y el repo

- **Gamma no es un subrepo dentro de este proyecto.**
- En este código, “Gamma” se usa como **API HTTP pública de mercados de Polymarket**, normalmente con base URL `https://gamma-api.polymarket.com`.
- Por lo tanto, **no necesitas instalar un repo de Gamma para correr ToTheMoon** en los flows actuales.
- Solo tendría sentido instalar un repo aparte de Gamma si tu equipo tiene tooling privado/extra fuera de este repo. Esa dependencia no aparece en el código actual.

---

## 3. Archivos de configuración y variables que debes tener listas primero

Antes de ejecutar nada, revisa estos archivos y puntos de configuración.

### 3.1 Archivo `.env`

El repo trae una plantilla mínima en `.env.example`:

```env
PK=
CLOB_API_KEY=
CLOB_SECRET=
CLOB_PASS_PHRASE=
CLOB_API_URL=
```

### 3.2 Qué significa cada variable

- `PK`
  - Private key de la wallet que firma contra Polymarket.
  - **Solo necesaria** para scripts autenticados o de trading real.
  - **No debería usarse** para paper trading puro salvo que adaptes scripts que la requieran.

- `CLOB_API_KEY`
  - API key del CLOB de Polymarket.
  - Necesaria para varios scripts autenticados de `examples/`.

- `CLOB_SECRET`
  - Secret asociado a la API key del CLOB.

- `CLOB_PASS_PHRASE`
  - Passphrase asociada a la API key del CLOB.

- `CLOB_API_URL`
  - Endpoint base del CLOB.
  - Producción típica: `https://clob.polymarket.com`
  - Algunos ejemplos RFQ usan staging.

### 3.3 Configuración hardcoded en las estrategias

Además del `.env`, hay estrategias con configuración en código:

- `ToTheMoon/strategies/mean_reversion.py`
  - `host`
  - `gamma_api_url`
  - `buy_below`
  - `sell_above`
  - `stake_usd`
  - `state_file`
  - `trades_file`

- `ToTheMoon/strategies/polymarket_autopilot/service.py`
  - `starting_capital`
  - `max_markets`
  - thresholds de señales TAIL / BONDING / SPREAD
  - `summary_channel`

- `ToTheMoon/strategies/polymarket_engine/config.py`
  - `gamma_base_url`
  - `clob_base_url`
  - `history_path`
  - configuración de riesgo y storage

### 3.4 Persistencia local que debes conocer

Estos archivos o rutas se generan o usan durante pruebas. En ejecución normal, cada script usa rutas relativas a su propio directorio; en tests se puede inyectar `tmp_path` u otro directorio temporal:

- `ToTheMoon/state.json`
- `ToTheMoon/paper_trades.json`
- `ToTheMoon/strategies/polymarket_autopilot/data/paper_trading.db`
- `ToTheMoon/strategies/polymarket_autopilot/logs/polymarket-autopilot.log`
- `ToTheMoon/strategies/polymarket_engine/data/...` o el path temporal que uses en tests

### 3.5 Checklist de configuración previa por tipo de ejecución

#### A. Solo pruebas unitarias/locales sin tocar APIs reales

Necesitas:

- Python 3.9+.
- Dependencias instaladas.
- **No** necesitas `PK`, API keys ni fondos.

#### B. Read-only contra Polymarket

Necesitas:

- conexión a internet,
- `CLOB_API_URL` opcional si quieres sobrescribir producción,
- normalmente **no** necesitas `PK` ni API keys para consultas públicas.

#### C. Trading real o scripts autenticados del CLOB

Necesitas:

- `PK`,
- `CLOB_API_KEY`,
- `CLOB_SECRET`,
- `CLOB_PASS_PHRASE`,
- en algunos casos también `funder` y `signature_type` según el tipo de wallet.

#### D. RFQ / staging

Necesitas:

- variables adicionales específicas del script,
- revisar cada ejemplo RFQ porque algunos usan requester/quoter separados,
- confirmar si `CLOB_API_URL` apunta a staging o producción.

---

## 4. Tokens, credenciales y permisos: qué hace falta y de dónde salen

## 4.1 Cuándo hace falta token/API key y cuándo no

### No hace falta token especial para

- correr tests unitarios,
- paper trading local que use stubs/mocks,
- varios scripts read-only,
- discovery por Gamma pública.

### Sí hace falta credencial para

- crear o derivar API keys,
- consultar recursos privados,
- cancelar órdenes propias,
- enviar órdenes reales,
- revisar balances/allowances autenticados,
- algunos flujos RFQ.

## 4.2 Dónde se consigue la API key del CLOB

En este repo hay ejemplos explícitos para crear o derivar credenciales del CLOB:

- `examples/create_api_key.py`
- `examples/derive_api_key.py`
- `examples/get_api_keys.py`
- `examples/create_readonly_api_key.py`

Operativamente, la API key del CLOB está asociada a tu identidad/wallet de Polymarket y se obtiene usando los endpoints de autenticación del propio CLOB a través del cliente del repo.

## 4.3 Apartado especial: generación del token/API key dentro de Polymarket

Si tu flujo operativo parte desde la web de Polymarket y luego usas este repo, conviene separar dos cosas:

### A. Identidad de wallet

- Tu wallet firma mensajes y demuestra que controlas la cuenta.
- Esa wallet puede ser EOA o una wallet proxy/funder.

### B. Credenciales del CLOB

- La API key, secret y passphrase son las credenciales prácticas para los requests autenticados.
- En este repo suelen generarse/derivarse después de autenticarte con la private key usando los ejemplos o el cliente Python.

## 4.4 ¿Esos tokens deben tener permisos especiales?

Sí, hay dos capas de permisos a distinguir:

### 1. Permisos de autenticación CLOB

- Tu API key debe ser válida para operar sobre tu cuenta.
- Para lectura privada o trading, debes usar el set correcto: `API_KEY + SECRET + PASS_PHRASE`.
- Si usas readonly key, sirve solo para lo que el endpoint readonly permita.

### 2. Permisos on-chain / allowances

Para **trading real**, además de la autenticación del CLOB, Polymarket necesita poder mover:

- **USDC**,
- **Conditional Tokens**.

Eso implica configurar allowances antes de operar con ciertas wallets, especialmente EOA/MetaMask/hardware wallets.

## 4.5 Apartado aparte: allowances en la web/infra de Polymarket

Antes de trading real, valida lo siguiente:

1. Que la wallet tenga fondos.
2. Que la wallet correcta sea la que firma o la funder wallet si aplica.
3. Que existan allowances activas para:
   - USDC,
   - conditional tokens.
4. Que el entorno coincida con el endpoint:
   - producción con `https://clob.polymarket.com`,
   - staging si el script lo requiere.

> Recomendación: documenta internamente quién genera la API key, qué wallet actúa como funder y en qué entorno se activaron los allowances. En equipos, estos son los errores más frecuentes.

---

## 5. Instalación completa del repo desde cero

## 5.1 Requisitos

- Python **3.9.10 o superior**.
- `pip`.
- Recomendado: `venv`.

## 5.2 Clonar e instalar

```bash
git clone <URL_DEL_REPO>
cd py-clob-client
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
pip install -e .
```

## 5.3 Crear tu `.env`

```bash
cp .env.example .env
```

Luego rellena solo lo necesario para tu caso:

- para tests: puedes dejarlo vacío,
- para read-only: normalmente basta con `CLOB_API_URL` si quieres customizar,
- para autenticado/real: completa todas las credenciales.

## 5.4 ¿Hace falta instalar también un repo de Gamma?

**No para este proyecto, en su estado actual.**

ToTheMoon usa Gamma como API remota por HTTP. No hay ninguna dependencia declarada en `requirements.txt`, `setup.py` ni en el código que exija clonar un repo separado de Gamma para ejecutar las estrategias presentes aquí.

Si en tu organización existe un repo interno de Gamma con utilidades adicionales, trátalo como dependencia externa opcional, no como requisito base de este repositorio.

---

## 6. Cómo proceder con la prueba de los diferentes scripts de ToTheMoon

La mejor forma de avanzar es **de menor a mayor riesgo**:

1. tests unitarios,
2. scripts paper-only,
3. integración parcial con APIs públicas,
4. ejemplos autenticados read-only,
5. trading real solo al final.

## 6.1 Fase 1 — Validar instalación y salud general del repo

Ejecuta:

```bash
pytest -q
```

Qué valida esta fase:

- que las dependencias estén bien instaladas,
- que la importación de `ToTheMoon` y `py_clob_client` funcione,
- que la lógica principal no esté rota.

Si quieres ir por suites concretas:

```bash
pytest tests/tothemoon -q
pytest tests/strategies/test_polymarket_autopilot.py -q
pytest tests/polymarket_engine/test_engine.py -q
```

## 6.2 Fase 2 — Probar `mean_reversion` en modo seguro

### Qué feature cubre

- discovery de mercados crypto tipo Up/Down,
- lectura de midpoint desde CLOB,
- reglas simples de compra/venta,
- persistencia local en JSON,
- circuit breaker por pérdidas consecutivas.

### Cómo funciona técnicamente

- usa `ClobClient` en modo read-only,
- descubre mercados con `get_simplified_markets`,
- toma `yes_token_id`,
- evalúa thresholds `buy_below` y `sell_above`,
- escribe en `ToTheMoon/state.json` y `ToTheMoon/paper_trades.json`, resolviéndolos desde el directorio del paquete `ToTheMoon`.

### Cómo probarlo

#### Opción A: test unitario recomendado

```bash
pytest tests/tothemoon/test_mean_reversion.py -q
```

#### Opción B: prueba manual controlada

Crea un pequeño runner local o usa un snippet como este desde `python`:

```python
from ToTheMoon.strategies.mean_reversion import MeanReversionPaperStrategy, StrategyConfig

strategy = MeanReversionPaperStrategy(StrategyConfig())
trades = strategy.run_once(page_limit=1)
print(trades)
```

### Configuración mínima

- No requiere API key del CLOB para el flow base.
- Sí requiere internet si consultas datos reales.
- Genera/usa:
  - `ToTheMoon/state.json`
  - `ToTheMoon/paper_trades.json`

### Riesgos / edge cases a vigilar

- mercados sin token `YES`,
- midpoint nulo o no disponible,
- cambios de estructura en respuestas del CLOB,
- circuit breaker activado por pérdidas consecutivas.

## 6.3 Fase 3 — Probar `polymarket_autopilot`

### Qué feature cubre

- paper trading multi-estrategia,
- señales TAIL, BONDING y SPREAD,
- persistencia en SQLite,
- logging de resumen diario.

### Cómo interactúa con otros componentes

- consume mercados desde Gamma,
- no envía órdenes reales,
- usa `PaperTradingStore` para portfolio y snapshots.

### Cómo probarlo

#### Opción A: tests

```bash
pytest tests/strategies/test_polymarket_autopilot.py -q
```

#### Opción B: ejecución manual

```bash
python -m ToTheMoon.strategies.polymarket_autopilot.runner
```

### Qué deberías verificar tras correrlo

- que exista `ToTheMoon/strategies/polymarket_autopilot/data/paper_trading.db`,
- que exista `ToTheMoon/strategies/polymarket_autopilot/logs/polymarket-autopilot.log`,
- que no haya órdenes reales ni dependencia de fondos.

### Configuración mínima

- internet para Gamma si haces ejecución real del runner,
- no requiere API keys en el flow actual,
- SQLite viene con Python estándar.

## 6.4 Fase 4 — Probar `polymarket_engine`

### Qué feature cubre

Este módulo sirve como pipeline de research/ejecución:

1. **discovery** desde Gamma,
2. **normalización** de catálogo,
3. **histórico** desde el CLOB (`/prices-history`),
4. construcción de **features**,
5. generación de **signals**,
6. evaluación de **risk**,
7. **paper execution** o preparación de ejecución real,
8. **reporting** y almacenamiento CSV.

### Cómo interactúan Gamma y CLOB aquí

- **Gamma** aporta el catálogo de mercados/tokens.
- **CLOB** aporta histórico/precios y, potencialmente, la capa de ejecución.
- Es el ejemplo más claro del repo donde ambos servicios se complementan.

### Cómo probarlo

#### Opción A: test end-to-end controlado

```bash
pytest tests/polymarket_engine/test_engine.py -q
```

Ese test ya cubre un flujo completo con payloads mockeados.

#### Opción B: integración incremental propia

Secuencia recomendada:

1. probar `discover_catalog` con payload mock,
2. probar `HistoricalDownloader` con uno o dos tokens,
3. verificar features,
4. ejecutar `PaperExecutionAdapter`,
5. revisar CSVs de salida.

### Configuración mínima

- Para tests: sin credenciales.
- Para integrar con endpoints reales:
  - internet,
  - `gamma_base_url` correcto,
  - `clob_base_url` correcto.
- Solo si das el salto a `RealExecutionAdapter` conectado a un cliente real necesitarás credenciales/autorización del CLOB.

## 6.5 Fase 5 — Probar `polymarket_mvp`

### Qué feature cubre

- parsing de mercados,
- agrupación por familias relacionadas,
- cálculo de probabilidades de referencia,
- scoring de incoherencias y tail premium,
- simulación y settlement de trades paper.

### Cómo probarlo

```bash
pytest tests/tothemoon/test_polymarket_mvp.py -q
```

### Cuándo usarlo

Úsalo cuando quieras validar la lógica cuantitativa y los conceptos del modelo antes de montar una integración completa con market data vivo.

## 6.6 Fase 6 — Probar los scripts de `examples/` antes de tocar features reales

Aunque tu pedido está centrado en ToTheMoon, conviene usar `examples/` como capa de verificación operativa.

Orden recomendado:

### Read-only primero

```bash
python examples/get_ok.py
python examples/get_markets.py
python examples/get_price.py
python examples/get_orderbook.py
```

### Luego autenticación

```bash
python examples/derive_api_key.py
python examples/get_api_keys.py
python examples/get_balance_allowance.py
```

### Y solo después trading real

```bash
python examples/update_balance_allowance.py
python examples/order.py
python examples/market_buy_order.py
python examples/market_sell_order.py
```

> Importante: los scripts de órdenes reales deben ejecutarse únicamente cuando ya validaste credenciales, allowances, wallet correcta, entorno correcto y riesgos operativos.

---

## 7. Procedimiento recomendado de prueba por feature

## 7.1 Discovery de mercados

### Objetivo
Validar que el sistema encuentra mercados y extrae correctamente token IDs y metadatos.

### Checks

- `mean_reversion`: detecta mercados crypto “up/down”.
- `polymarket_engine`: construye catálogo válido desde Gamma.
- `polymarket_mvp`: parsea `YES` y `NO` correctamente.

### Comandos

```bash
pytest tests/tothemoon/test_mean_reversion.py -q
pytest tests/polymarket_engine/test_engine.py -q
pytest tests/tothemoon/test_polymarket_mvp.py -q
```

## 7.2 Señales y lógica cuantitativa

### Objetivo
Validar reglas TAIL, BONDING, SPREAD, mean reversion e incoherencias entre mercados.

### Checks

- señales salen solo en condiciones correctas,
- thresholds son trazables,
- no hay señales falsas por datos incompletos.

### Comandos

```bash
pytest tests/strategies/test_polymarket_autopilot.py -q
pytest tests/tothemoon/test_polymarket_mvp.py -q
```

## 7.3 Persistencia local

### Objetivo
Confirmar que cada módulo deja artefactos reproducibles.

### Checks

- JSON en `mean_reversion`,
- SQLite y logs en `autopilot`,
- CSVs/reportes en `polymarket_engine`.

### Procedimiento

1. correr la suite o runner,
2. inspeccionar archivos generados,
3. borrar artefactos si quieres repetir limpio.

## 7.4 Riesgo y ejecución

### Objetivo
Separar claramente paper execution de real execution.

### Checks

- `PaperExecutionAdapter` solo genera registros simulados,
- `RealExecutionAdapter` debe usarse solo cuando el cliente autenticado esté listo,
- los límites de riesgo bloquean exposición indebida.

### Comando base

```bash
pytest tests/polymarket_engine/test_engine.py -q
```

---

## 8. Seguridad operacional antes de pasar a trading real

## Nunca saltes directamente de tests a órdenes reales

Checklist mínimo:

- [ ] `.env` completado correctamente.
- [ ] `PK` corresponde a la wallet esperada.
- [ ] `CLOB_API_URL` apunta al entorno correcto.
- [ ] API key / secret / passphrase válidos.
- [ ] allowances verificadas.
- [ ] saldo verificado.
- [ ] token IDs verificados.
- [ ] tamaño de orden reducido para pruebas.
- [ ] logs habilitados.
- [ ] confirmación de si la wallet usa `funder` y `signature_type` especial.

### Wallets proxy / funder

Si tu cuenta usa wallet delegada, email wallet o smart wallet:

- confirma el `funder` address,
- revisa el `signature_type` correcto,
- prueba primero con derivación de credenciales y endpoints read-only autenticados.

---

## 9. Plan de trabajo sugerido para alguien que entra nuevo al repo

### Día 1 — Instalación y comprensión

- instalar dependencias,
- leer `README.md` y `ToTheMoon/README.md`,
- correr `pytest -q`.

### Día 2 — Paper trading puro

- correr tests de `mean_reversion`,
- ejecutar `polymarket_autopilot.runner`,
- inspeccionar JSON, SQLite y logs.

### Día 3 — Engine de research

- correr `tests/polymarket_engine/test_engine.py`,
- entender discovery + histórico + features + risk + execution.

### Día 4 — Autenticación CLOB

- preparar `.env`,
- derivar/crear API keys,
- probar scripts read-only autenticados.

### Día 5 — Trading real controlado

- verificar allowances,
- usar tamaños mínimos,
- ejecutar solo ejemplos puntuales y con supervisión.

---

## 10. Definition of Done para “ya puedo probar ToTheMoon con criterio”

Considera que ya tienes el entorno listo cuando puedes hacer todo esto:

- correr todas las suites relevantes sin errores,
- explicar qué módulos son paper-only y cuáles pueden tocar trading real,
- saber qué secretos hacen falta para cada script,
- entender que Gamma aquí se usa como API y no como repo obligatorio,
- verificar artefactos de salida de `mean_reversion`, `autopilot` y `polymarket_engine`,
- derivar o crear credenciales del CLOB si vas a usar features autenticadas,
- validar allowances antes de cualquier orden real.

---

## 11. Extensiones futuras recomendadas de esta documentación

Si el equipo sigue creciendo, convendría añadir después:

- un `.env.example` ampliado para RFQ y wallets proxy,
- un script `make` o `justfile` con comandos estándar de prueba,
- un documento separado de “runbooks” para producción/staging,
- una matriz “script -> credenciales necesarias -> riesgo -> entorno”.
