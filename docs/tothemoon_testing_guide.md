# Guía de instalación, configuración y pruebas de scripts de ToTheMoon

## 1. Qué es ToTheMoon y qué se va a probar

### Qué es
`ToTheMoon` es la carpeta del repositorio donde viven varias estrategias y prototipos alrededor de Polymarket. En este repo hay, como mínimo, cuatro líneas de trabajo distintas:

1. **`mean_reversion.py`**: estrategia simple de *paper trading* sobre mercados “Up or Down”.
2. **`strategies/polymarket_autopilot`**: simulador de señales con persistencia en SQLite y resumen diario.
3. **`strategies/polymarket_engine`**: pipeline más modular para discovery, histórico, features, riesgo, backtest y adapters de ejecución.
4. **`strategies/polymarket_mvp` / `strategies/mvp1_market_maker`**: prototipos de investigación y contratos de datos para nuevos features o blueprints.

### Para quién es
Este documento está pensado para alguien que:

- necesita levantar el repo desde cero,
- quiere entender qué archivos de configuración deben estar preparados,
- quiere saber si además hace falta instalar algo relacionado con **Gamma**,
- y necesita una receta ordenada para probar los diferentes scripts/features sin mezclar credenciales ni entornos.

### Qué problema resuelve
En este repo conviven piezas con distintos niveles de madurez:

- módulos puramente offline,
- estrategias de *paper trading*,
- clientes de lectura pública,
- ejemplos autenticados contra CLOB,
- y componentes de ejecución real preparados pero no conectados automáticamente en `ToTheMoon`.

El objetivo de esta guía es separar claramente:

- **qué depende de Gamma**,
- **qué depende de CLOB**,
- **qué requiere claves/tokens**,
- **qué puede probarse offline**,
- y **en qué orden conviene validar cada feature**.

### Cómo interactúan entre ellos
La interacción entre componentes, a nivel práctico, es esta:

```text
Gamma API (metadatos de mercados)
        │
        ├── polymarket_engine.discovery
        └── polymarket_autopilot.fetch_market_data

CLOB API (orderbooks, midpoint, histórico, trading)
        │
        ├── py_clob_client
        ├── mean_reversion.py
        ├── polymarket_engine.historical
        └── ejemplos autenticados / trading real

Persistencia local
        │
        ├── JSON -> mean_reversion
        ├── SQLite -> polymarket_autopilot
        └── CSV -> polymarket_engine
```

## 2. Archivos de configuración y prerequisitos que deben estar “up” antes de probar nada

Esta es la parte más importante: **antes de ejecutar scripts**, hay que decidir si se va a probar solo lectura pública, *paper trading* local o endpoints autenticados.

### 2.1 Configuración base del repo

#### Archivos del repo que mandan la instalación
- `requirements.txt`: dependencias fijadas para desarrollo y tests.
- `setup.py`: instalación del paquete `py_clob_client` y dependencias runtime.
- `Makefile`: comandos rápidos `init`, `test` y `fmt`.

### 2.2 Variables y secretos posibles

No todos los flujos usan secretos. Esta tabla resume qué necesita cada uno.

| Variable | Cuándo hace falta | Para qué sirve |
|---|---|---|
| `CLOB_API_URL` | Opcional | Cambiar host de CLOB; por defecto suele usar `https://clob.polymarket.com`. |
| `PK` | Solo endpoints autenticados o creación/derivación de credenciales | Private key para firmar autenticación L1. |
| `CLOB_API_KEY` | Endpoints autenticados L2 | API key de CLOB. |
| `CLOB_SECRET` | Endpoints autenticados L2 | Secret de CLOB. |
| `CLOB_PASS_PHRASE` | Endpoints autenticados L2 | Passphrase asociada a la API key. |
| `CHAIN_ID` | Algunos ejemplos RFQ | Red objetivo. |
| `BUILDER_API_KEY` / `BUILDER_SECRET` | Solo ejemplos builder | Credenciales builder específicas. |
| `REQUESTER_API_KEY` / `REQUESTER_SECRET` | Solo `rfq_full_flow.py` | Credenciales del requester. |
| `QUOTER_API_KEY` / `QUOTER_SECRET` | Solo `rfq_full_flow.py` | Credenciales del quoter. |

### 2.3 ¿Hace falta un archivo `.env`?

No existe un `.env.example` en este repo, pero muchos ejemplos llaman a `load_dotenv()`. Lo más práctico es crear uno en la raíz del repo.

Ejemplo mínimo para **solo lectura / paper trading**:

```env
CLOB_API_URL=https://clob.polymarket.com
```

Ejemplo para **endpoints autenticados**:

```env
CLOB_API_URL=https://clob.polymarket.com
PK=0xTU_PRIVATE_KEY
CLOB_API_KEY=tu_api_key
CLOB_SECRET=tu_api_secret
CLOB_PASS_PHRASE=tu_api_passphrase
CHAIN_ID=137
```

> Recomendación: mantener un `.env.local` o gestor de secretos fuera de Git. Nunca commitear claves reales.

### 2.4 ¿Qué necesita cada feature?

#### A. `ToTheMoon/strategies/mean_reversion.py`
- **No necesita API key ni secret**.
- **No ejecuta órdenes reales**.
- Usa `ClobClient` en modo lectura para:
  - descubrir mercados,
  - leer midpoint,
  - guardar estado local en JSON.

#### B. `ToTheMoon/strategies/polymarket_autopilot`
- **No necesita API key ni secret**.
- Consume la **Gamma Markets API** pública.
- Persiste datos en SQLite.
- Solo hace *paper trading*.

#### C. `ToTheMoon/strategies/polymarket_engine`
- Para tests y backtests locales, **no necesita credenciales**.
- Para discovery e histórico reales:
  - usa **Gamma** para catálogo,
  - usa **CLOB** para `prices-history`.
- El adapter real está preparado, pero los tests actuales lo usan de forma homogénea/simulada.

#### D. `examples/` autenticados de `py_clob_client`
- **Sí pueden requerir `PK` y credenciales CLOB**.
- Son útiles para validar credenciales, allowances y acceso autenticado, aunque no forman parte directa del flujo paper de `ToTheMoon`.

## 3. Tokens, credenciales y permisos especiales

## 3.1 Qué NO requiere token

### Gamma
Para lo que usa este repo, **Gamma se consume como API pública**. No aparece en el código ningún token obligatorio de Gamma para:

- discovery del engine,
- autopilot,
- obtención de mercados.

Conclusión práctica: **no hace falta instalar un repo adicional de Gamma ni generar un token de Gamma para probar `ToTheMoon`**.

## 3.2 Qué SÍ requiere autenticación

### CLOB autenticado
Los endpoints autenticados de `py_clob_client` sí requieren credenciales. Hay dos niveles relevantes:

- **L1**: private key (`PK`) para firmar.
- **L2**: `CLOB_API_KEY`, `CLOB_SECRET` y `CLOB_PASS_PHRASE` para endpoints autenticados.

## 3.3 Cómo conseguir esas credenciales

Este repo da a entender el siguiente flujo operativo:

1. Tener wallet/private key válida para Polymarket/CLOB.
2. Instanciar `ClobClient` con la key.
3. Crear o derivar credenciales API con scripts como:
   - `examples/create_api_key.py`
   - `examples/derive_api_key.py`
4. Guardar con seguridad `api_key`, `secret` y `passphrase`.

### Importante
Las credenciales creadas no deben tratarse como recuperables. Hay una advertencia explícita en el paquete indicando que deben guardarse de forma segura tras su creación.

## 3.4 ¿Es necesario un token dentro de la web de Polymarket?

Con la evidencia de este repo, lo correcto es decir lo siguiente:

- Para **Gamma pública**: no.
- Para **lectura pública de CLOB**: no.
- Para **crear/derivar API creds y usar endpoints autenticados de CLOB**: necesitas una wallet capaz de firmar y luego generar las credenciales API correspondientes.

No veo en este repo un flujo documentado que dependa de un “token manual” generado desde una pantalla web de Gamma. Lo que sí hay es un flujo de autenticación basado en firma y en API creds de CLOB.

## 3.5 Permisos especiales y apartado separado para allowances

Si se va a pasar de lectura a trading/autenticación avanzada, hay que separar dos cosas:

### A. Credenciales
Permiten autenticarse contra CLOB.

### B. Allowances
Permiten operar con colateral o tokens condicionales cuando corresponda.

#### Cuándo preocuparse por allowances
Especialmente si se usan wallets EOA / MetaMask / hardware wallets y se quiere probar el camino de trading real o semirreal.

#### Cómo se gestiona en este repo
Hay un ejemplo específico:

```bash
python examples/update_balance_allowance.py
```

Ese script muestra tres tipos de actualización:

- allowance de **USDC**,
- allowance del token **YES**,
- allowance del token **NO**.

#### Recomendación operativa
No mezclar en la misma sesión de pruebas:

- tests offline,
- paper trading,
- creación de credenciales,
- actualización de allowances,
- órdenes reales.

Conviene validarlos en ese orden, de menor a mayor riesgo.

## 4. Instalación del repo desde cero

## 4.1 Requisitos

- Python **3.9.10+** como mínimo para el paquete.
- Recomendado: entorno virtual dedicado.
- Acceso de red si se van a probar Gamma/CLOB reales.

## 4.2 Instalación paso a paso

### Opción recomendada

```bash
git clone <url-del-repo>
cd py-clob-client
python -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
pip install -e .
```

### Opción rápida con Makefile

```bash
make init
pip install -e .
```

## 4.3 ¿Hace falta instalar también el repo de Gamma?

### Respuesta corta
**No, no es necesario para probar los features actuales de `ToTheMoon`.**

### Por qué
Porque `ToTheMoon` y `polymarket_engine` consumen Gamma vía HTTP pública, no vía import de un paquete local de Gamma.

### Cuándo podría ser útil
Solo como apoyo de desarrollo, por ejemplo si quieres:

- inspeccionar el esquema exacto de respuestas de mercados,
- comparar payloads,
- o desarrollar tooling paralelo.

Pero para ejecutar y probar los features de este repo, **no es prerequisito**.

## 5. Orden recomendado de pruebas por tipo de feature

La mejor forma de proceder es ir de menos riesgo y menos dependencias a más dependencia externa.

### Fase 1 — Tests unitarios/offline
Objetivo: verificar lógica local sin depender de red ni credenciales.

#### Qué cubre
- `mean_reversion`
- `polymarket_mvp`
- `polymarket_autopilot`
- `polymarket_engine`
- helpers de riesgo/resiliencia

#### Comandos sugeridos
```bash
pytest tests/tothemoon -q
pytest tests/strategies/test_polymarket_autopilot.py -q
pytest tests/polymarket_engine/test_engine.py -q
pytest tests/real_helpers -q
```

### Fase 2 — Paper trading local reproducible
Objetivo: validar persistencia local y flujos de simulación.

#### Qué probar
1. `mean_reversion.py`
2. `polymarket_autopilot.runner`
3. backtest / engine offline

### Fase 3 — Lectura online de Gamma/CLOB sin credenciales
Objetivo: validar conectividad real y compatibilidad de payloads.

#### Qué probar
- discovery contra Gamma,
- midpoint / market reads contra CLOB,
- histórico `prices-history`.

### Fase 4 — Autenticación CLOB
Objetivo: validar credenciales, sin lanzar todavía una orden real si no es necesario.

#### Qué probar
- derivación/creación de API keys,
- lectura de API keys,
- readonly keys,
- balance allowance.

### Fase 5 — Features de ejecución avanzada
Objetivo: solo si realmente hace falta pasar a operativa autenticada.

- órdenes,
- cancelaciones,
- RFQ,
- builder flows,
- allowances completos.

## 6. Procedimiento de prueba por script/feature de ToTheMoon

## 6.1 `ToTheMoon/strategies/mean_reversion.py`

### Qué hace
- Descubre mercados activos con texto “up/down”.
- Obtiene `midpoint` del token `YES`.
- Compra en paper si el precio cae por debajo del umbral.
- Vende en paper si sube por encima del umbral.
- Activa circuit breaker tras pérdidas consecutivas.
- Guarda estado en JSON.

### Configuración mínima
No requiere API creds. Solo conectividad a CLOB si se usa contra datos reales.

### Archivos que hay que vigilar
- `ToTheMoon/state.json`
- `ToTheMoon/paper_trades.json`

### Flujo recomendado de prueba
1. Validar tests unitarios.
2. Ejecutar una pasada controlada con datos stub o monkeypatch.
3. Ejecutar una pasada real si se quiere verificar discovery.
4. Confirmar que los JSON se crean y actualizan.

### Ejemplo de ejecución manual
```bash
python - <<'PY'
from ToTheMoon.strategies.mean_reversion import MeanReversionPaperStrategy, StrategyConfig

strategy = MeanReversionPaperStrategy(StrategyConfig())
trades = strategy.run_once(page_limit=1)
print(trades)
PY
```

### Qué revisar al terminar
- si se creó `state.json`,
- si se creó `paper_trades.json`,
- si `circuit_breaker_active` cambia al forzar pérdidas.

## 6.2 `ToTheMoon/strategies/polymarket_autopilot`

### Qué hace
- Consulta mercados desde Gamma.
- Genera señales TAIL / BONDING / SPREAD.
- Ejecuta trades simulados sobre SQLite.
- Publica resumen diario en un log local.

### Configuración mínima
No necesita secretos. Sí necesita red si no se mockea el cliente.

### Archivos/directorios que deben existir o poder crearse
- `ToTheMoon/strategies/polymarket_autopilot/data/`
- `ToTheMoon/strategies/polymarket_autopilot/logs/`

### Script principal
```bash
python -m ToTheMoon.strategies.polymarket_autopilot.runner
```

### Qué validar
- creación de `paper_trading.db`,
- creación de `polymarket-autopilot.log`,
- inserciones en tablas `portfolio`, `positions`, `trades`, `market_history`.

### Procedimiento recomendado
1. Correr tests unitarios del autopilot.
2. Ejecutar el runner una vez.
3. Inspeccionar SQLite.
4. Revisar el log diario.

### Inspección rápida de la base
```bash
sqlite3 ToTheMoon/strategies/polymarket_autopilot/data/paper_trading.db '.tables'
```

## 6.3 `ToTheMoon/strategies/polymarket_engine`

### Qué hace
Es el stack más modular. Separa:

1. **discovery** desde Gamma,
2. **descarga de histórico** desde CLOB,
3. **features** de incoherencia y colas,
4. **riesgo y portfolio**,
5. **execution adapters** paper/real,
6. **reporting y backtest**.

### Configuración relevante
La configuración central está en el dataclass `EngineConfig`.

#### Valores a revisar antes de probar
- `gamma_base_url`
- `clob_base_url`
- `history_path`
- `ws_stale_after_seconds`
- límites de estrategia/riesgo
- paths de almacenamiento bajo `data/polymarket_engine`

### Cómo interactúan los submódulos
```text
discovery -> catálogo de mercados/tokens
historical -> CSV por token
features -> candidatos/score
signal_engine -> señal operativa
risk -> aprobación o rechazo
execution -> paper o real
reporting -> resumen
```

### Orden recomendado de prueba
#### Paso 1: test end-to-end offline
```bash
pytest tests/polymarket_engine/test_engine.py -q
```

#### Paso 2: discovery real contra Gamma
Crear un pequeño script ad hoc o REPL para:
- instanciar `GammaDiscoveryClient`,
- llamar a `fetch_markets()`,
- pasar el resultado a `discover_catalog()`.

#### Paso 3: histórico real contra CLOB
Probar `HistoricalDownloader` con pocos tokens y un intervalo como `1h`.

#### Paso 4: revisar archivos generados
Esperar artefactos como:
- `catalog/market_catalog.csv`
- `catalog/token_catalog.csv`
- `historical/<interval>/<token_id>.csv`
- `execution/order_events.csv`
- `execution/fills.csv`
- `reports/strategy_summary.csv`

### Cuándo usar el adapter real
Solo cuando ya estén validados:
- discovery,
- histórico,
- features,
- señal,
- riesgo,
- y credenciales/autorizaciones.

## 6.4 `ToTheMoon/strategies/polymarket_mvp`

### Qué hace
Es un módulo de investigación para:
- parsear definiciones de mercado,
- agrupar mercados relacionados,
- calcular probabilidades de referencia,
- detectar incoherencias y tail premium,
- simular entrada y settlement.

### Cómo se prueba
Principalmente por tests unitarios:

```bash
pytest tests/tothemoon/test_polymarket_mvp.py -q
```

### Observación importante
Este módulo sirve como laboratorio de lógica cuantitativa. No debería ser el primer punto para meter credenciales ni operativa real.

## 6.5 `ToTheMoon/strategies/mvp1_market_maker`

### Qué hace
Es más un blueprint/HLD que un feature productivo completo. Sirve para documentar:
- elegibilidad,
- quoting,
- inventory risk,
- cancel/replace,
- persistencia y métricas.

### Cómo proceder con su prueba
- usarlo como referencia de diseño,
- validar primero contratos y módulos que lo soporten,
- no tratarlo como entrypoint ejecutable principal salvo que se construyan scripts adicionales alrededor.

## 7. Pruebas de autenticación y credenciales CLOB antes de features sensibles

Si se necesita validar acceso autenticado, hacerlo aparte del testing de `ToTheMoon`.

## 7.1 Crear o derivar credenciales

### Derivar
```bash
python examples/derive_api_key.py
```

### Crear
```bash
python examples/create_api_key.py
```

## 7.2 Probar credenciales readonly
```bash
python examples/create_readonly_api_key.py
python examples/get_readonly_api_keys.py
```

## 7.3 Validar allowances
```bash
python examples/update_balance_allowance.py
python examples/get_balance_allowance.py
```

## 7.4 Solo después: órdenes o RFQ
```bash
python examples/order.py
python examples/market_buy_order.py
python examples/market_sell_order.py
python examples/rfq_full_flow.py
```

> Recomendación: si el objetivo es probar `ToTheMoon`, normalmente no hace falta llegar a esta fase salvo que vayas a conectar el adapter real o a verificar infraestructura de trading autenticado.

## 8. Experiencia de usuario/desarrollador y flujos felices/alternativos

## 8.1 Happy flows

### Happy flow A — paper trading mínimo
1. Instalar repo.
2. Correr tests offline.
3. Ejecutar `mean_reversion`.
4. Confirmar JSONs.

### Happy flow B — autopilot paper con persistencia
1. Instalar repo.
2. Ejecutar tests del autopilot.
3. Correr runner.
4. Verificar SQLite y log.

### Happy flow C — engine modular
1. Instalar repo.
2. Correr test end-to-end del engine.
3. Hacer discovery real.
4. Descargar histórico.
5. Validar outputs CSV.

## 8.2 Alternative flows

### Si Gamma cambia el payload
- ajustar parsing en `discovery.py` o `service.py`,
- volver a correr tests de discovery/autopilot.

### Si CLOB responde pero no hay datos suficientes
- validar `token_id`,
- revisar si el mercado está activo,
- bajar el universo de prueba a pocos mercados.

### Si falla la autenticación
- comprobar `PK`, `CHAIN_ID` y credenciales L2,
- regenerar o derivar creds,
- revisar que no falte `CLOB_PASS_PHRASE`.

### Si el problema es allowance
- separar credenciales de autorización on-chain,
- probar `get_balance_allowance` antes de `update_balance_allowance`,
- no asumir que autenticación correcta implica permiso operativo correcto.

## 9. Necesidades técnicas para devs y mantenibilidad

## 9.1 Dependencias externas
- **Gamma API**: discovery / mercados.
- **CLOB API**: midpoint, histórico, trading, autenticación.
- **SQLite**: autopilot.
- **JSON**: mean reversion.
- **CSV**: polymarket_engine.

## 9.2 Qué probar por tipo
- **unit tests**: lógica de señales, parseo, persistencia local.
- **integration light**: HTTP real contra Gamma/CLOB sin autenticación.
- **regression tests**: payload parsing y artefactos generados.
- **manual checks**: credenciales, allowances, órdenes.

## 9.3 Seguridad
- nunca reutilizar credenciales reales en tests automatizados,
- no commitear `.env`,
- separar entornos de paper y real,
- probar allowances y autenticación por separado,
- evitar ejecutar órdenes reales hasta haber validado el flujo paper de punta a punta.

## 10. Plan de trabajo recomendado

## 10.1 MVP de validación técnica
Duración estimada: 1 sesión corta.

1. Instalar repo.
2. Ejecutar tests de `ToTheMoon` y engine.
3. Ejecutar autopilot una vez.
4. Ejecutar mean reversion una vez.

## 10.2 Validación online controlada
Duración estimada: 1 sesión adicional.

1. Discovery real en Gamma.
2. Histórico real en CLOB.
3. Confirmar outputs en CSV/SQLite/JSON.

## 10.3 Validación autenticada
Duración estimada: solo si realmente se necesita.

1. Configurar `.env`.
2. Crear/derivar creds.
3. Probar readonly.
4. Probar allowances.
5. Recién después, orden o RFQ.

## 10.4 Riesgos principales
- cambios de schema en Gamma/CLOB,
- confusión entre paper y real,
- credenciales mal configuradas,
- allowances incompletos,
- usar demasiados mercados en pruebas iniciales.

## 11. Ripple effects y documentación que conviene mantener actualizada

Si se modifica cualquiera de estos features, conviene actualizar:

- este documento,
- `ToTheMoon/README.md`,
- `ToTheMoon/strategies/polymarket_autopilot/README.md`,
- `docs/polymarket_engine_mvp/README.md`.

También conviene dejar claro en cada nuevo script:

- si usa Gamma o CLOB,
- si es read-only, paper o real,
- qué artefactos escribe,
- y qué secretos requiere.

## 12. Contexto más amplio y futuras extensiones

### Limitaciones actuales
- no hay un entrypoint unificado para todos los modos de `ToTheMoon`,
- la configuración está repartida entre dataclasses y scripts de ejemplo,
- no existe un `.env.example` oficial,
- algunas pruebas reales dependen de servicios externos cambiantes.

### Mejoras recomendadas
- crear `docs/env.example.md` o `.env.example`,
- añadir CLIs formales para discovery / history / paper runs,
- separar configuración por entorno (`dev`, `paper`, `real`),
- añadir smoke tests opcionales online con flags explícitos,
- documentar más claramente el paso de paper a real.

### Moonshot ideas
- dashboard único de estado para JSON/SQLite/CSV,
- scheduler común para mean reversion + autopilot + engine,
- validación automática de credenciales y allowances antes de cualquier orden,
- modo “doctor” que compruebe conectividad, paths, secrets y permisos antes de ejecutar features.
