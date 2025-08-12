from __future__ import annotations

import argparse
import asyncio
import os
from pathlib import Path

from dotenv import load_dotenv

from nc_vip_dmv.config import load_config
from nc_vip_dmv.core.scheduler import Scheduler


async def async_main() -> None:
    parser = argparse.ArgumentParser(description="NC VIP-DMV checker")
    parser.add_argument("--config", type=str, default="config.yaml", help="Path to config.yaml")
    parser.add_argument("--checker", type=str, choices=["playwright", "browseruse"], default=None, help="Override checker type")
    parser.add_argument("--once", action="store_true", help="Run a single check iteration and exit")
    parser.add_argument("--no-notify", action="store_true", help="Disable notifications (console only)")
    args = parser.parse_args()

    # Load env
    load_dotenv()

    config_path = Path(args.config)
    if not config_path.exists():
        raise SystemExit(f"Config file not found: {config_path}")

    config = load_config(config_path)

    # Optional env overrides for notifier enabled flags
    sms_enabled_env = os.getenv("NCVIP_SMS_ENABLED")
    if sms_enabled_env is not None:
        config.notifiers.sms.enabled = sms_enabled_env.lower() in {"1", "true", "yes"}
    discord_enabled_env = os.getenv("NCVIP_DISCORD_ENABLED")
    if discord_enabled_env is not None:
        config.notifiers.discord.enabled = discord_enabled_env.lower() in {"1", "true", "yes"}

    scheduler = Scheduler(config, notifications_enabled=not args.no_notify)
    await scheduler.run(checker_override=args.checker, run_once=args.once)


def main() -> None:
    try:
        asyncio.run(async_main())
    except KeyboardInterrupt:
        print("Interrupted")


if __name__ == "__main__":
    main()
