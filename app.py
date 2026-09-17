"""
Market Maker Arena -- a simple browser game.

You and three bots each quote a two-sided market (a bid and an ask) every
round on a security whose "true value" drifts randomly, like a noisy coin
flip nudging the price up or down. Trades happen two ways each round:

  1. Direct trades: if your bid crosses someone else's ask (or vice versa),
     you trade directly with each other, at the midpoint of those two
     prices.
  2. The customer: one outside trader shows up every round and trades
     once, always taking whichever price is best across everyone's quotes.
     Sometimes the customer is "informed" -- it already knows which way
     the price is about to move, and only trades when that's good for it
     (which means bad for whoever it trades with). That's "adverse
     selection" in one sentence: informed flow picks off quotes that
     turn out to be mispriced right before the price moves.

At the end of every round the true value is revealed, and everyone's
position is marked to that price -- so you can see exactly how much you
made from capturing the spread, and how much you gained or lost from
whatever inventory you were carrying when the price moved.

Run it with:  python app.py    then open http://127.0.0.1:5050
"""

import random

from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

NUM_ROUNDS = 20
STARTING_VALUE = 100.0
STEP_STD = 1.5           # typical size of the random move in fair value each round
INFORMED_PROB = 0.35     # chance the customer already knows which way the price is headed
HISTORY_WINDOW = 8       # how many recent rounds bots look back at to gauge choppiness


def steady_eddie(state):
    """Quotes a constant $3 half-spread around the last known value. Never
    adjusts for inventory or recent volatility -- the naive baseline that
    gets run over."""
    mid = state["last_value"]
    return mid - 3.0, mid + 3.0


def nervous_nick(state):
    """Same fixed spread as Eddie, but leans its quotes against its own
    inventory: if it's built up a long position, it shifts both prices
    down, making itself a more attractive seller and a less attractive
    buyer, nudging its position back toward flat."""
    mid = state["last_value"]
    inv = state["inventories"]["Nervous Nick"]
    skew = -0.5 * inv
    center = mid + skew
    return center - 2.0, center + 2.0


def sharp_sam(state):
    """Widens its spread when the recent price history has been choppy
    (less sure where fair value really is), and leans against its own
    inventory harder than Nick does. This is the toughest bot to beat --
    it's a simplified version of the same idea real market-making desks
    use: quote wider when you're uncertain, and work harder to stay flat."""
    mid = state["last_value"]
    vol = state["recent_volatility"]
    inv = state["inventories"]["Sharp Sam"]
    half_spread = 1.0 + vol
    skew = -0.35 * inv
    center = mid + skew
    return center - half_spread, center + half_spread


BOTS = {
    "Steady Eddie": steady_eddie,
    "Nervous Nick": nervous_nick,
    "Sharp Sam": sharp_sam,
}
PARTICIPANTS = ["You", *BOTS.keys()]


def new_game():
    return {
        "round": 0,
        "last_value": STARTING_VALUE,
        "history": [STARTING_VALUE],
        "cash": {p: 0.0 for p in PARTICIPANTS},
        "inventories": {p: 0 for p in PARTICIPANTS},
        "recent_volatility": 0.0,
        "log": [],
        "game_over": False,
    }


GAME = new_game()


def compute_recent_volatility(history):
    window = history[-HISTORY_WINDOW:]
    if len(window) < 2:
        return 0.0
    steps = [abs(window[i] - window[i - 1]) for i in range(1, len(window))]
    return sum(steps) / len(steps)


def _execute(state, buyer, seller, price):
    """Settle one trade: the buyer pays cash and gains one unit of
    inventory, the seller receives cash and gives up one unit. "Customer"
    is not a real participant, so it has no cash/inventory to update."""
    if buyer != "Customer":
        state["cash"][buyer] -= price
        state["inventories"][buyer] += 1
    if seller != "Customer":
        state["cash"][seller] += price
        state["inventories"][seller] -= 1


def clear_round(state, bot_quotes, player_bid, player_ask):
    all_quotes = dict(bot_quotes)
    all_quotes["You"] = (player_bid, player_ask)

    trades = []

    best_bidder = max(all_quotes, key=lambda n: all_quotes[n][0])
    best_asker = min(all_quotes, key=lambda n: all_quotes[n][1])
    best_bid = all_quotes[best_bidder][0]
    best_ask = all_quotes[best_asker][1]

    if best_bidder != best_asker and best_bid >= best_ask:
        price = (best_bid + best_ask) / 2.0
        _execute(state, buyer=best_bidder, seller=best_asker, price=price)
        trades.append({
            "type": "crossed_market",
            "buyer": best_bidder,
            "seller": best_asker,
            "price": round(price, 2),
        })

    next_value = state["last_value"] + random.gauss(0, STEP_STD)
    is_informed = random.random() < INFORMED_PROB
    if is_informed:
        customer_wants_to_buy = next_value > state["last_value"]
    else:
        customer_wants_to_buy = random.random() < 0.5

    if customer_wants_to_buy:
        seller = min(all_quotes, key=lambda n: all_quotes[n][1])
        price = all_quotes[seller][1]
        _execute(state, buyer="Customer", seller=seller, price=price)
        trades.append({
            "type": "customer",
            "side": "buy",
            "counterparty": seller,
            "price": round(price, 2),
            "informed": is_informed,
        })
    else:
        buyer = max(all_quotes, key=lambda n: all_quotes[n][0])
        price = all_quotes[buyer][0]
        _execute(state, buyer=buyer, seller="Customer", price=price)
        trades.append({
            "type": "customer",
            "side": "sell",
            "counterparty": buyer,
            "price": round(price, 2),
            "informed": is_informed,
        })

    return all_quotes, trades, next_value


def public_state(state):
    pnl = {
        p: state["cash"][p] + state["inventories"][p] * state["last_value"]
        for p in PARTICIPANTS
    }
    return {
        "round": state["round"],
        "num_rounds": NUM_ROUNDS,
        "last_value": round(state["last_value"], 2),
        "history": [round(v, 2) for v in state["history"]],
        "inventories": state["inventories"],
        "cash": {p: round(c, 2) for p, c in state["cash"].items()},
        "pnl": {p: round(v, 2) for p, v in pnl.items()},
        "log": state["log"][-10:],
        "game_over": state["game_over"],
    }


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/state")
def api_state():
    return jsonify(public_state(GAME))


@app.route("/api/quote", methods=["POST"])
def api_quote():
    if GAME["game_over"]:
        return jsonify({"error": "Game over -- start a new game."}), 400

    data = request.get_json(force=True, silent=True) or {}
    try:
        bid = float(data["bid"])
        ask = float(data["ask"])
    except (KeyError, TypeError, ValueError):
        return jsonify({"error": "Bid and ask must both be numbers."}), 400

    if ask < bid:
        return jsonify({"error": "Your ask can't be below your bid."}), 400

    bot_quotes = {name: fn(GAME) for name, fn in BOTS.items()}
    all_quotes, trades, next_value = clear_round(GAME, bot_quotes, bid, ask)

    GAME["history"].append(next_value)
    GAME["last_value"] = next_value
    GAME["recent_volatility"] = compute_recent_volatility(GAME["history"])
    GAME["round"] += 1
    if GAME["round"] >= NUM_ROUNDS:
        GAME["game_over"] = True

    round_summary = {
        "round": GAME["round"],
        "quotes": {n: {"bid": round(b, 2), "ask": round(a, 2)} for n, (b, a) in all_quotes.items()},
        "trades": trades,
        "revealed_value": round(next_value, 2),
    }
    GAME["log"].append(round_summary)

    return jsonify({"round_summary": round_summary, "state": public_state(GAME)})


@app.route("/api/new_game", methods=["POST"])
def api_new_game():
    global GAME
    GAME = new_game()
    return jsonify(public_state(GAME))


if __name__ == "__main__":
    app.run(debug=True, port=5050)
