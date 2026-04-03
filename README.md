# Polymarket Python CLOB Client

<a href='https://pypi.org/project/py-clob-client'>
    <img src='https://img.shields.io/pypi/v/py-clob-client.svg' alt='PyPI'/>
</a>

Python client for the Polymarket Central Limit Order Book (CLOB).

## Documentation

- Arquitectura MVP del bot Polymarket (discovery, histórico, paper, backtester y real): `docs/polymarket_engine_mvp/README.md`.

## Resumen rápido de endpoints (qué usamos y qué más ofrece Polymarket)

Referencia oficial: https://docs.polymarket.com/api-reference/introduction

### 1) Endpoints que usamos en este repo (SDK + estrategias)

> Objetivo: dejar claro **qué enviamos**, **qué recibimos** y **cómo lo tratamos** en el cliente.

| Tipo | Endpoints (ejemplos) | Parámetros que enviamos | Respuesta que recibimos | Cómo lo tratamos en el código |
|---|---|---|---|---|
| Salud/tiempo | `GET /`, `GET /time` | Sin payload | Estado OK / timestamp del servidor | Uso directo para healthcheck y sincronía de reloj. |
| Descubrimiento de mercados | `GET /simplified-markets`, `GET /markets`, `GET /markets/{id}` | `next_cursor`, filtros de mercado | Listas/paginación con metadata de mercados | Iteramos con cursor (`next_cursor`) y filtramos tokens elegibles para estrategia. |
| Orderbook y precios | `GET /book`, `POST /books`, `GET /price(s)`, `GET /midpoint(s)`, `GET /spread(s)`, `GET /last-trade-price(s)` | `token_id` (o lista), `side` cuando aplica | Bids/asks, midpoint, spread, last trade, precios | Parseamos orderbook a `OrderBookSummary`; validamos hash; convertimos precios a `float` para señales. |
| Trading (órdenes) | `POST /order`, `POST /orders`, `DELETE /order`, `DELETE /orders`, `DELETE /cancel-all`, `GET /data/orders`, `GET /data/order/{id}` | Payload firmado (L2): token, side, size, price/tipo orden | Confirmación de orden, estado, listas de órdenes | Construimos orden con `OrderBuilder`, redondeamos por tick size, enviamos JSON firmado. |
| Trades | `GET /data/trades`, `GET /builder/trades` | Filtros (`market`, `asset_id`, `after`, `before`, `maker_address`, `next_cursor`) | Trades paginados | Armamos query params de forma incremental y consumimos por páginas. |
| Cuenta y permisos | `GET /balance-allowance`, `POST /balance-allowance/update`, `GET /order-scoring`, `POST /v1/heartbeats` | Parámetros de asset/signature type, IDs de orden | Balance/allowance, flags de scoring, ack heartbeat | Se usa para validar capacidad de operar y mantener sesiones de market maker. |
| Auth de API keys | `POST /auth/api-key`, `GET /auth/derive-api-key`, `GET /auth/api-keys`, readonly keys | Headers firmados L1/L2 | `apiKey`, `secret`, `passphrase`, listas de keys | Parseamos a `ApiCreds`; si crear falla hacemos fallback a derive. |
| RFQ | `/rfq/request`, `/rfq/quote`, `/rfq/data/*`, `/rfq/request/accept`, `/rfq/quote/approve` | `assetIn`, `assetOut`, `amountIn`, `amountOut`, IDs RFQ, filtros | Requests/quotes RFQ y estado de match | Convertimos unidades, redondeamos por tick, serializamos cuerpo exacto para firma L2. |

#### Tratamiento estándar de parámetros y respuestas

- **Request**: enviamos `Content-Type: application/json`, headers de auth según nivel (L0/L1/L2), y query params explícitos (sin magia implícita).
- **Errores**: toda respuesta HTTP distinta de `200` levanta `PolyApiException`.
- **Respuesta**: si hay JSON, devolvemos `dict`; si no, texto plano.
- **Tipado interno**: para partes críticas (orderbook, api creds, RFQ payload), convertimos a tipos del cliente (`OrderBookSummary`, `ApiCreds`, etc.).
- **Precisión**: precio/tamaño se redondean con la configuración de tick size antes de enviar órdenes/RFQ.

### 2) Qué otras APIs ofrece Polymarket (además de lo que ya usamos)

Polymarket separa dominios en varias APIs. Esto nos permite elegir el canal correcto según caso de uso.

| API | Base URL | ¿Auth? | Para qué sirve | Endpoints útiles a evaluar |
|---|---|---|---|---|
| **Gamma API** | `https://gamma-api.polymarket.com` | Pública | Discovery/browsing: eventos, mercados, tags, series, comments, sports, search, perfiles públicos | Events (`list/get`), Markets (`list/by-slug`), Search, Tags, Series, Comments, Sports metadata |
| **Data API** | `https://data-api.polymarket.com` | Pública | Analytics y datos de usuario/mercado | Posiciones abiertas/cerradas, actividad de usuario, holders, open interest, leaderboards, builder analytics |
| **CLOB API** | `https://clob.polymarket.com` | Mixta (público + trading autenticado) | Precios/orderbook + ejecución (órdenes, cancelaciones, trades, RFQ) | Price history, rewards/rebates, profile endpoints, leaderboard, websockets market/user/sports |
| **Bridge API** | `https://bridge.polymarket.com` | Según operación | Depósitos/retiros (proxy de fun.xyz) | Supported assets, create deposit/withdrawal addresses, quote, tx status |
| **Relayer API** | (documentada en API Reference) | Sí, según endpoint | Envío y seguimiento de transacciones de relayer/safe | Submit transaction, tx by id, recent txs, nonce actual, safe deployed, API keys |

### 3) Compendio corto de “qué enviar / qué recibir” por familia

| Familia | Enviamos típicamente | Recibimos típicamente |
|---|---|---|
| Discovery (Gamma/CLOB markets) | `limit`, `offset`/`cursor`, `slug`, `tag`, filtros de estado | Objetos de mercado/evento, tags, timestamps, estado de mercado |
| Pricing/Orderbook (CLOB) | `token_id` (uno o varios), `side`, rango temporal en histórico | `bids/asks`, `midpoint`, `spread`, `last_trade_price`, series históricas |
| Orders/Trading (CLOB) | Orden firmada (price, size, side, token, nonce/salt, tipo), IDs para cancelación | Ack de creación/cancelación, estado de orden, órdenes paginadas |
| Trades/Activity (CLOB/Data) | Filtros por `market`, `asset_id`, ventana temporal, dirección | Trades/actividad paginada, métricas agregadas |
| Cuenta/Perfil (Data/CLOB profile) | Wallet address, fechas/rangos, filtros de mercado | Posiciones, PnL/valor, estadísticas por usuario |
| RFQ (CLOB) | `assetIn/out`, `amountIn/out`, request/quote IDs, aceptación/aprobación | RFQ requests/quotes, mejor cotización, estado de ejecución |

> Recomendación MVP: mantener **Gamma + CLOB público** para discovery/pricing, activar **CLOB autenticado** solo en ejecución, y sumar **Data API** cuando necesitemos analítica de rendimiento o reporting avanzado.

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
