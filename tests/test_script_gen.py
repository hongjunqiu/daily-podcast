"""对话脚本生成模块测试。"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from script_gen_v2 import (
    build_prompt, validate_script, save_transcript, load_news_content,
    load_show_config, _build_hosts_description,
)

# 测试用 show_config
MOCK_SHOW_CONFIG = {
    "show": {
        "name": "科技早知道",
        "slogan": "每天 5 分钟，掌握科技圈大小事",
        "duration_target": "5-8 分钟",
        "script_length": "2800-3500 字",
    },
    "hosts": [
        {"name": "芊悦", "voice": "Cherry", "role": "主讲", "personality": "阳光大方、有主见"},
        {"name": "萌萌", "voice": "Bunny", "role": "搭档", "personality": "活泼好奇、梗王"},
    ],
}


class TestBuildPrompt(unittest.TestCase):

    def test_includes_news_content(self):
        prompt = build_prompt("Apple 发布 M5 芯片。", show_config=MOCK_SHOW_CONFIG)
        self.assertIn("Apple 发布 M5 芯片", prompt)
        self.assertIn("芊悦", prompt)
        self.assertIn("萌萌", prompt)

    def test_includes_format_requirements(self):
        prompt = build_prompt("测试内容", show_config=MOCK_SHOW_CONFIG)
        self.assertIn("中文科技播客", prompt)
        self.assertIn("<芊悦>", prompt)
        self.assertIn("<萌萌>", prompt)

    def test_includes_show_config_values(self):
        prompt = build_prompt("测试", show_config=MOCK_SHOW_CONFIG)
        self.assertIn("科技早知道", prompt)
        self.assertIn("每天 5 分钟，掌握科技圈大小事", prompt)
        self.assertIn("2800-3500 字", prompt)

    def test_auto_load_config(self):
        """测试自动从 yaml 加载配置。"""
        prompt = build_prompt("测试内容")
        self.assertIn("科技早知道", prompt)
        self.assertIn("芊悦", prompt)


class TestLoadShowConfig(unittest.TestCase):

    def test_load_default(self):
        config = load_show_config()
        self.assertIn("show", config)
        self.assertIn("hosts", config)
        self.assertEqual(config["show"]["name"], "科技早知道")
        self.assertEqual(config["show"]["script_length"], "2800-3500 字")

    def test_load_custom_path(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False, encoding="utf-8") as f:
            f.write("show:\n  name: Test\nhosts: []\n")
            f.flush()
            config = load_show_config(f.name)
            self.assertEqual(config["show"]["name"], "Test")
        os.unlink(f.name)


class TestBuildHostsDescription(unittest.TestCase):

    def test_format(self):
        desc = _build_hosts_description(MOCK_SHOW_CONFIG["hosts"])
        self.assertIn("**芊悦**（主讲）", desc)
        self.assertIn("**萌萌**（搭档）", desc)


class TestValidateScript(unittest.TestCase):

    def test_valid_script(self):
        script = (
            "<芊悦>大家好！</芊悦>"
            "<萌萌>你好！</萌萌>"
        ) * 18  # 36 turns total
        self.assertTrue(validate_script(script))

    def test_no_qianyue_raises(self):
        with self.assertRaises(ValueError):
            validate_script("<萌萌>只有我一个人</萌萌>" * 40)

    def test_no_mengmeng_raises(self):
        with self.assertRaises(ValueError):
            validate_script("<芊悦>只有我一个人</芊悦>" * 40)

    def test_too_few_segments_raises(self):
        with self.assertRaises(ValueError):
            validate_script("<芊悦>你好</芊悦><萌萌>嗨</萌萌>" * 10)

    def test_unclosed_tag_raises(self):
        script = "<芊悦>开头<芊悦>又开头</芊悦><萌萌>回复</萌萌>" * 20
        with self.assertRaises(ValueError):
            validate_script(script)

    # ─── strict 模式测试 ───

    def test_strict_too_few_chars_500(self):
        """strict 模式下 < 500 字 → ValueError"""
        script = ("<芊悦>好</芊悦><萌萌>嗯</萌萌>") * 18
        self.assertLess(len(script), 500)
        with self.assertRaises(ValueError) as ctx:
            validate_script(script, strict=True)
        self.assertIn("极少", str(ctx.exception))

    def test_strict_too_few_chars_2500(self):
        """strict 模式下 500-2500 字 → ValueError"""
        # 每轮约 40 字，18 轮 = ~720 字
        segment = "<芊悦>这是一段比较长的话来凑够字数的内容啊。</芊悦><萌萌>对呀对呀确实是这样的呢嗯嗯嗯嗯嗯。</萌萌>"
        script = segment * 18  # ~36 turns, ~1200 chars
        self.assertGreater(len(script), 500)
        self.assertLess(len(script), 2500)
        with self.assertRaises(ValueError) as ctx:
            validate_script(script, strict=True)
        self.assertIn("不足", str(ctx.exception))

    def test_strict_too_many_chars(self):
        """strict 模式下 > 4000 字 → ValueError"""
        filler = "啊" * 120
        script = (f"<芊悦>{filler}</芊悦><萌萌>{filler}</萌萌>") * 18
        self.assertGreater(len(script), 4000)
        with self.assertRaises(ValueError) as ctx:
            validate_script(script, strict=True)
        self.assertIn("过多", str(ctx.exception))

    def test_strict_too_many_turns(self):
        """strict 模式下 > 42 轮 → ValueError"""
        filler = "嗯" * 60  # enough chars per turn
        script = (f"<芊悦>{filler}</芊悦><萌萌>{filler}</萌萌>") * 22  # 44 turns
        with self.assertRaises(ValueError) as ctx:
            validate_script(script, strict=True)
        self.assertIn("过多", str(ctx.exception))

    def test_strict_valid(self):
        """strict 模式下正常脚本 → True"""
        filler = "嗯" * 75  # ~75 chars per segment
        script = (f"<芊悦>{filler}</芊悦><萌萌>{filler}</萌萌>") * 19  # 38 turns, ~2850+ chars
        char_count = len(script)
        self.assertGreaterEqual(char_count, 2500)
        self.assertLessEqual(char_count, 4000)
        self.assertTrue(validate_script(script, strict=True))

    def test_non_strict_warns_but_passes(self):
        """非 strict 模式下字数超限只 warning 不 raise"""
        filler = "啊" * 120
        script = (f"<芊悦>{filler}</芊悦><萌萌>{filler}</萌萌>") * 18
        self.assertGreater(len(script), 4000)
        self.assertTrue(validate_script(script, strict=False))


class TestSaveTranscript(unittest.TestCase):

    def test_save_and_read(self):
        script = "<芊悦>测试</芊悦><萌萌>OK</萌萌>"
        with tempfile.TemporaryDirectory() as tmpdir:
            path = save_transcript(script, date="2026-04-01", output_dir=tmpdir)
            self.assertTrue(os.path.exists(path))
            self.assertIn("2026-04-01", path)
            with open(path, "r", encoding="utf-8") as f:
                self.assertEqual(f.read(), script)


class TestLoadNewsContent(unittest.TestCase):

    def test_load_existing(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False, encoding="utf-8") as f:
            f.write("# 早报\n\nApple 发布新品。")
            f.flush()
            content = load_news_content(f.name)
            self.assertIn("Apple", content)
        os.unlink(f.name)

    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            load_news_content("/nonexistent.md")

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".md", delete=False) as f:
            f.write("")
            f.flush()
            with self.assertRaises(ValueError):
                load_news_content(f.name)
        os.unlink(f.name)


if __name__ == "__main__":
    unittest.main()
