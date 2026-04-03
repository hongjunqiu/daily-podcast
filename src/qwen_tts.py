"""千问 TTS 模块 — 通过 DashScope HTTP API 调用 qwen3-tts-instruct-flash。

支持 Cherry（芊悦）和 Bunny（萌小姬）双女声，
带 instructions 控制语气和语速。
"""

import json
import logging
import os
import subprocess
import tempfile
import urllib.request
from typing import Optional

logger = logging.getLogger("daily_podcast.tts")

# DashScope API
API_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation"
DEFAULT_MODEL = "qwen3-tts-instruct-flash"

# 声音配置
VOICES = {
    "芊悦": {
        "voice": "Cherry",
        "instructions": "自然大方，语速稍快，像朋友聊天，阳光自然",
    },
    "萌萌": {
        "voice": "Bunny",
        "instructions": "活泼可爱，语速稍快，充满好奇心，偶尔惊讶",
    },
}


def synthesize_segment(
    text: str,
    output_path: str,
    voice_name: str = "Cherry",
    instructions: str = "",
    model: str = DEFAULT_MODEL,
    api_key: Optional[str] = None,
) -> str:
    """
    调用 DashScope TTS API 合成单段语音。

    Args:
        text: 要合成的文本。
        output_path: 输出 MP3 文件路径。
        voice_name: DashScope voice 名称（如 Cherry, Bunny）。
        instructions: instruct 指令（控制语气语速）。
        model: TTS 模型名称。
        api_key: DashScope API key，不传则从环境变量读取。

    Returns:
        输出文件路径。
    """
    resolved_key = api_key or os.environ.get("DASHSCOPE_API_KEY")
    if not resolved_key:
        raise ValueError("DASHSCOPE_API_KEY 未设置")

    input_data = {
        "text": text,
        "voice": voice_name,
        "language_type": "Chinese",
    }

    if instructions and "instruct" in model:
        input_data["instructions"] = instructions

    request_body = {
        "model": model,
        "input": input_data,
    }

    headers = {
        "Authorization": f"Bearer {resolved_key}",
        "Content-Type": "application/json",
    }

    req = urllib.request.Request(
        API_URL,
        data=json.dumps(request_body).encode("utf-8"),
        headers=headers,
        method="POST",
    )

    logger.info("TTS 合成: voice=%s, text_len=%d", voice_name, len(text))

    with urllib.request.urlopen(req, timeout=120) as resp:
        result = json.loads(resp.read().decode("utf-8"))

    audio_url = result.get("output", {}).get("audio", {}).get("url")
    if not audio_url:
        raise RuntimeError(f"DashScope TTS 未返回音频 URL: {result}")

    # 下载音频
    with urllib.request.urlopen(audio_url, timeout=120) as audio_resp:
        audio_data = audio_resp.read()

    # 保存为 wav 再转 mp3
    wav_path = output_path.rsplit(".", 1)[0] + ".wav"
    with open(wav_path, "wb") as f:
        f.write(audio_data)

    subprocess.run(
        ["ffmpeg", "-y", "-i", wav_path, "-acodec", "libmp3lame", "-q:a", "2", output_path],
        capture_output=True,
        check=True,
    )
    os.remove(wav_path)

    logger.info("TTS 完成: %s (%d bytes)", output_path, os.path.getsize(output_path))
    return output_path


def get_voice_config(speaker: str) -> dict:
    """
    根据说话人名称获取 voice 配置。

    Args:
        speaker: '芊悦' 或 '萌萌'

    Returns:
        dict with 'voice' and 'instructions' keys.
    """
    config = VOICES.get(speaker)
    if not config:
        raise ValueError(f"未知说话人: {speaker}，可选: {list(VOICES.keys())}")
    return config
