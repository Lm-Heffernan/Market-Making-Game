# Market Maker Arena

A browser game: you and three bots each quote a two-sided market every
round on a security whose fair value drifts randomly. Trades happen when
quotes cross, and a "customer" trades once per round against whoever's
showing the best price — sometimes with foreknowledge of which way the
price is about to move (adverse selection).

## Run it

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

Then open http://127.0.0.1:5050

## Deploy it (make it a public link)

Free option: [Render](https://render.com).

1. Push this repo to GitHub (already done if you're reading this on GitHub).
2. On Render: **New > Web Service**, connect this repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Deploy. Render gives you a public `https://...onrender.com` URL.

Free tier sleeps after 15 minutes idle and takes ~30–50s to wake back up
on the next visit — normal, not a bug. Each visitor gets their own
independent game (tracked by a session cookie), so multiple people can
play at once without interfering with each other.

## How the game works

Each round, every participant (you + 3 bots) posts a **bid** (price they'll
buy at) and an **ask** (price they'll sell at), without seeing anyone
else's quotes. Two things can trade:

1. **Crossed quotes.** If the best bid on the board is `>=` the best ask,
   those two participants trade with each other at the midpoint. Quote too
   aggressively (bid too high, or ask too low) and someone else's quote
   might trade right through you.
2. **The customer.** One outside trader shows up every round and always
   takes the single best price available — buying at the lowest ask or
   selling to the highest bid. With some probability, the customer is
   *informed*: it already knows which way the fair value is about to move,
   and only trades when that's bad for its counterparty. That's adverse
   selection in one sentence — quoting a careless or stale price gets you
   picked off right before the market moves against you.

At the end of every round the fair value is revealed and everyone's
position (cash + inventory) is marked to that price, so you can see
directly how much of your P&L came from capturing the spread versus how
much came from the inventory you were carrying when the price moved.

## The bots

- **Steady Eddie** — a constant $3 half-spread around the last known
  value. Never adjusts for inventory or recent volatility. The naive
  baseline that gets run over once it builds a big position.
- **Nervous Nick** — same fixed spread as Eddie, but shifts both quotes
  down when he's long: his ask gets cheaper (more attractive to buyers,
  helping him sell down his position) and his bid gets less attractive
  (less likely to buy even more). He does the reverse when short, nudging
  his inventory back toward flat either way.
- **Sharp Sam** — widens his spread when the recent price history has
  been choppy, and leans against his own inventory harder than Nick. The
  toughest bot to beat, but still just a heuristic — not a stochastic
  control model — so there's real room to beat him with good judgment
  about when to quote wide vs. tight.

## Architecture

Three layers, no database:

```
Browser (templates/index.html + vanilla JS)
   |  fetch() calls to /api/*
Flask routes (app.py)
   |  read / write
In-memory game state (one plain dict per visitor)
```

**Data model.** A "game" is a single dict: `round`, `last_value` (current
fair value), `history` (every past value), `cash` and `inventories` per
participant, `recent_volatility`, and a `log` of past rounds. No ORM, no
tables — the state is small enough that a dict is the honest right answer.

**Per-visitor state.** `GAMES` is a `dict[session_id -> game_dict]`. Flask's
signed session cookie gives each visitor an opaque id; `get_game()` looks up
(or creates) that visitor's game by it. This is what makes the app safe for
more than one person to play at once — the first version used a single
shared game, which broke the moment a second visitor loaded the page. The
tradeoff: state lives only in server memory, so it's per-process (a restart
or a second server instance starts everyone fresh) — fine here, but it's
the reason a real deployment would swap this for Redis or a database.

**One request, traced.** Submitting a quote: the frontend `fetch`s
`/api/quote` → `get_game()` fetches your dict by cookie → each bot function
(`steady_eddie`, `nervous_nick`, `sharp_sam`) is called with the game dict
and returns its own `(bid, ask)` → `clear_round()` decides what trades
happen → the game dict is mutated (new fair value appended, round
incremented) → `public_state()` reshapes the internal dict into rounded,
JSON-friendly numbers → the frontend re-renders the leaderboard, sparkline,
and round log from that response.

**The matching algorithm (`clear_round`).** In order: (1) collect all four
quotes, (2) find the best bid and best ask across everyone and execute one
midpoint trade if they cross and belong to different participants, (3)
generate the next fair value, (4) decide if the customer is informed (knows
the sign of that move) or random, (5) the customer trades once against
whoever has the best price on the side it wants. Crossed-quotes and the
customer are kept as two separate checks on purpose — they model two
different real things (competition between market makers vs. external order
flow), and merging them into one matching engine would obscure which effect
caused which trade.

## Why this design

The three ideas this game is built to make concrete, without needing any
stochastic calculus, are the same three ideas that show up in every
market-making interview conversation:

- **Spread capture** — you earn money by buying low and selling high
  around a price you don't fully know, not by predicting direction.
- **Inventory risk** — holding a position (long or short) exposes you to
  the next random move in fair value; a bot with zero net position at
  reveal time has no exposure to that move at all.
- **Adverse selection** — some of your counterparties know more than you
  do, and they'll only trade with you when it's bad for you. Wider or
  smarter quotes are partly a defense against exactly this.

If you want to see where this leads mathematically later, the standard
reference is Avellaneda & Stoikov (2008), *"High-frequency trading in a
limit order book"* — it derives a closed-form optimal bid/ask as a
function of inventory, risk aversion, volatility, and time-to-horizon.
Sharp Sam's "widen when choppy, skew against inventory" logic is a plain-
English sketch of the same intuition that formula makes precise.
