"""Cron 入口脚本测试。"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock
from pathlib import Path

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cron_entry import resolve_news_path, load_pipeline_config


class TestResolveNewsPath(unittest.TestCase):
    """路径解析测试。"""

    def test_default_pattern(self):
        config = {
            "news_input_dir": "/data/news",
            "news_filename_pattern": "{date}.md",
        }
        path = resolve_news_path(config, "2026-04-01")
        self.assertEqual(path, "/data/news/2026-04-01.md")

    def test_custom_pattern(self):
        config = {
            "news_input_dir": "/data",
            "news_filename_pattern": "tech-daily-{date}.md",
        }
        path = resolve_news_path(config, "2026-04-01")
        self.assertEqual(path, "/data/tech-daily-2026-04-01.md")


class TestLoadPipelineConfig(unittest.TestCase):
    """配置加载测试。"""

    def test_load_config(self):
        config = load_pipeline_config()
        self.assertIn("news_input_dir", config)
        self.assertIn("site_repo", config)
        self.assertIn("llm_model", config)
        self.assertIn("cron", config)
        self.assertEqual(config["cron"]["timezone"], "Asia/Shanghai")


class TestCronExitCodes(unittest.TestCase):
    """Cron 入口 exit code 测试。"""

    def test_exit_code_1_missing_file(self):
        """早报文件不存在时 exit code 为 1。"""
        import subprocess
        result = subprocess.run(
            [
                sys.executable, "-m", "cron_entry",
                "--date", "1999-01-01",
            ],
            cwd=os.path.join(os.path.dirname(__file__), "..", "src"),
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 1)
        self.assertIn("早报文件不存在", result.stderr)

    def test_exit_code_2_pipeline_failure(self):
        """Pipeline 执行异常时 exit code 为 2。"""
        import subprocess
        import tempfile

        # 创建一个临时早报文件，让它通过文件存在检查
        # 但 pipeline 会因缺少 LLM API key 等原因失败
        with tempfile.TemporaryDirectory() as tmpdir:
            news_file = os.path.join(tmpdir, "2099-12-31.md")
            with open(news_file, "w", encoding="utf-8") as f:
                f.write("# 测试早报\n\n这是测试内容。")

            # 用 env 覆盖 news_input_dir 不行（是 yaml 配置），
            # 所以用一个 wrapper 脚本来 monkey-patch pipeline
            wrapper = os.path.join(tmpdir, "run_cron.py")
            with open(wrapper, "w") as f:
                f.write(f'''
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "{os.path.join(os.path.dirname(__file__), '..', 'src')}"))
# Monkey-patch run_pipeline to always raise
import pipeline
def fake_run_pipeline(**kwargs):
    raise RuntimeError("模拟 pipeline 失败")
pipeline.run_pipeline = fake_run_pipeline

# Monkey-patch config to use our temp dir
import cron_entry
original_load = cron_entry.load_pipeline_config
def patched_load():
    cfg = original_load()
    cfg["news_input_dir"] = "{tmpdir}"
    cfg["news_filename_pattern"] = "{{date}}.md"
    return cfg
cron_entry.load_pipeline_config = patched_load

# Run main
sys.argv = ["cron_entry", "--date", "2099-12-31"]
cron_entry.main()
''')

            result = subprocess.run(
                [sys.executable, wrapper],
                capture_output=True,
                text=True,
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("Pipeline 执行失败", result.stderr)


if __name__ == "__main__":
    unittest.main()
