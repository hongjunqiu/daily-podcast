"""对话脚本生成模块 — 读取早报 markdown，输出双人对话脚本。

脚本格式: <芊悦>文本</芊悦> 和 <萌萌>文本</萌萌> 交替。

这个模块提供 prompt 模板和脚本解析/验证工具。
实际的对话生成由 cron agent（Claude）完成，
本模块供 pipeline 和 cron_entry 调用。
"""

import datetime
import os
import re
import logging
from pathlib import Path
from typing import Optional

logger = logging.getLogger("daily_podcast.script_gen")


# ─────────────────────────── Prompt 模板 ───────────────────────────

SCRIPT_GENERATION_PROMPT = """你是一档中文科技播客《科技早知道》的对话脚本编剧。

请基于以下今日科技早报内容，生成两位女主持人之间自然、流畅的对话脚本。

## 主持人设定
- **芊悦**（主讲）：阳光大方，负责介绍和分析新闻，语气自然专业
- **萌萌**（搭档）：活泼可爱，负责提问、评论、吐槽，偶尔惊讶

## 要求
1. 对话风格轻松诙谐，像闺蜜聊天，不要像新闻播报
2. 每条新闻用对话形式展开，不要简单罗列
3. 适当加入类比、段子、流行文化梗让内容更有趣
4. 全部使用中文，英文术语需翻译或加中文解释
5. 控制总对话长度在 3000-5000 字，对应 5-8 分钟播客
6. 开头要有自然的开场白，结尾要有告别语
7. 使用 <芊悦></芊悦> 和 <萌萌></萌萌> 标签包裹每段对话
8. 每个标签内只放一个人的一段话，不要嵌套

## 格式示例
<芊悦>大家好，欢迎收听《科技早知道》！我是芊悦。</芊悦>
<萌萌>我是萌萌！今天又有好多劲爆消息，快给大家说说！</萌萌>
<芊悦>今天第一条大新闻是...</芊悦>
...

## 今日早报内容
{news_content}

请直接输出对话脚本，不要加任何额外说明。
"""


# ─────────────────────────── 工具函数 ───────────────────────────

def build_prompt(news_content: str) -> str:
    """
    基于早报内容构建对话脚本生成 prompt。

    Args:
        news_content: 今日科技早报 markdown 内容。

    Returns:
        完整的 prompt 字符串。
    """
    return SCRIPT_GENERATION_PROMPT.format(news_content=news_content)


def validate_script(script_text: str) -> bool:
    """
    验证对话脚本格式是否正确。

    检查:
    - 包含 <芊悦> 和 <萌萌> 标签
    - 标签正确闭合
    - 至少有 4 段对话（2 个来回）

    Returns:
        True 如果格式正确。

    Raises:
        ValueError 如果格式有问题。
    """
    qianyue_count = len(re.findall(r"<芊悦>.*?</芊悦>", script_text, re.DOTALL))
    mengmeng_count = len(re.findall(r"<萌萌>.*?</萌萌>", script_text, re.DOTALL))

    if qianyue_count == 0:
        raise ValueError("脚本中没有 <芊悦> 标签")
    if mengmeng_count == 0:
        raise ValueError("脚本中没有 <萌萌> 标签")
    if qianyue_count + mengmeng_count < 4:
        raise ValueError(
            f"对话段落太少（芊悦:{qianyue_count}, 萌萌:{mengmeng_count}），"
            "至少需要 4 段"
        )

    # 检查未闭合标签
    open_qy = script_text.count("<芊悦>")
    close_qy = script_text.count("</芊悦>")
    open_mm = script_text.count("<萌萌>")
    close_mm = script_text.count("</萌萌>")

    if open_qy != close_qy:
        raise ValueError(f"芊悦标签未闭合: {open_qy} 开 / {close_qy} 闭")
    if open_mm != close_mm:
        raise ValueError(f"萌萌标签未闭合: {open_mm} 开 / {close_mm} 闭")

    return True


def save_transcript(
    script_text: str,
    date: Optional[str] = None,
    output_dir: Optional[str] = None,
) -> str:
    """
    保存对话脚本到文件。

    Args:
        script_text: 对话脚本文本。
        date: 日期字符串，默认今天。
        output_dir: 输出目录，默认 data/transcripts/。

    Returns:
        保存的文件路径。
    """
    date_str = date or datetime.date.today().isoformat()
    project_root = Path(__file__).resolve().parent.parent
    save_dir = output_dir or str(project_root / "data" / "transcripts")
    os.makedirs(save_dir, exist_ok=True)

    filepath = os.path.join(save_dir, f"transcript_{date_str}.txt")
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(script_text)

    logger.info("对话脚本保存: %s (%d 字)", filepath, len(script_text))
    return filepath


def load_news_content(news_path: str) -> str:
    """读取早报 markdown 文件。"""
    path = Path(news_path)
    if not path.exists():
        raise FileNotFoundError(f"早报文件不存在: {news_path}")
    content = path.read_text(encoding="utf-8")
    if not content.strip():
        raise ValueError(f"早报文件为空: {news_path}")
    return content
