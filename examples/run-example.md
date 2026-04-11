# Example commands

Dry-run (safe validation):

```bash
.venv/bin/python /Users/evgenianosko/.openclaw/workspace/skills/btc-5m-live/scripts/test_btc_5m_session_exit_sl.py --profile conservative
```

Real execution (conservative):

```bash
.venv/bin/python /Users/evgenianosko/.openclaw/workspace/skills/btc-5m-live/scripts/test_btc_5m_session_exit_sl.py --profile conservative --execute
```

Real execution (aggressive):

```bash
.venv/bin/python /Users/evgenianosko/.openclaw/workspace/skills/btc-5m-live/scripts/test_btc_5m_session_exit_sl.py --profile aggressive --execute
```