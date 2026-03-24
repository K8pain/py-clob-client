from ToTheMoon.strategies.automated_paper_v1_web.mean_reversion import MeanReversionPaperStrategy, StrategyConfig


class StubClient:
    def __init__(self, pages, midpoint):
        self.pages = pages
        self.midpoint = midpoint

    def get_simplified_markets(self, next_cursor="MA=="):
        return self.pages[next_cursor]

    def get_midpoint(self, token_id):
        return self.midpoint[token_id]


def test_discover_active_up_down_markets(tmp_path):
    cfg = StrategyConfig(
        state_file=str(tmp_path / "state.json"),
        trades_file=str(tmp_path / "trades.json"),
    )
    strategy = MeanReversionPaperStrategy(cfg)
    strategy.client = StubClient(
        pages={
            "MA==": {
                "data": [
                    {
                        "active": True,
                        "closed": False,
                        "question": "Will Bitcoin go Up or Down today?",
                        "market_slug": "btc-up-down",
                        "tokens": [{"outcome": "YES", "token_id": "1"}],
                    },
                    {
                        "active": True,
                        "closed": False,
                        "question": "Will gold rise?",
                        "market_slug": "gold-rise",
                        "tokens": [{"outcome": "YES", "token_id": "2"}],
                    },
                ],
                "next_cursor": "LTE=",
            }
        },
        midpoint={"1": 0.35},
    )

    markets = strategy.discover_active_up_down_markets()

    assert len(markets) == 1
    assert markets[0]["yes_token_id"] == "1"


def test_circuit_breaker_after_three_losses(tmp_path):
    cfg = StrategyConfig(
        state_file=str(tmp_path / "state.json"),
        trades_file=str(tmp_path / "trades.json"),
        buy_below=0.40,
        sell_above=0.60,
    )
    strategy = MeanReversionPaperStrategy(cfg)
    strategy.client = StubClient(
        pages={"MA==": {"data": [], "next_cursor": "LTE="}},
        midpoint={"1": 0.3},
    )

    market = {"market_slug": "btc-up-down", "yes_token_id": "1"}

    strategy.client.midpoint["1"] = 0.30
    strategy.evaluate_market(market)  # buy
    strategy.client.midpoint["1"] = 0.65
    strategy.evaluate_market(market)  # win

    for _ in range(3):
        strategy.client.midpoint["1"] = 0.30
        strategy.evaluate_market(market)  # buy
        strategy.client.midpoint["1"] = 0.61
        strategy.state["open_positions"]["1"]["entry_price"] = 0.70
        strategy.evaluate_market(market)  # sell loss

    assert strategy.state["consecutive_losses"] == 3
    assert strategy.state["circuit_breaker_active"] is True
