# Google Alerts Setup

Google Alerts is a free service that emails you when new articles matching your keywords appear online. Set this up in minutes — no coding required.

## Step 1 — Go to Google Alerts

Visit: https://google.com/alerts

## Step 2 — Create These Alerts

Create one alert per keyword below. For each:
1. Paste the keyword into the search box
2. Click "Show options"
3. Set **How often** → As-it-happens (for urgent ones) or Once a day
4. Set **Sources** → News
5. Set **Language** → English
6. Click **Create Alert**

### High Priority (As-it-happens)
These can move markets within hours:

| Keyword | Why It Matters |
|---|---|
| `"Strait of Hormuz"` | Oil supply disruption — Shell, oil prices |
| `"OPEC production cut"` | Direct oil price impact |
| `"Iran Israel conflict"` | Middle East escalation — gold, oil, defense |
| `"Federal Reserve rate"` | Moves all markets |
| `"oil price spike"` | Direct Shell/energy impact |
| `"Bitcoin ETF"` | Crypto institutional flows |

### Medium Priority (Once a day)
Important but slower moving:

| Keyword | Why It Matters |
|---|---|
| `"BYD sales record"` | Your EV position |
| `"Rheinmetall contract"` | Defense spending |
| `"Barrick Gold earnings"` | Your gold mining position |
| `"NATO defense spending"` | Rheinmetall, defense sector |
| `"gold price record"` | Barrick Gold, safe haven demand |
| `"Ukraine ceasefire"` | Could reverse defense/oil trades |
| `"Shell dividend"` | Direct holding news |
| `"recession warning"` | Portfolio-wide risk |

## Step 3 — When an Alert Arrives

Paste the headline into Claude with this prompt:

```
This news just broke: [PASTE HEADLINE HERE]

My portfolio:
- Shell (SHEL) - Oil stock
- Barrick Gold (GOLD) - Gold mining
- Rheinmetall (RHM) - Defense
- Bitcoin (BTC) - Crypto
- BYD (BYDDY) - EV stock

Tell me:
1. Impact on my specific holdings
2. Should I buy / sell / hold anything right now?
3. Urgency level: HIGH / MEDIUM / LOW

Be direct and brief.
```

## Step 4 — Upgrade to Automated Alerts

Once you're comfortable with the above, use the bot in this repository to automate the entire process — it monitors news 24/7 and sends alerts directly to your Telegram.

See the main [README](../README.md) for setup instructions.
