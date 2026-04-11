---
name: btc-5m-live
description: Run and monitor BTC 5-minute Up/Down trading on Polymarket using momentum-near-close logic (time-left, BTC move, market skew), fixed/controlled sizing, optional micro-hedge, and one-shot or loop execution.
---

# BTC 5m Live

## Paths
- Main trading repo: `/Users/evgenianosko/.openclaw/workspace/pm-hl-conservative-plus-repo`
- Core runner: `src/live/pm_live_trade_runner.py`
- Skill wrapper: `scripts/run_btc_5m_threshold_test.py`

## Strategy Alignment
Use this skill when the operator wants to execute a BTC 5m momentum strategy:
- Entry focus near event close (around 2 minutes left).
- Confirm meaningful BTC move in the interval (about $70-$100).
- Prefer direction supported by market skew.
- Enter with momentum, not against it.
- Optional small opposite hedge when skew becomes extreme.

## Operational Rules
- Default is dry-run unless `--execute` is set.
- Use controlled stake sizing (`--stake-usd`, profile caps).
- If both UP and DOWN satisfy threshold logic, choose the stronger side.
- Keep stop-loss and timing guards enabled in profile config.

## One-shot real test
From trading repo root:

```bash
.venv/bin/python /Users/evgenianosko/.openclaw/workspace/skills/btc-5m-live/scripts/test_btc_5m_session_exit_sl.py --profile conservative --execute
```

Aggressive profile:

```bash
.venv/bin/python /Users/evgenianosko/.openclaw/workspace/skills/btc-5m-live/scripts/test_btc_5m_session_exit_sl.py --profile aggressive --execute
```

Override profile params manually (example):

```bash
.venv/bin/python /Users/evgenianosko/.openclaw/workspace/skills/btc-5m-live/scripts/test_btc_5m_session_exit_sl.py --profile conservative --stake-usd 5 --entry-timeout-min 90 --execute
```

## Strategy Profiles
- File: `config/btc_5m_profiles.yaml`
- Presets: `conservative`, `aggressive`
- Includes entry/exit timing, quote staleness checks, spread/liquidity guards, hedge triggers, and risk caps.

## Hot Commands (chat-friendly)
Examples:
- `btc5m conservative start`
- `btc5m aggressive start`

Handler:
- `scripts/btc5m_hot.sh [conservative|aggressive]`

Output:
- writes run log: `runtime/btc5m_<profile>_<UTCSTAMP>.log`

## Notes
- Wrapper resolves current BTC 5m market slug (`btc-updown-5m-<bucket>`).
- Real order placement is delegated to `pm_live_trade_runner.py` with `--force-side` and `--max-notional-usd`.
- Keep all GitHub-facing docs and metadata in English.