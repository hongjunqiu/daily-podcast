"""CosyVoice TTS adapter 单元测试。

运行方式：
    cd /Users/hongjun/.openclaw/workspace-cody
    source .venv/bin/activate
    python -m pytest daily-podcast/tests/test_cosyvoice.py -v
"""

import os
import unittest
from unittest.mock import patch, MagicMock

# 确保 src 可导入
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from cosyvoice import CosyVoiceTTS, register, DEFAULT_MODEL, DEFAULT_MALE_VOICE, DEFAULT_FEMALE_VOICE


class TestCosyVoiceTTSInit(unittest.TestCase):
    """初始化相关测试。"""

    @patch.dict(os.environ, {"DASHSCOPE_API_KEY": "test-key-123"})
    def test_init_from_env(self):
        """从环境变量读取 API key 初始化。"""
        provider = CosyVoiceTTS()
        self.assertEqual(provider.model, DEFAULT_MODEL)

    def test_init_with_explicit_key(self):
        """显式传入 API key 初始化。"""
        provider = CosyVoiceTTS(api_key="explicit-key")
        self.assertEqual(provider.model, DEFAULT_MODEL)

    @patch.dict(os.environ, {}, clear=True)
    def test_init_no_key_raises(self):
        """没有 API key 时抛出 ValueError。"""
        # 清除可能残留的 dashscope.api_key
        import dashscope
        original = dashscope.api_key
        dashscope.api_key = None
        try:
            with self.assertRaises(ValueError):
                CosyVoiceTTS()
        finally:
            dashscope.api_key = original

    def test_init_custom_model(self):
        """自定义模型名称。"""
        provider = CosyVoiceTTS(api_key="key", model="cosyvoice-v3")
        self.assertEqual(provider.model, "cosyvoice-v3")


class TestCosyVoiceTTSGenerateAudio(unittest.TestCase):
    """generate_audio 方法测试。"""

    def setUp(self):
        self.provider = CosyVoiceTTS(api_key="test-key")

    @patch("cosyvoice.SpeechSynthesizer")
    def test_generate_audio_success(self, MockSynthesizer):
        """正常合成返回 bytes。"""
        fake_audio = b"\xff\xfb\x90\x00" + b"\x00" * 1000  # fake MP3 bytes
        mock_instance = MagicMock()
        mock_instance.call.return_value = fake_audio
        MockSynthesizer.return_value = mock_instance

        result = self.provider.generate_audio(
            text="你好，这是测试",
            voice=DEFAULT_MALE_VOICE,
            model=DEFAULT_MODEL,
        )

        self.assertEqual(result, fake_audio)
        MockSynthesizer.assert_called_once()
        mock_instance.call.assert_called_once_with("你好，这是测试")

    @patch("cosyvoice.SpeechSynthesizer")
    def test_generate_audio_empty_raises(self, MockSynthesizer):
        """API 返回空数据时抛出 RuntimeError。"""
        mock_instance = MagicMock()
        mock_instance.call.return_value = None
        MockSynthesizer.return_value = mock_instance

        with self.assertRaises(RuntimeError):
            self.provider.generate_audio(
                text="测试",
                voice=DEFAULT_FEMALE_VOICE,
                model=DEFAULT_MODEL,
            )

    @patch("cosyvoice.SpeechSynthesizer")
    def test_generate_audio_api_error(self, MockSynthesizer):
        """API 异常时包装为 RuntimeError。"""
        MockSynthesizer.side_effect = Exception("网络超时")

        with self.assertRaises(RuntimeError) as ctx:
            self.provider.generate_audio(
                text="测试",
                voice=DEFAULT_MALE_VOICE,
                model=DEFAULT_MODEL,
            )
        self.assertIn("网络超时", str(ctx.exception))

    def test_generate_audio_empty_text_raises(self):
        """空文本时 validate_parameters 抛出 ValueError。"""
        with self.assertRaises(ValueError):
            self.provider.generate_audio(text="", voice=DEFAULT_MALE_VOICE, model=DEFAULT_MODEL)

    def test_generate_audio_empty_voice_raises(self):
        """空 voice 时抛出 ValueError。"""
        with self.assertRaises(ValueError):
            self.provider.generate_audio(text="hello", voice="", model=DEFAULT_MODEL)

    @patch("cosyvoice.SpeechSynthesizer")
    def test_generate_audio_uses_instance_model(self, MockSynthesizer):
        """不传 model 时使用实例的 self.model。"""
        mock_instance = MagicMock()
        mock_instance.call.return_value = b"\x00" * 100
        MockSynthesizer.return_value = mock_instance

        self.provider.generate_audio(
            text="测试",
            voice=DEFAULT_MALE_VOICE,
            model=None,
        )

        # 检查 SpeechSynthesizer 被使用了实例的 model
        call_kwargs = MockSynthesizer.call_args
        self.assertEqual(call_kwargs.kwargs.get("model") or call_kwargs[1].get("model"), DEFAULT_MODEL)


class TestCosyVoiceTTSSupportedTags(unittest.TestCase):
    """SSML tag 支持测试。"""

    def test_supported_tags(self):
        """返回预期的 SSML 标签列表。"""
        provider = CosyVoiceTTS(api_key="key")
        tags = provider.get_supported_tags()
        self.assertIn("break", tags)
        self.assertIn("phoneme", tags)
        self.assertIn("sub", tags)


class TestRegister(unittest.TestCase):
    """注册到 TTSProviderFactory 测试。"""

    def test_register(self):
        """register() 后 factory 能创建 cosyvoice provider。"""
        register()
        from podcastfy.tts.factory import TTSProviderFactory
        self.assertIn("cosyvoice", TTSProviderFactory._providers)
        self.assertEqual(TTSProviderFactory._providers["cosyvoice"], CosyVoiceTTS)


if __name__ == "__main__":
    unittest.main()
