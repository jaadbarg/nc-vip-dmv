# NC VIP-DMV

Automates checking for appointment availability at NC DMV offices and sends instant notifications to a Discord channel. MVP supports every-few-seconds checks and Discord notifications. Optional Browser-Use agent for complex workflows.

- Project repo referenced: [browser-use](https://github.com/browser-use/browser-use)
- Target site: NC DMV Skip-The-Line scheduling portal

## Features
- Async scheduler checks multiple offices in parallel
- Playwright-based checker for speed
- Optional Browser-Use agent for robust navigation flows
- Discord notifications with deduping

## Requirements
- Python 3.11+
- macOS (tested), should work on Linux too

## Quickstart
1. Create virtualenv and install deps:
   ```bash
   cd /Users/jaado/Desktop/projects/nc-vip-dmv
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   playwright install chromium
   ```

2. Configure env and YAML:
   - Copy `.env.example` to `.env` and set `DISCORD_WEBHOOK_URL` and (if using Browser-Use) `OPENAI_API_KEY`.
   - Copy `config.example.yaml` to `config.yaml` and edit office URLs/names.

3. Run:
   ```bash
   source .venv/bin/activate
   python -m nc_vip_dmv.main --config config.yaml --checker playwright
   ```

To use Browser-Use checker instead:
```bash
python -m nc_vip_dmv.main --config config.yaml --checker browseruse
```

## Notes
- Respect site Terms; keep check interval reasonable
- Default interval is 5s; you can reduce to 1s at your own risk
- Browser-Use library: see docs and examples in the repo: [browser-use/browser-use](https://github.com/browser-use/browser-use)

## Roadmap
- Auto-book (V2)
- Web UI for subscriptions
- Multi-channel notifications (SMS, email)
