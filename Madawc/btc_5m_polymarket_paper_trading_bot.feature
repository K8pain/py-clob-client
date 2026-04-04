Feature: btc_5m_polymarket_paper_trading_bot
  # Objetivo:
  # Implementar un bot 24/7 en Python/Linux para paper trading sobre mercados
  # Bitcoin Up/Down de 5 minutos en Polymarket, sin órdenes reales.

  Background:
    Given the bot uses only public market-data endpoints
    And the bot does not call authenticated trading endpoints
    And the seed frontend URL is "https://polymarket.com/es/event/btc-updown-5m-1774854300"
    And the seed event slug is "btc-updown-5m-1774854300"
    And the canonical BTC 5m family prefix is "btc-updown-5m-"
    And the family title prefix is "Bitcoin Up or Down -"

  Scenario: exact_real_workflow
    Given the system is started
    Then the runtime order is exactly:
      """
      1. Sync server time from CLOB /time.
      2. Validate the seed event by GET /events/slug/btc-updown-5m-1774854300.
      3. Discover all active and unclosed Gamma events with paginated GET /events?active=true&closed=false.
      4. Keep only event/market rows from the BTC 5m family using slug/title predicates.
      5. Fetch all paginated CLOB simplified markets.
      6. Keep only active, unclosed, unarchived, accepting_orders CLOB rows.
      7. Join Gamma and CLOB by token overlap.
      8. Map outcomes exactly to Up and Down tokens.
      9. Enrich each selected market with tick size, fee rate, and initial book snapshots.
      10. Open the market websocket and subscribe to every selected token.
      11. Open the RTDS websocket and subscribe to btcusdt crypto prices.
      12. Recompute classification every second.
      13. Build live price snapshots from websocket state.
      14. Emit a confidence_099 signal only when best_bid >= 0.99, spread <= 0.01, and seconds_to_close is inside the entry window.
      15. Create one BUY paper order of 1 share on the chosen outcome.
      16. Fill at best ask, else midpoint, else last trade, else reject.
      17. Debit notional and fee from the paper ledger.
      18. Mark positions every second until resolution.
      19. Settle from market_resolved or winner flags from simplified-markets.
      20. Credit payout, compute realized PnL, close the position, and persist all artifacts.
      21. Repeat discovery every 30 seconds forever.
      """

  Scenario: prompt_detailed_for_code_implementation
    Given the following prompt is the implementation contract
    Then the exact prompt text is:
      """
      Implement a production-style Python/Linux 24/7 paper-trading bot for Polymarket BTC 5-minute markets only.

      Hard scope:
      - Asset family: only frontend slugs that start with "btc-updown-5m-".
      - Seed validation slug: "btc-updown-5m-1774854300".
      - No real trading. Never call authenticated CLOB order endpoints.
      - Use Gamma API for discovery and CLOB API / py-clob-client-compatible models for market data.
      - Persist all state durably to a local ledger store.
      - Use UTC internally and CLOB /time as authoritative clock when skew > 2 seconds.

      WebSocket contract:
      - Market channel: wss://ws-subscriptions-clob.polymarket.com/ws/market
      - RTDS channel: wss://ws-live-data.polymarket.com

      Strategy:
      - Name: confidence_099
      - Evaluate only markets in entry_window.
      - Emit SignalCandidate when best_bid >= 0.99, spread <= 0.01 and opposite ask <= 0.01.

      Paper execution:
      - Create exactly one BUY order of quantity 1.0 share per signal.
      - Fill price priority: best ask, midpoint, last trade, else reject.

      Ledger:
      - initial cash: 10000.00 paper USDC
      - no leverage
      - no shorting
      """
