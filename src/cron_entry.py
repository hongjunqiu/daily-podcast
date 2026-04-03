#!/usr/bin/env python3
"""每日科技播客 Cron 入口脚本。

被 cron 调度调用，读取当日早报，运行完整 pipeline，
生成播客并发布到 Astro blog。

用法（手动测试）：
    cd /Users/hongjun/.openclaw/workspace-cody/daily-podcast
    source ../.venv/bin/activate
    python src/cron_entry.py                   # 使用今天日期
    python src/cron_entry.py --date 2026-04-01 # 指定日期
    python src/cron_entry.py --dry-run         # 不执行 git push
"""

import argparse
import datetime
import logging
import os
import sys
import yaml
from pathlib import Path

# 把 src 目录加入 path
sys.path.insert(0, os.path.dirname(__file__))

from pipeline import run_pipeline

logger = logging.getLogger("daily_podcast.cron")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
PIPELINE_CONFIG = PROJECT_ROOT / "config" / "pipeline_config.yaml"

# Discord 通知频道（失败时发送到 #system-ops）
NOTIFY_CHANNEL_ID = None  # 待配置，如 "1234567890"


def notify_failure(error_msg: str) -> None:
    """Pipeline 失败时输出告警信息（供外部 cron 调度捕获或扩展为 Discord 通知）。"""
    alert = f"🚨 **每日播客 Pipeline 失败** — {error_msg}"
    logger.error(alert)
    # TODO: 接入 Discord webhook 或 OpenClaw message tool 发送到 #system-ops
    # 当前先写到 stderr，cron 调度层可以捕获
    print(alert, file=sys.stderr)


def load_pipeline_config() -> dict:
    with open(PIPELINE_CONFIG, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def resolve_news_path(config: dict, date_str: str) -> str:
    """根据日期解析早报文件路径。"""
    input_dir = config["news_input_dir"]
    pattern = config.get("news_filename_pattern", "{date}.md")
    filename = pattern.format(date=date_str)
    return os.path.join(input_dir, filename)


def main():
    parser = argparse.ArgumentParser(description="每日科技播客 Cron 入口")
    parser.add_argument("--date", help="指定日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--dry-run", action="store_true", help="不执行 git push")
    parser.add_argument("--transcript-only", action="store_true", help="仅生成脚本")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # 加载配置
    config = load_pipeline_config()
    date_str = args.date or datetime.date.today().isoformat()

    # 解析早报路径
    news_path = resolve_news_path(config, date_str)
    logger.info("Cron 启动: date=%s, news=%s", date_str, news_path)

    if not os.path.exists(news_path):
        logger.error("早报文件不存在: %s — 跳过今日播客生成", news_path)
        notify_failure(f"早报文件不存在: {news_path}")
        sys.exit(1)

    # 运行 pipeline
    try:
        results = run_pipeline(
            input_path=news_path,
            site_repo=config.get("site_repo"),
            llm_model=config.get("llm_model", "claude-sonnet-4-20250514"),
            api_key_label=config.get("api_key_label", "ANTHROPIC_API_KEY"),
            dry_run=args.dry_run,
            transcript_only=args.transcript_only,
        )

        logger.info("Pipeline 完成:")
        for k, v in results.items():
            if k != "transcript":
                logger.info("  %s: %s", k, v)

    except Exception as e:
        logger.error("Pipeline 执行失败: %s", e, exc_info=True)
        notify_failure(f"Pipeline 执行失败: {e}")
        sys.exit(2)


if __name__ == "__main__":
    main()
