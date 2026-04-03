"""Pipeline v2 测试。"""

import os
import sys
import tempfile
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from pipeline import parse_transcript, load_transcript, generate_blog_post, run_pipeline


class TestParseTranscript(unittest.TestCase):
    """对话脚本解析测试。"""

    def test_basic_parse(self):
        text = "<芊悦>大家好，欢迎收听。</芊悦><萌萌>今天有什么新闻？</萌萌>"
        segments = parse_transcript(text)
        self.assertEqual(len(segments), 2)
        self.assertEqual(segments[0], ("芊悦", "大家好，欢迎收听。"))
        self.assertEqual(segments[1], ("萌萌", "今天有什么新闻？"))

    def test_multiline(self):
        text = "<芊悦>\n  多行\n  文本\n</芊悦><萌萌>OK</萌萌>"
        segments = parse_transcript(text)
        self.assertEqual(segments[0][0], "芊悦")
        self.assertIn("多行", segments[0][1])

    def test_empty_tags_raises(self):
        with self.assertRaises(ValueError):
            parse_transcript("没有标签的文本")

    def test_empty_content_raises(self):
        with self.assertRaises(ValueError):
            parse_transcript("<芊悦>   </芊悦>")


class TestLoadTranscript(unittest.TestCase):
    """文件加载测试。"""

    def test_load_existing(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("<芊悦>测试</芊悦><萌萌>OK</萌萌>")
            f.flush()
            content = load_transcript(f.name)
            self.assertIn("芊悦", content)
        os.unlink(f.name)

    def test_file_not_found(self):
        with self.assertRaises(FileNotFoundError):
            load_transcript("/nonexistent.txt")

    def test_empty_file(self):
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write("")
            f.flush()
            with self.assertRaises(ValueError):
                load_transcript(f.name)
        os.unlink(f.name)


class TestGenerateBlogPost(unittest.TestCase):
    """Blog post 生成测试。"""

    def test_blog_post_format(self):
        transcript = "<芊悦>大家好！</芊悦><萌萌>今天聊什么？</萌萌>"
        with tempfile.TemporaryDirectory() as site_repo:
            post_path = generate_blog_post(
                transcript_text=transcript,
                audio_filename="2026-04-01.mp3",
                date="2026-04-01",
                site_repo=site_repo,
            )
            self.assertTrue(os.path.exists(post_path))
            content = open(post_path, "r", encoding="utf-8").read()
            self.assertIn("publishDate: 2026-04-01", content)
            self.assertIn("**芊悦**", content)
            self.assertIn("**萌萌**", content)
            self.assertIn("/audio/podcast/2026-04-01.mp3", content)
            self.assertNotIn("<芊悦>", content)

    def test_single_quote_escape(self):
        transcript = "<芊悦>Apple's new chip</芊悦><萌萌>That's cool</萌萌>"
        with tempfile.TemporaryDirectory() as site_repo:
            post_path = generate_blog_post(
                transcript_text=transcript,
                audio_filename="test.mp3",
                date="2026-04-01",
                site_repo=site_repo,
            )
            content = open(post_path, "r", encoding="utf-8").read()
            self.assertIn("''", content)


class TestRunPipeline(unittest.TestCase):
    """Pipeline 集成测试。"""

    @patch("pipeline.synthesize_all_segments")
    @patch("pipeline.merge_audio_files")
    @patch("pipeline.copy_audio_to_site")
    @patch("pipeline.git_publish")
    def test_full_dry_run(self, mock_git, mock_copy, mock_merge, mock_tts):
        mock_tts.return_value = ["/tmp/001.mp3"]
        mock_merge.return_value = "/tmp/final.mp3"
        mock_copy.return_value = "/tmp/dest.mp3"

        with tempfile.TemporaryDirectory() as tmpdir:
            # 创建 transcript
            transcript_file = os.path.join(tmpdir, "transcript.txt")
            with open(transcript_file, "w", encoding="utf-8") as f:
                f.write("<芊悦>今天新闻很精彩。</芊悦><萌萌>说来听听！</萌萌>")

            site_repo = os.path.join(tmpdir, "site")
            results = run_pipeline(
                transcript_path=transcript_file,
                site_repo=site_repo,
                dry_run=True,
            )

            self.assertIn("date", results)
            self.assertEqual(results["segment_count"], 2)
            self.assertFalse(results.get("published", True))

    @patch("pipeline.synthesize_all_segments")
    @patch("pipeline.merge_audio_files")
    def test_no_site_repo(self, mock_merge, mock_tts):
        mock_tts.return_value = ["/tmp/001.mp3"]
        mock_merge.return_value = "/tmp/final.mp3"

        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
            f.write("<芊悦>测试</芊悦><萌萌>OK</萌萌>")
            f.flush()
            results = run_pipeline(transcript_path=f.name, site_repo=None)
            self.assertNotIn("post_path", results)
        os.unlink(f.name)


class TestGitPublish(unittest.TestCase):
    """Git 发布测试。"""

    @patch("subprocess.run")
    def test_nothing_to_commit(self, mock_run):
        from pipeline import git_publish
        mock_run.side_effect = [
            MagicMock(returncode=0),  # git add
            MagicMock(returncode=0),  # git diff --cached --quiet (无变更)
        ]
        git_publish("/fake/repo", "2026-04-01")
        self.assertEqual(mock_run.call_count, 2)


if __name__ == "__main__":
    unittest.main()
