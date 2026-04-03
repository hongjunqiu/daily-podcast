"""CosyVoice TTS provider for Podcastfy — 通过 DashScope API 调用千问 CosyVoice-v2。"""

import os
import logging
from typing import List, Optional

import dashscope
from dashscope.audio.tts_v2 import SpeechSynthesizer, AudioFormat

from podcastfy.tts.base import TTSProvider

logger = logging.getLogger(__name__)

# 默认音色
DEFAULT_MALE_VOICE = "longanyang_v2"      # 龙安洋 — 自然阳光
DEFAULT_FEMALE_VOICE = "qianxue"          # 芊悦 — 温柔自然
DEFAULT_MODEL = "cosyvoice-v2"


class CosyVoiceTTS(TTSProvider):
    """DashScope CosyVoice TTS provider implementation."""

    # CosyVoice 支持的 SSML 标签
    PROVIDER_SSML_TAGS: List[str] = ["break", "phoneme", "sub"]

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: str = DEFAULT_MODEL,
    ):
        """
        初始化 CosyVoice TTS provider。

        Args:
            api_key: DashScope API key。如果不传，从环境变量 DASHSCOPE_API_KEY 读取。
            model: CosyVoice 模型名称，默认 cosyvoice-v2。
        """
        resolved_key = api_key or os.environ.get("DASHSCOPE_API_KEY")
        if not resolved_key:
            raise ValueError(
                "DashScope API key 未提供。"
                "请设置环境变量 DASHSCOPE_API_KEY 或传入 api_key 参数。"
            )
        dashscope.api_key = resolved_key
        self.model = model

    def get_supported_tags(self) -> List[str]:
        """返回支持的 SSML 标签。"""
        return self.PROVIDER_SSML_TAGS

    def generate_audio(
        self,
        text: str,
        voice: str,
        model: str = None,
        voice2: str = None,
    ) -> bytes:
        """
        调用 DashScope CosyVoice API 合成语音。

        Args:
            text: 要合成的文本。
            voice: 音色名称（如 longxiaocheng_v2）。
            model: 模型名称，可选，覆盖实例级设置。
            voice2: 未使用，保持接口兼容。

        Returns:
            MP3 音频的 bytes。

        Raises:
            ValueError: 参数无效。
            RuntimeError: 语音合成失败。
        """
        use_model = model or self.model
        use_voice = voice

        self.validate_parameters(text, use_voice, use_model)

        logger.info(
            "CosyVoice TTS: model=%s, voice=%s, text_len=%d",
            use_model, use_voice, len(text),
        )

        try:
            synthesizer = SpeechSynthesizer(
                model=use_model,
                voice=use_voice,
                format=AudioFormat.MP3_22050HZ_MONO_256KBPS,
            )
            audio_data = synthesizer.call(text)

            if not audio_data:
                raise RuntimeError(
                    f"CosyVoice 返回空音频。voice={use_voice}, model={use_model}"
                )

            logger.info(
                "CosyVoice TTS 完成: %d bytes, voice=%s",
                len(audio_data), use_voice,
            )
            return audio_data

        except Exception as e:
            raise RuntimeError(
                f"CosyVoice TTS 合成失败: {e}"
            ) from e


def register():
    """在 Podcastfy 的 TTSProviderFactory 中注册 CosyVoice provider。"""
    from podcastfy.tts.factory import TTSProviderFactory
    TTSProviderFactory.register_provider("cosyvoice", CosyVoiceTTS)
