"""对话脚本生成模块 v2 — Phase 2 增强版。

改进点：
- 更详细的 no-go list
- 节奏变化指引
- 强化自然对话要求
- 对话轮次 35+
- 冲突/不同意见要求
- Phase 3: strict 验证模式 + 从 show_identity.yaml 加载配置
"""

import datetime
import os
import re
import logging
from pathlib import Path
from typing import Optional

import yaml

logger = logging.getLogger("daily_podcast.script_gen")


# ─────────────────────────── Prompt 模板 v2 ───────────────────────────

SCRIPT_GENERATION_PROMPT = """你是一档中文科技播客《{show_name}》的对话脚本编剧。
请基于以下今日科技早报内容，生成两位女主持人之间自然、有深度、有火花的对话脚本。

## 节目信息
- 节目名：{show_name}
- Slogan：{slogan}
- 时长目标：{duration_target}（对应 {script_length}脚本）

## 主持人设定
{hosts_description}

## 互动风格（核心！参考 NotebookLM 的自然互动感）
- 芊悦抛出观点 → 萌萌挑战、补充或换个角度看
- 萌萌提出疑问 → 芊悦深入解释，不敷衍
- **必须有至少 2 处两人观点明确不同的地方**（不是假装不同，是真的持不同立场并各自给出理由）
- 加入自然反应词和口语化表达：
  - 惊讶："哇塞"、"不是吧"、"这也太..."、"我天"、"震惊了"
  - 认同："确实"、"你说得对"、"有道理"、"本来就是嘛"
  - 质疑："真的假的？"、"等等"、"我不太同意"、"话是这么说啦但是..."
  - 搞笑："笑死"、"你这个比喻绝了"、"哈哈哈哈"、"离谱"
  - 过渡："对了"、"哎说到这个"、"你知道吗"、"而且而且"
  - 思考："嗯..."、"怎么说呢"、"这个嘛"、"我觉得吧"
- 偶尔互相吐槽、开玩笑，像闺蜜聊天
- 允许打断对方说话（用"——"表示）
- 对话中可以提到"我昨天刚看到"、"我一个朋友说"之类增加真实感

## 节奏变化指引（重要！）
不要每条新闻都用同一种节奏。脚本里要混合以下三种节奏：
1. **深度讨论**（1-2 条核心新闻）：花 4-6 个来回深入聊，有观点交锋，有类比解释，有延伸思考
2. **快速带过**（2-3 条次要新闻）：1-2 个来回搞定，信息密度高，节奏快
3. **互相吐槽/发散**（穿插在讨论中）：聊到某个点突然跑题、互怼、讲段子，然后拉回来

## 内容结构
1. **开场**（固定格式）：
   - {host1_name}打招呼 + 报日期
   - {host2_name}接话 + 预告今天最炸的 1-2 条新闻（制造悬念）
2. **深度聊天**（选 2-3 条最有料的新闻深入讨论）：
   - 不是念标题！要聊：这事为什么重要？对我们有什么影响？背后的逻辑是什么？
   - **至少 3 处使用生活化类比**（"这就像..."、"你可以理解为..."、"就好比..."）
   - 主持人要有自己的看法和立场，不是中立播报
   - 适当加入年轻人能 get 的流行文化梗
3. **快讯速览**（剩余新闻快速带过）：
   - "接下来快速过几条——" 简洁总结，不拖沓
4. **结尾**（固定格式）：
   - {host1_name}用 1-2 句话总结今天关键洞察
   - {host2_name}说 slogan "{slogan}" + "我们明天见～"

## ⛔ 不要做的事（No-Go List）
- **不要**用"好的，接下来我们聊聊..."这种生硬过渡，要自然地从上一个话题引到下一个
- **不要**每条新闻都是"芊悦介绍→萌萌感叹→芊悦分析→萌萌总结"的固定套路，要有变化
- **不要**让萌萌变成只会说"哇"和"好厉害"的捧哏，她要有自己的独立见解
- **不要**用书面语气，比如"值得注意的是"、"综上所述"、"不可忽视"
- **不要**在每条新闻之间加明显的分隔语，新闻之间的过渡要像聊天自然跳转
- **不要**把所有新闻都说成"重磅"或"震撼"，有些就是普通新闻，轻松带过就好
- **不要**在开场就剧透所有新闻内容，只预告最劲爆的制造悬念
- **不要**让两个人的语气太相似，芊悦偏理性分析，萌萌偏感性直觉

## 格式要求
- 使用 <{host1_name}></{host1_name}> 和 <{host2_name}></{host2_name}> 标签包裹每段对话
- 每个标签内只放一个人的一段话，不要嵌套
- 总字数 {script_length}
- **对话轮次 35-42 轮**（不要超过 42 轮，保证互动密度）
- 每段话不要太长，控制在 2-4 句话以内（模拟真实对话的短句交互）

## 格式示例
<{host1_name}>嘿！大家好，欢迎收听《{show_name}》，我是{host1_name}～今天是4月4号，周六。</{host1_name}>
<{host2_name}>我是{host2_name}！今天有条消息我真的忍不住要先剧透一下——Google 又放大招了，而且这次是开源的！</{host2_name}>
<{host1_name}>哈哈别急，咱们一个一个来。</{host1_name}>

## 今日早报内容
{news_content}

请直接输出对话脚本，不要加任何额外说明。
"""


# ─────────────────────────── 工具函数 ───────────────────────────

def load_show_config(config_path: Optional[str] = None) -> dict:
    """
    加载 show_identity.yaml 配置。

    Args:
        config_path: 配置文件路径，默认 config/show_identity.yaml。

    Returns:
        配置字典。
    """
    if config_path is None:
        config_path = str(Path(__file__).resolve().parent.parent / "config" / "show_identity.yaml")
    with open(config_path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def _build_hosts_description(hosts: list) -> str:
    """根据 hosts 列表生成主持人设定文本。"""
    lines = []
    for h in hosts:
        lines.append(f"- **{h['name']}**（{h['role']}）：{h['personality']}")
    return "\n".join(lines)


def build_prompt(news_content: str, show_config: Optional[dict] = None) -> str:
    """
    基于早报内容构建对话脚本生成 prompt。

    Args:
        news_content: 今日科技早报 markdown 内容。
        show_config: show_identity 配置字典，为 None 时自动加载。

    Returns:
        完整的 prompt 字符串。
    """
    if show_config is None:
        show_config = load_show_config()

    show = show_config["show"]
    hosts = show_config["hosts"]

    return SCRIPT_GENERATION_PROMPT.format(
        show_name=show["name"],
        slogan=show["slogan"],
        duration_target=show["duration_target"],
        script_length=show["script_length"],
        hosts_description=_build_hosts_description(hosts),
        host1_name=hosts[0]["name"],
        host2_name=hosts[1]["name"],
        news_content=news_content,
    )


def validate_script(script_text: str, strict: bool = False) -> bool:
    """
    验证对话脚本格式是否正确（v2 加严）。

    检查:
    - 包含 <芊悦> 和 <萌萌> 标签
    - 标签正确闭合
    - 至少 35 轮对话
    - 字数范围检查

    Args:
        script_text: 脚本文本。
        strict: True 时字数/轮次超限直接 raise ValueError。

    Returns:
        True 如果格式正确。

    Raises:
        ValueError 如果格式有问题。
    """
    qianyue_count = len(re.findall(r"<芊悦>.*?</芊悦>", script_text, re.DOTALL))
    mengmeng_count = len(re.findall(r"<萌萌>.*?</萌萌>", script_text, re.DOTALL))

    total_turns = qianyue_count + mengmeng_count

    if qianyue_count == 0:
        raise ValueError("脚本中没有 <芊悦> 标签")
    if mengmeng_count == 0:
        raise ValueError("脚本中没有 <萌萌> 标签")

    # 轮次检查
    if total_turns < 35:
        raise ValueError(
            f"对话轮次不足（芊悦:{qianyue_count}, 萌萌:{mengmeng_count}, "
            f"共 {total_turns} 轮），至少需要 35 轮"
        )
    if strict and total_turns > 42:
        raise ValueError(
            f"对话轮次过多（共 {total_turns} 轮），不应超过 42 轮"
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

    # 字数检查
    char_count = len(script_text)
    if strict:
        if char_count < 500:
            raise ValueError(f"脚本字数极少（{char_count} 字），不予发布")
        if char_count < 2500:
            raise ValueError(
                f"脚本字数不足（{char_count} 字），可能 LLM 输出不完整"
            )
        if char_count > 4000:
            raise ValueError(
                f"脚本字数过多（{char_count} 字），超出时长目标"
            )
    else:
        if char_count < 2500:
            logger.warning(
                "⚠️ 脚本字数偏少: %d 字（建议 2800-3500 字），可能不足 5 分钟",
                char_count,
            )
        if char_count > 4000:
            logger.warning(
                "⚠️ 脚本字数偏多: %d 字（建议 2800-3500 字），可能超过 8 分钟",
                char_count,
            )

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
