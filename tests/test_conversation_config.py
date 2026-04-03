"""验证 conversation_config.yaml 能被 Podcastfy 正确加载。"""

import os
import sys
import yaml

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from podcastfy.utils.config_conversation import load_conversation_config


def test_config_loads():
    """配置文件能被正确加载。"""
    config_path = os.path.join(
        os.path.dirname(__file__), "..", "config", "conversation_config.yaml"
    )
    with open(config_path, "r") as f:
        config_dict = yaml.safe_load(f)

    config = load_conversation_config(config_dict)

    # 验证基本字段
    assert config.get("podcast_name") == "科技早知道"
    assert config.get("output_language") == "Chinese"
    assert config.get("creativity") == 0.8

    # 验证 TTS 配置
    tts = config.get("text_to_speech")
    assert tts.get("default_tts_model") == "cosyvoice"
    assert tts.get("ending_message") == "感谢收听，我们明天见！"

    cosyvoice_cfg = tts.get("cosyvoice")
    assert cosyvoice_cfg.get("model") == "cosyvoice-v2"
    voices = cosyvoice_cfg.get("default_voices")
    assert voices.get("question") == "longanyang_v2"
    assert voices.get("answer") == "qianxue"

    # 验证对话风格
    styles = config.get("conversation_style")
    assert "engaging" in styles
    assert "humorous" in styles

    # 验证 user_instructions 包含关键内容
    instructions = config.get("user_instructions")
    assert "安洋" in instructions
    assert "芊悦" in instructions
    assert "Person1" in instructions

    print("✅ conversation_config.yaml 验证通过！")


def test_cosyvoice_provider_registration():
    """CosyVoice provider 注册后 TextToSpeech 能识别。"""
    from cosyvoice import register
    register()

    from podcastfy.tts.factory import TTSProviderFactory
    assert "cosyvoice" in TTSProviderFactory._providers
    print("✅ CosyVoice provider 注册到 Factory 成功！")


if __name__ == "__main__":
    test_config_loads()
    test_cosyvoice_provider_registration()
