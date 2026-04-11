"""Constantes y configuración por entorno para ejecutar KORLIC v2."""

from __future__ import annotations

import os

# URL base del API Gamma usado para descubrir mercados.
DEFAULT_GAMMA_BASE_URL = "https://gamma-api.polymarket.com"
# URL base del CLOB usado para leer orderbooks y operar.
DEFAULT_CLOB_HOST = "https://clob.polymarket.com"
# Espera mínima entre requests a Gamma para evitar rate limit.
DEFAULT_GAMMA_MIN_INTERVAL_SECONDS = 0.25
# Espera mínima entre requests al CLOB para evitar rate limit.
DEFAULT_CLOB_MIN_INTERVAL_SECONDS = 0.05
# Cantidad máxima de mercados por página en Gamma.
DEFAULT_GAMMA_PAGE_LIMIT = 100
# Número máximo de páginas a pedir en Gamma (0 = sin límite manual).
DEFAULT_GAMMA_MAX_PAGES = 0
# Evento semilla usado para arrancar discovery incluso con paginación vacía.
DEFAULT_GAMMA_SEED_EVENT_SLUG = "btc-updown-5m-1774854300"
# Ventana de segundos previa al expiry donde el mercado se considera operable.
DEFAULT_MARKET_NEAR_EXPIRY_SECONDS = 900
# Intervalo entre ciclos completos del bot.
DEFAULT_LOOP_INTERVAL_SECONDS = 240.0

# Precio de entrada esperado para disparar señal.
DEFAULT_SIGNAL_ENTRY_PRICE = 0.97
# Segundos a expiry máximos permitidos para entrar.
DEFAULT_SIGNAL_ENTRY_SECONDS = 600
# Profundidad mínima del orderbook para considerar entrada.
DEFAULT_SIGNAL_MIN_DEPTH = 10.0
# Tamaño mínimo de orden permitido por la estrategia.
DEFAULT_SIGNAL_MIN_SIZE = 5.0
# Stake máximo por trade.
DEFAULT_SIGNAL_MAX_STAKE = 25.0
# Número máximo de trades por mercado.
DEFAULT_MAX_TRADES_PER_MARKET = 1
# Modo de selección de lado del orderbook (0=actual, 1=lado YES/UP, 2=lado NO/DOWN).
DEFAULT_ORDERBOOK_SIDE_MODE = 0
# Si es True, reinicia la base sqlite al iniciar.
DEFAULT_RESET_DB_ON_START = False
# Pausa opcional entre pasos internos de un ciclo.
DEFAULT_CYCLE_STEP_SLEEP_SECONDS = 0.0
# Prefijos de mercados que deben ignorarse durante discovery.
DEFAULT_SKIPPED_MARKET_PREFIXES = (
    "Bitcoin above",
    "Counter-Strike",
    "Ethereum above",
    "Game 2:",
    "Game Handicap: SN (-1.5) vs CCG Esports (+1.5)",
    "Games Total: O/U 2.5",
    "HYPE Up or Down",
    "Hyperliquid Up or Down",
    "LoL: Supernova vs CCG Esports (BO3) - North American Challengers League Regular Season",
    "LoL: Supernova vs CCG Esports - Game 2 Winner",
    "Map x: Odd/Even",
    "Map Handicap:",
    "Valorant: Akave Esports Black vs MYVRA GC (BO3) - VCT Game Changers Latin America North Playoffs",
    "Valorant: Akave Esports Black vs MYVRA GC - Map 1 Winner",
    "Valorant: Akave Esports Black vs MYVRA GC - Map 2 Winner",
    "Valorant: KRÜ Blaze vs Olimpo Gold (BO3) - VCT Game Changers Latin America South Playoffs",
    "Valorant: KRÜ Blaze vs Olimpo Gold - Map 2 Winner",
    "Will Bitcoin dip",
    "Will Bitcoin reach",
    "Will Ethereum dip",
    "Will Ethereum reach",
    "Will Solana dip",
    "Will Solana reach",
    "Will XRP dip",
    "Will XRP reach",
)

# Configuración final: defaults + override por variables de entorno.
# Base URL final de Gamma usada por PublicGammaClient.
KORLIC_GAMMA_BASE_URL = os.getenv("KORLIC_GAMMA_BASE_URL", DEFAULT_GAMMA_BASE_URL)
# Base URL final del CLOB.
KORLIC_CLOB_HOST = os.getenv("KORLIC_CLOB_HOST", DEFAULT_CLOB_HOST)
# Throttle final para llamadas a Gamma.
KORLIC_GAMMA_MIN_INTERVAL_SECONDS = float(
    os.getenv("KORLIC_GAMMA_MIN_INTERVAL_SECONDS", str(DEFAULT_GAMMA_MIN_INTERVAL_SECONDS))
)
# Throttle final para llamadas al CLOB.
KORLIC_CLOB_MIN_INTERVAL_SECONDS = float(
    os.getenv("KORLIC_CLOB_MIN_INTERVAL_SECONDS", str(DEFAULT_CLOB_MIN_INTERVAL_SECONDS))
)
# Límite final de registros por página de Gamma.
KORLIC_GAMMA_PAGE_LIMIT = int(os.getenv("KORLIC_GAMMA_PAGE_LIMIT", str(DEFAULT_GAMMA_PAGE_LIMIT)))
# Tope final de páginas a consultar en Gamma.
KORLIC_GAMMA_MAX_PAGES = int(os.getenv("KORLIC_GAMMA_MAX_PAGES", str(DEFAULT_GAMMA_MAX_PAGES)))
# Slug semilla final para bootstrap de discovery en Gamma.
KORLIC_GAMMA_SEED_EVENT_SLUG = os.getenv("KORLIC_GAMMA_SEED_EVENT_SLUG", DEFAULT_GAMMA_SEED_EVENT_SLUG)
# Ventana final near-expiry para seleccionar mercados operables.
KORLIC_MARKET_NEAR_EXPIRY_SECONDS = int(
    os.getenv("KORLIC_MARKET_NEAR_EXPIRY_SECONDS", str(DEFAULT_MARKET_NEAR_EXPIRY_SECONDS))
)
# Precio de entrada final.
KORLIC_SIGNAL_ENTRY_PRICE = float(os.getenv("KORLIC_SIGNAL_ENTRY_PRICE", str(DEFAULT_SIGNAL_ENTRY_PRICE)))
# Segundos de entrada final.
KORLIC_SIGNAL_ENTRY_SECONDS = int(os.getenv("KORLIC_SIGNAL_ENTRY_SECONDS", str(DEFAULT_SIGNAL_ENTRY_SECONDS)))
# Profundidad mínima final.
KORLIC_SIGNAL_MIN_DEPTH = float(os.getenv("KORLIC_SIGNAL_MIN_DEPTH", str(DEFAULT_SIGNAL_MIN_DEPTH)))
# Tamaño mínimo final de orden.
KORLIC_SIGNAL_MIN_SIZE = float(os.getenv("KORLIC_SIGNAL_MIN_SIZE", str(DEFAULT_SIGNAL_MIN_SIZE)))
# Stake máximo final.
KORLIC_SIGNAL_MAX_STAKE = float(os.getenv("KORLIC_SIGNAL_MAX_STAKE", str(DEFAULT_SIGNAL_MAX_STAKE)))
# Máximo de trades final por mercado.
KORLIC_MAX_TRADES_PER_MARKET = int(os.getenv("KORLIC_MAX_TRADES_PER_MARKET", str(DEFAULT_MAX_TRADES_PER_MARKET)))
# Modo final de selección de lado del orderbook.
KORLIC_ORDERBOOK_SIDE_MODE = int(os.getenv("KORLIC_ORDERBOOK_SIDE_MODE", str(DEFAULT_ORDERBOOK_SIDE_MODE)))
# Pausa final entre pasos del ciclo.
KORLIC_CYCLE_STEP_SLEEP_SECONDS = float(
    os.getenv("KORLIC_CYCLE_STEP_SLEEP_SECONDS", str(DEFAULT_CYCLE_STEP_SLEEP_SECONDS))
)
# Intervalo final entre ciclos completos.
KORLIC_LOOP_INTERVAL_SECONDS = float(os.getenv("KORLIC_LOOP_INTERVAL_SECONDS", str(DEFAULT_LOOP_INTERVAL_SECONDS)))
# Lista final de prefijos ignorados.
KORLIC_SKIPPED_MARKET_PREFIXES = tuple(
    prefix.strip()
    for prefix in os.getenv("KORLIC_SKIPPED_MARKET_PREFIXES", "\n".join(DEFAULT_SKIPPED_MARKET_PREFIXES)).splitlines()
    if prefix.strip()
)
# Bandera final para reiniciar DB al inicio.
KORLIC_RESET_DB_ON_START = os.getenv("KORLIC_RESET_DB_ON_START", str(DEFAULT_RESET_DB_ON_START)).strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)
