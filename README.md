# Market Maker Arena

A browser game where you compete against 3 bots as a market maker. Each round everyone quotes a bid/ask, trades happen when quotes cross or when a simulated "customer" trades against the best price on the board, and P&L gets marked to the true value at the end of each round.

Built to practice market making concepts (spread capture, inventory risk, adverse selection) without needing the full stochastic calculus behind models like Avellaneda-Stoikov.

## Run it locally

```
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

Then open http://127.0.0.1:5050 in a browser.

## How to play

1. Each round, you and 3 bots post a bid (buy price) and ask (sell price), without seeing each other's quotes.
2. If your bid crosses someone else's ask (or vice versa), you trade with them at the midpoint.
3. A customer also trades once per round, always at the best price on the board. Some percentage of the time the customer already knows which way the price is about to move and only trades when it's bad for you (adverse selection).
4. At the end of the round the true price is revealed and everyone's cash + inventory gets marked to it.
5. 20 rounds, highest P&L wins.

## Bots

- Steady Eddie: fixed $3 half-spread, ignores inventory and volatility.
- Nervous Nick: same fixed spread, but shifts both quotes to lean against his own inventory.
- Sharp Sam: widens spread when the market's been choppy, leans against inventory harder than Nick. Hardest to beat.

## Architecture

No database, everything in memory.

- `app.py` holds a `GAMES` dict keyed by a session id (from Flask's session cookie), so each visitor gets their own game and they don't interfere with each other. One shared global game was the first version, but that breaks with more than one player.
- A "game" is just one dict: round number, current fair value, price history, cash/inventory per player, recent volatility, log of past rounds.
- Bot functions (`steady_eddie`, `nervous_nick`, `sharp_sam`) take the game dict and return their `(bid, ask)`.
- `clear_round()` does the matching: find best bid/ask across everyone, execute a midpoint trade if they cross, generate the next fair value, decide if the customer is informed, execute the customer's trade against whoever's showing the best price.
- `public_state()` reshapes the internal dict into rounded numbers for the frontend to render.
- Frontend is one HTML file with vanilla JS, hits `/api/state`, `/api/quote`, `/api/new_game`. No frontend framework.

Known limitation: state is only in server memory, so a restart or scaling to multiple server processes wipes/splits it. Fine for this, would need Redis or a real DB otherwise.

## Deploying your own copy (Render, free)

1. Fork or clone this repo to your own GitHub account.
2. On [render.com](https://render.com): New > Web Service, connect the repo.
3. Build command: `pip install -r requirements.txt`
4. Start command: `gunicorn app:app`
5. Deploy. Render gives you a public URL.

Free tier sleeps after 15 min idle, takes ~30-50s to wake up on the next visit.
