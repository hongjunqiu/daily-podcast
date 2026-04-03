"""千问 TTS 模块测试。"""

import os
import sys
import json
import unittest
from unittest.mock import patch, MagicMock, mock_open

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from qwen_tts import synthesize_segment, get_voice_config, VOICES, DEFAULT_MODEL


class TestGetVoiceConfig(unittest.TestCase):
    """声音配置测试。"""

    def test_qianyue_config(self):
        config = get_voice_config("芊悦")
        self.assertEqual(config["voice"], "Cherry")
        self.assertIn("自然", config["instructions"])

    def test_mengmeng_config(self):
        config = get_voice_config("萌萌")
        self.assertEqual(config["voice"], "Bunny")
        self.assertIn("活泼", config["instructions"])

    def test_unknown_speaker_raises(self):
        with self.assertRaises(ValueError):
            get_voice_config("不存在的角色")

    def test_voices_are_all_female(self):
        """确认只有双女声配置。"""
        self.assertEqual(len(VOICES), 2)
        self.assertIn("芊悦", VOICES)
        self.assertIn("萌萌", VOICES)


class TestSynthesizeSegment(unittest.TestCase):
    """TTS 合成测试。"""

    @patch("qwen_tts.subprocess.run")
    @patch("qwen_tts.urllib.request.urlopen")
    @patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-key"})
    def test_success(self, mock_urlopen, mock_subprocess):
        """正常合成流程。"""
        # Mock API 响应
        api_response = json.dumps({
            "output": {"audio": {"url": "https://example.com/audio.wav"}}
        }).encode("utf-8")
        
        mock_api_resp = MagicMock()
        mock_api_resp.read.return_value = api_response
        mock_api_resp.__enter__ = MagicMock(return_value=mock_api_resp)
        mock_api_resp.__exit__ = MagicMock(return_value=False)

        mock_audio_resp = MagicMock()
        mock_audio_resp.read.return_value = b"\x00" * 1000  # fake wav
        mock_audio_resp.__enter__ = MagicMock(return_value=mock_audio_resp)
        mock_audio_resp.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [mock_api_resp, mock_audio_resp]
        mock_subprocess.return_value = MagicMock(returncode=0)

        import tempfile
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
            output_path = f.name

        try:
            result = synthesize_segment("你好", output_path, voice_name="Cherry")
            self.assertEqual(result, output_path)
            mock_subprocess.assert_called_once()
            # 验证 ffmpeg 调用参数
            call_args = mock_subprocess.call_args[0][0]
            self.assertIn("ffmpeg", call_args)
            self.assertIn("libmp3lame", call_args)
        finally:
            if os.path.exists(output_path):
                os.unlink(output_path)

    @patch.dict(os.environ, {}, clear=True)
    def test_no_api_key_raises(self):
        """没有 API key 时抛出 ValueError。"""
        import dashscope
        original = getattr(dashscope, 'api_key', None)
        try:
            with self.assertRaises(ValueError):
                synthesize_segment("测试", "/tmp/test.mp3")
        finally:
            if original:
                dashscope.api_key = original

    @patch("qwen_tts.urllib.request.urlopen")
    @patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-key"})
    def test_no_audio_url_raises(self, mock_urlopen):
        """API 返回无音频 URL 时抛出 RuntimeError。"""
        api_response = json.dumps({"output": {}}).encode("utf-8")
        mock_resp = MagicMock()
        mock_resp.read.return_value = api_response
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)
        mock_urlopen.return_value = mock_resp

        with self.assertRaises(RuntimeError):
            synthesize_segment("测试", "/tmp/test.mp3")

    @patch("qwen_tts.urllib.request.urlopen")
    @patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-key"})
    def test_instruct_model_includes_instructions(self, mock_urlopen):
        """instruct 模型时请求体包含 instructions。"""
        api_response = json.dumps({
            "output": {"audio": {"url": "https://example.com/audio.wav"}}
        }).encode("utf-8")
        
        mock_resp = MagicMock()
        mock_resp.read.return_value = api_response
        mock_resp.__enter__ = MagicMock(return_value=mock_resp)
        mock_resp.__exit__ = MagicMock(return_value=False)

        mock_audio = MagicMock()
        mock_audio.read.return_value = b"\x00" * 100
        mock_audio.__enter__ = MagicMock(return_value=mock_audio)
        mock_audio.__exit__ = MagicMock(return_value=False)

        mock_urlopen.side_effect = [mock_resp, mock_audio]

        # 拦截 Request 看请求体
        with patch("qwen_tts.subprocess.run"):
            import tempfile
            with tempfile.NamedTemporaryFile(suffix=".mp3", delete=False) as f:
                output_path = f.name
            try:
                synthesize_segment(
                    "测试", output_path,
                    voice_name="Cherry",
                    instructions="语速快一点",
                    model="qwen3-tts-instruct-flash",
                )
                # 检查第一次 urlopen 的请求体
                call_args = mock_urlopen.call_args_list[0]
                request_obj = call_args[0][0]
                body = json.loads(request_obj.data.decode("utf-8"))
                self.assertEqual(body["input"]["instructions"], "语速快一点")
            finally:
                if os.path.exists(output_path):
                    os.unlink(output_path)


class TestDefaultModel(unittest.TestCase):
    """模型配置测试。"""

    def test_default_model(self):
        self.assertEqual(DEFAULT_MODEL, "qwen3-tts-instruct-flash")


if __name__ == "__main__":
    unittest.main()
