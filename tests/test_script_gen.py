"""对话脚本生成模块测试。"""

import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from script_gen import build_prompt, validate_script, save_transcript, load_news_content


class TestBuildPrompt(unittest.TestCase):

    def test_includes_news_content(self):
        prompt = build_prompt("Apple 发布 M5 芯片。")
        self.assertIn("Apple 发布 M5 芯片", prompt)
        self.assertIn("芊悦", prompt)
        self.assertIn("萌萌", prompt)

    def test_includes_format_requirements(self):
        prompt = build_prompt("测试内容")
        self.assertIn("全部使用中文", prompt)
        self.assertIn("<芊悦>", prompt)
        self.assertIn("<萌萌>", prompt)


class TestValidateScript(unittest.TestCase):

    def test_valid_script(self):
        script = (
            "<芊悦>大家好！</芊悦>"
            "<萌萌>你好！</萌萌>"
            "<芊悦>今天新闻很多。</芊悦>"
            "<萌萌>快说快说！</萌萌>"
        )
        self.assertTrue(validate_script(script))

    def test_no_qianyue_raises(self):
        with self.assertRaises(ValueError):
            validate_script("<萌萌>只有我一个人</萌萌>" * 4)

    def test_no_mengmeng_raises(self):
        with self.assertRaises(ValueError):
            validate_script("<芊悦>只有我一个人</芊悦>" * 4)

    def test_too_few_segments_raises(self):
        with self.assertRaises(ValueError):
            validate_script("<芊悦>你好</芊悦><萌萌>嗨</萌萌>")

    def test_unclosed_tag_raises(self):
        script = "<芊悦>开头<芊悦>又开头</芊悦><萌萌>回复</萌萌>" * 2
        with self.assertRaises(ValueError):
            validate_script(script)


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
