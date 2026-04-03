# Polymarket Python CLOB Client

<a href='https://pypi.org/project/py-clob-client'>
    <img src='https://img.shields.io/pypi/v/py-clob-client.svg' alt='PyPI'/>
</a>

Python client for the Polymarket Central Limit Order Book (CLOB).

## Documentation

- Arquitectura MVP del bot Polymarket (discovery, histórico, paper, backtester y real): `docs/polymarket_engine_mvp/README.md`.

## Resumen rápido de APIs y endpoints de Polymarket

> Fuente oficial: https://docs.polymarket.com/api-reference/introduction

### 1) Endpoints que **sí usamos** en este repo (py-clob-client)

| Dominio | Endpoint(s) | Qué enviamos (request) | Qué recibimos (response) | Cómo lo tratamos en el cliente |
|---|---|---|---|---|
| Salud/tiempo | `/` , `/time` | Sin auth ni body | Estado OK y timestamp del servidor | Se usan para health-check y sincronización básica. |
| Orderbook & pricing | `/book`, `/books`, `/price`, `/prices`, `/midpoint`, `/midpoints`, `/spread`, `/spreads`, `/last-trade-price`, `/last-trades-prices`, `/tick-size`, `/neg-risk`, `/fee-rate` | `token_id` (o lista de `token_ids`), `side` en precios puntuales | Precio, midpoint, spread, últimos trades, libro de órdenes, metadatos de ejecución (tick/fee/risk) | Se parsea a estructuras internas (por ejemplo `OrderBookSummary`) y se cachean `tick-size`, `neg-risk` y `fee-rate` para reducir llamadas repetidas. |
| Órdenes (trading) | `/order`, `/orders`, `/data/order/{id}`, `/data/orders`, `/cancel-all`, `/cancel-market-orders`, `/order-scoring`, `/orders-scoring`, `/v1/heartbeats` | Payload firmado (L2) con orden(es), filtros para listar/cancelar, heartbeat de builder | Confirmación de alta/cancelación, estado de orden, listado paginado, estado de scoring | Se firma con headers L2; para crear órdenes se redondea precio/size según `tick-size` antes de enviar. |
| Auth de CLOB | `/auth/api-key`, `/auth/derive-api-key`, `/auth/api-keys`, `/auth/readonly-*`, `/auth/ban-status/closed-only` | Firma L1/L2, nonce opcional | Credenciales API (`apiKey`, `secret`, `passphrase`) y estado de acceso | Flujo create-or-derive para credenciales; modo automático L0/L1/L2 según claves presentes. |
| Trades & notificaciones | `/data/trades`, `/builder/trades`, `/notifications` | Filtros (mercado, usuario, cursor) y drop params para limpiar notifs | Trades paginados y notificaciones | Se maneja paginación por `next_cursor` hasta `END_CURSOR`. |
| Mercados CLOB | `/markets`, `/markets/{condition_id}`, `/simplified-markets`, `/sampling-markets`, `/sampling-simplified-markets`, `/live-activity/events/{condition_id}` | `next_cursor`, `condition_id` | Catálogo de mercados (normal o simplificado) y actividad | Se usa para discovery rápido y para enriquecer decisiones de trading. |
| Balance/allowance | `/balance-allowance`, `/balance-allowance/update` | Parámetros de activo/tipo de firma/funder | Balance y allowance vigentes + resultado de actualización | Se consulta/actualiza antes de operar para validar capacidad de ejecución. |
| RFQ | `/rfq/request`, `/rfq/quote`, `/rfq/data/*`, `/rfq/config` | Requests/quotes firmados con montos (`assetIn/Out`, `amountIn/Out`) y filtros | Estado de requests/quotes, best quote, config RFQ | Se calcula monto según side (BUY/SELL), se redondea por tick-size y luego se firma L2. |

### 2) Otras APIs/endpoints que **no son el core actual** pero podrían servirnos

> Polymarket separa 3 APIs principales: **Gamma** (discovery), **Data** (analytics/usuario), **CLOB** (orderbook + trading), más **Bridge/Relayer** y **WebSocket**.

| API / Área | Endpoints útiles (ejemplos) | Parámetros típicos a enviar | Respuesta típica | Cuándo nos conviene |
|---|---|---|---|---|
| Gamma API (`gamma-api.polymarket.com`) | Events, Markets, Tags, Series, Comments, Search, Sports | `id`, `slug`, `tag`, `limit`, `offset`, filtros por estado/fecha | Objetos de mercado/evento + listas paginadas de metadata pública | Discovery avanzado, filtrado temático y features de exploración para seleccionar universo operable. |
| Data API (`data-api.polymarket.com`) | Positions, User activity, Holders, Open interest, Leaderboards, Builder analytics | `user`, `market`, rango de fechas, `limit/cursor` | Métricas históricas, posiciones, actividad y rankings | Señales cuantitativas, scoring de mercados y análisis post-trade. |
| CLOB extra (además de lo ya usado) | Price history, rebates, rewards endpoints | `token_id`/`market`, fechas, wallet, cursores | Series temporales de precio + datos de rebates/rewards | Optimización de ejecución y evaluación de rentabilidad neta (fees/rebates/rewards). |
| Profile | Public profile, open/closed positions, activity, portfolio value, trades, snapshot CSV | `wallet`, filtros de fecha/mercado | Estado de cuenta y actividad detallada | Reporting, auditoría operativa y reconciliación. |
| Bridge API (`bridge.polymarket.com`) | Supported assets, create deposit/withdraw address, quote, tx status | Asset/red, amount, address destino/origen | Rutas y estado de depósitos/retiros | Si automatizamos flujo de fondos (treasury / cash management). |
| Relayer API | Submit tx, tx by id, recent txs, nonce, safe deployed, API keys | Payload de transacción, `user`, `nonce` | Estado de transacciones y metadatos de relayer | Operación avanzada con safes/proxies y control fino de envío onchain. |
| WebSocket | Market channel, User channel, Sports channel | Suscripción por `market`/`asset`/usuario | Eventos en tiempo real (book, trades, user updates) | Estrategias low-latency, alertas y UIs en vivo. |

### 3) Compendio mínimo de contratos de request/response (guía práctica)

| Tipo de endpoint | Request: campos clave | Response: campos clave | Regla práctica de tratamiento |
|---|---|---|---|
| Listados paginados | `limit`, `next_cursor`/`cursor`, filtros (`market`, `user`, `start/end`) | `data` (lista), `next_cursor` | Iterar hasta cursor final; deduplicar por `id`. |
| Lookup por recurso | `id`, `slug`, `condition_id`, `token_id` | Objeto único de mercado/evento/orden | Validar `None`/404 y degradar sin romper pipeline. |
| Pricing/orderbook | `token_id` (1 o N), `side` opcional | bid/ask, midpoint, spread, last price, niveles de libro | Normalizar floats/decimals y timestamp; cachear datos semiestables (tick/fee/risk). |
| Trading autenticado | Firma L1/L2 + body firmado (`price`, `size`, `side`, `token_id`, tipo orden) | Ack de orden + `order_id`/estado/error | Firmar siempre contra `request_path` exacto y redondear a tick-size antes de enviar. |
| Balance/riesgo | `asset_type`, `signature_type`, `funder` | balance, allowance, flags de riesgo/scoring | Chequear pre-trade y bloquear operación si no cumple límites. |
| RFQ | request/quote con `assetIn/Out`, `amountIn/Out`, `userType` | `requestId`, `quoteId`, best quote, estado | Calcular montos por lado (BUY/SELL), firmar L2 y auditar ciclo request→quote→accept. |

### 4) Opciones concretas para ampliar el bot (prioridad sugerida)

1. **WebSocket market/user** para pasar de polling a streaming real-time.  
2. **Data API (positions + activity + open interest)** para filtros y risk overlays basados en evidencia histórica.  
3. **Rewards/Rebates** para optimizar ejecución neta (no solo precio bruto).  
4. **Profile/accounting snapshot** para conciliación diaria automática.  
5. **Bridge/Relayer** solo si vamos a automatizar treasury y operaciones de infraestructura wallet/safe.


## Talic

- Talic implementation overview: `Talic/README.md`
- Talic operations runbook: `docs/talic_runbook.md`

## Installation

```bash
# install from PyPI (Python 3.9>)
pip install py-clob-client
```
## Usage

The examples below are short and copy‑pasteable.

- What you need:
  - **Python 3.9+**
  - **Private key** that owns funds on Polymarket
  - Optional: a **proxy/funder address** if you use an email or smart‑contract wallet
  - Tip: store secrets in environment variables (e.g., with `.env`)

### Quickstart (read‑only)

```python
from py_clob_client.client import ClobClient

client = ClobClient("https://clob.polymarket.com")  # Level 0 (no auth)

ok = client.get_ok()
time = client.get_server_time()
print(ok, time)
```

### Start trading (EOA)

**Note**: If using MetaMask or hardware wallet, you must first set token allowances. See [Token Allowances section](#important-token-allowances-for-metamaskeoa-users) below.

```python
from py_clob_client.client import ClobClient

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137
PRIVATE_KEY = "<your-private-key>"
FUNDER = "<your-funder-address>"

client = ClobClient(
    HOST,  # The CLOB API endpoint
    key=PRIVATE_KEY,  # Your wallet's private key
    chain_id=CHAIN_ID,  # Polygon chain ID (137)
    signature_type=1,  # 1 for email/Magic wallet signatures
    funder=FUNDER  # Address that holds your funds
)
client.set_api_creds(client.create_or_derive_api_creds())
```

### Start trading (proxy wallet)

For email/Magic or browser wallet proxies, you need to specify two additional parameters:

#### Funder Address
The **funder address** is the actual address that holds your funds on Polymarket. When using proxy wallets (email wallets like Magic or browser extension wallets), the signing key differs from the address holding the funds. The funder address ensures orders are properly attributed to your funded account.

#### Signature Types
The **signature_type** parameter tells the system how to verify your signatures:
- `signature_type=0` (default): Standard EOA (Externally Owned Account) signatures - includes MetaMask, hardware wallets, and any wallet where you control the private key directly
- `signature_type=1`: Email/Magic wallet signatures (delegated signing)
- `signature_type=2`: Browser wallet proxy signatures (when using a proxy contract, not direct wallet connections)

```python
from py_clob_client.client import ClobClient

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137
PRIVATE_KEY = "<your-private-key>"
PROXY_FUNDER = "<your-proxy-or-smart-wallet-address>"  # Address that holds your funds

client = ClobClient(
    HOST,  # The CLOB API endpoint
    key=PRIVATE_KEY,  # Your wallet's private key
    chain_id=CHAIN_ID,  # Polygon chain ID (137)
    signature_type=1,  # 1 for email/Magic wallet signatures
    funder=PROXY_FUNDER  # Address that holds your funds
)
client.set_api_creds(client.create_or_derive_api_creds())
```

### Find markets, prices, and orderbooks

```python
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import BookParams

client = ClobClient("https://clob.polymarket.com")  # read-only

token_id = "<token-id>"  # Get a token ID: https://docs.polymarket.com/developers/gamma-markets-api/get-markets

mid = client.get_midpoint(token_id)
price = client.get_price(token_id, side="BUY")
book = client.get_order_book(token_id)
books = client.get_order_books([BookParams(token_id=token_id)])
print(mid, price, book.market, len(books))
```

### Place a market order (buy by $ amount)

**Note**: EOA/MetaMask users must set token allowances before trading. See [Token Allowances section](#important-token-allowances-for-metamaskeoa-users) below.

```python
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import MarketOrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137
PRIVATE_KEY = "<your-private-key>"
FUNDER = "<your-funder-address>"

client = ClobClient(
    HOST,  # The CLOB API endpoint
    key=PRIVATE_KEY,  # Your wallet's private key
    chain_id=CHAIN_ID,  # Polygon chain ID (137)
    signature_type=1,  # 1 for email/Magic wallet signatures
    funder=FUNDER  # Address that holds your funds
)
client.set_api_creds(client.create_or_derive_api_creds())

mo = MarketOrderArgs(token_id="<token-id>", amount=25.0, side=BUY, order_type=OrderType.FOK)  # Get a token ID: https://docs.polymarket.com/developers/gamma-markets-api/get-markets
signed = client.create_market_order(mo)
resp = client.post_order(signed, OrderType.FOK)
print(resp)
```

### Place a limit order (shares at a price)

**Note**: EOA/MetaMask users must set token allowances before trading. See [Token Allowances section](#important-token-allowances-for-metamaskeoa-users) below.

```python
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OrderArgs, OrderType
from py_clob_client.order_builder.constants import BUY

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137
PRIVATE_KEY = "<your-private-key>"
FUNDER = "<your-funder-address>"

client = ClobClient(
    HOST,  # The CLOB API endpoint
    key=PRIVATE_KEY,  # Your wallet's private key
    chain_id=CHAIN_ID,  # Polygon chain ID (137)
    signature_type=1,  # 1 for email/Magic wallet signatures
    funder=FUNDER  # Address that holds your funds
)
client.set_api_creds(client.create_or_derive_api_creds())

order = OrderArgs(token_id="<token-id>", price=0.01, size=5.0, side=BUY)  # Get a token ID: https://docs.polymarket.com/developers/gamma-markets-api/get-markets
signed = client.create_order(order)
resp = client.post_order(signed, OrderType.GTC)
print(resp)
```

### Manage orders

**Note**: EOA/MetaMask users must set token allowances before trading. See [Token Allowances section](#important-token-allowances-for-metamaskeoa-users) below.

```python
from py_clob_client.client import ClobClient
from py_clob_client.clob_types import OpenOrderParams

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137
PRIVATE_KEY = "<your-private-key>"
FUNDER = "<your-funder-address>"

client = ClobClient(
    HOST,  # The CLOB API endpoint
    key=PRIVATE_KEY,  # Your wallet's private key
    chain_id=CHAIN_ID,  # Polygon chain ID (137)
    signature_type=1,  # 1 for email/Magic wallet signatures
    funder=FUNDER  # Address that holds your funds
)
client.set_api_creds(client.create_or_derive_api_creds())

open_orders = client.get_orders(OpenOrderParams())

order_id = open_orders[0]["id"] if open_orders else None
if order_id:
    client.cancel(order_id)

client.cancel_all()
```

### Markets (read‑only)

```python
from py_clob_client.client import ClobClient

client = ClobClient("https://clob.polymarket.com")
markets = client.get_simplified_markets()
print(markets["data"][:1])
```

### User trades (requires auth)

**Note**: EOA/MetaMask users must set token allowances before trading. See [Token Allowances section](#important-token-allowances-for-metamaskeoa-users) below.

```python
from py_clob_client.client import ClobClient

HOST = "https://clob.polymarket.com"
CHAIN_ID = 137
PRIVATE_KEY = "<your-private-key>"
FUNDER = "<your-funder-address>"

client = ClobClient(
    HOST,  # The CLOB API endpoint
    key=PRIVATE_KEY,  # Your wallet's private key
    chain_id=CHAIN_ID,  # Polygon chain ID (137)
    signature_type=1,  # 1 for email/Magic wallet signatures
    funder=FUNDER  # Address that holds your funds
)
client.set_api_creds(client.create_or_derive_api_creds())

last = client.get_last_trade_price("<token-id>")
trades = client.get_trades()
print(last, len(trades))
```

## Important: Token Allowances for MetaMask/EOA Users

### Do I need to set allowances?
- **Using email/Magic wallet?** No action needed - allowances are set automatically.
- **Using MetaMask or hardware wallet?** You need to set allowances before trading.

### What are allowances?
Think of allowances as permissions. Before Polymarket can move your funds to execute trades, you need to give the exchange contracts permission to access your USDC and conditional tokens.

### Quick Setup
You need to approve two types of tokens:
1. **USDC** (for deposits and trading)
2. **Conditional Tokens** (the outcome tokens you trade)

Each needs approval for the exchange contracts to work properly.

### Setting Allowances
Here's a simple breakdown of what needs to be approved:

**For USDC (your trading currency):**
- Token: `0x2791Bca1f2de4661ED88A30C99A7a9449Aa84174`
- Approve for these contracts:
  - `0x4bFb41d5B3570DeFd03C39a9A4D8dE6Bd8B8982E` (Main exchange)
  - `0xC5d563A36AE78145C45a50134d48A1215220f80a` (Neg risk markets)
  - `0xd91E80cF2E7be2e162c6513ceD06f1dD0dA35296` (Neg risk adapter)

**For Conditional Tokens (your outcome tokens):**
- Token: `0x4D97DCd97eC945f40cF65F87097ACe5EA0476045`
- Approve for the same three contracts above

### Example Code
See [this Python example](https://gist.github.com/poly-rodr/44313920481de58d5a3f6d1f8226bd5e) for setting allowances programmatically.

**Pro tip**: You only need to set these once per wallet. After that, you can trade freely.

## Notes
- To discover token IDs, use the Markets API Explorer: [Get Markets](https://docs.polymarket.com/developers/gamma-markets-api/get-markets).
- Prices are in dollars from 0.00 to 1.00. Shares are whole or fractional units of the outcome token.

See [/example](/examples) for more.