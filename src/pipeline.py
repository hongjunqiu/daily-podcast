"""每日科技播客 Pipeline v2 — 去掉 Podcastfy 依赖，直接用千问 TTS。

流程: 对话脚本文件 → TTS 逐段合成 → 音频合并 → Blog Post → Git 发布

用法:
    python src/pipeline.py --transcript data/transcripts/transcript_2026-04-01.txt --site-repo /path/to/site --dry-run
    python src/pipeline.py --transcript data/transcripts/transcript_2026-04-01.txt
"""

import argparse
import datetime
import logging
import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import List, Optional, Tuple

from qwen_tts import synthesize_segment, get_voice_config

logger = logging.getLogger("daily_podcast.pipeline")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


# ─────────────────────────── Step 1: 解析对话脚本 ───────────────────────────

def parse_transcript(transcript_text: str) -> List[Tuple[str, str]]:
    """
    解析对话脚本，提取说话人和文本。

    脚本格式: <芊悦>文本</芊悦> 和 <萌萌>文本</萌萌> 交替。

    Returns:
        List of (speaker, text) tuples.
    """
    pattern = r"<(芊悦|萌萌)>(.*?)</\1>"
    matches = re.findall(pattern, transcript_text, re.DOTALL)

    if not matches:
        raise ValueError("对话脚本格式错误：未找到 <芊悦>/<萌萌> 标签")

    segments = []
    for speaker, text in matches:
        clean_text = " ".join(text.split()).strip()
        if clean_text:
            segments.append((speaker, clean_text))

    if not segments:
        raise ValueError("对话脚本为空：所有段落都没有内容")

    logger.info("解析对话脚本: %d 段", len(segments))
    return segments


def load_transcript(path: str) -> str:
    """从文件读取对话脚本。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"对话脚本文件不存在: {path}")
    content = p.read_text(encoding="utf-8")
    if not content.strip():
        raise ValueError(f"对话脚本文件为空: {path}")
    return content


# ─────────────────────────── Step 2: TTS 逐段合成 ───────────────────────────

def synthesize_all_segments(
    segments: List[Tuple[str, str]],
    output_dir: str,
) -> List[str]:
    """
    对每个对话段落调用千问 TTS 合成音频。

    Args:
        segments: (speaker, text) 列表。
        output_dir: 临时音频文件输出目录。

    Returns:
        按顺序排列的 MP3 文件路径列表。
    """
    os.makedirs(output_dir, exist_ok=True)
    audio_files = []

    for idx, (speaker, text) in enumerate(segments):
        voice_cfg = get_voice_config(speaker)
        output_path = os.path.join(output_dir, f"{idx:03d}_{speaker}.mp3")

        synthesize_segment(
            text=text,
            output_path=output_path,
            voice_name=voice_cfg["voice"],
            instructions=voice_cfg["instructions"],
        )
        audio_files.append(output_path)
        logger.info("合成 %d/%d: %s (%d 字)", idx + 1, len(segments), speaker, len(text))

    return audio_files


# ─────────────────────────── Step 3: 音频合并 ───────────────────────────

def merge_audio_files(audio_files: List[str], output_path: str) -> str:
    """
    用 ffmpeg 将多个 MP3 文件顺序合并。

    Args:
        audio_files: MP3 文件路径列表。
        output_path: 输出合并后的 MP3 路径。

    Returns:
        输出文件路径。
    """
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    # 生成 400ms 静音文件用于段落间停顿
    silence_path = os.path.join(os.path.dirname(output_path), "_silence_400ms.mp3")
    silence_cmd = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "anullsrc=r=24000:cl=mono",
        "-t", "0.4",
        "-acodec", "libmp3lame", "-q:a", "2",
        silence_path,
    ]
    silence_result = subprocess.run(silence_cmd, capture_output=True, text=True)
    if silence_result.returncode != 0:
        raise RuntimeError(f"ffmpeg 生成静音文件失败:\n{silence_result.stderr}")

    # 创建 ffmpeg concat 列表文件，段落间插入静音
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        for i, audio in enumerate(audio_files):
            f.write(f"file '{audio}'\n")
            if i < len(audio_files) - 1:
                f.write(f"file '{silence_path}'\n")
        concat_list = f.name

    try:
        cmd = [
            "ffmpeg", "-y", "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-acodec", "libmp3lame", "-q:a", "2",
            output_path,
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"ffmpeg 合并失败:\n{result.stderr}")
    finally:
        os.unlink(concat_list)
        if os.path.exists(silence_path):
            os.unlink(silence_path)

    logger.info("音频合并完成: %s (%d bytes)", output_path, os.path.getsize(output_path))
    return output_path


# ─────────────────────────── Step 4: Blog Post 生成 ───────────────────────────

def parse_news_markdown(news_path: str) -> str:
    """解析早报 markdown 文件，生成新闻列表 markdown。

    Args:
        news_path: 早报 markdown 文件路径。

    Returns:
        格式化的新闻列表 markdown 字符串，解析失败返回空字符串。
    """
    p = Path(news_path)
    if not p.exists():
        logger.warning("早报文件不存在: %s", news_path)
        return ""

    content = p.read_text(encoding="utf-8")
    sections = []
    current_heading = None
    current_items: List = []

    def _flush_section():
        if current_heading and current_items:
            final = []
            for item in current_items:
                if isinstance(item, tuple):
                    title, summary, _ = item
                    final.append(f"- **{title}** — {summary}")
                else:
                    final.append(item)
            sections.append(f"### {current_heading}\n\n" + "\n".join(final))

    for line in content.split("\n"):
        heading_match = re.match(r"^##\s+(.+)$", line)
        if heading_match:
            _flush_section()
            current_heading = heading_match.group(1).strip()
            current_items = []
            continue

        item_match = re.match(r"^\d+\.\s+\*\*(.+?)\*\*\s*[—–-]\s*(.+)$", line)
        if item_match:
            # Flush previous tuple if it had no link
            if current_items and isinstance(current_items[-1], tuple):
                title, summary, _ = current_items[-1]
                current_items[-1] = f"- **{title}** — {summary}"
            current_items.append((item_match.group(1).strip(), item_match.group(2).strip(), None))
            continue

        link_match = re.match(r"^\s*🔗\s*<?([^>\s]+)>?\s*$", line)
        if link_match and current_items and isinstance(current_items[-1], tuple):
            title, summary, _ = current_items[-1]
            current_items[-1] = f"- **[{title}]({link_match.group(1)})** — {summary}"
            continue

    _flush_section()

    if not sections:
        logger.warning("早报文件解析结果为空: %s", news_path)
        return ""

    return "\n\n".join(sections)


def _extract_news_headlines(news_path: str, max_items: int = 5) -> List[str]:
    """从早报 markdown 提取前 N 条新闻标题。"""
    p = Path(news_path)
    if not p.exists():
        return []
    content = p.read_text(encoding="utf-8")
    titles = re.findall(r"^\d+\.\s+\*\*(.+?)\*\*\s*[—–-]", content, re.MULTILINE)
    return titles[:max_items]


def _wavesurfer_player(audio_filename: str) -> str:
    """生成 wavesurfer.js 内联播放器 HTML。"""
    return f'''<div style="background: linear-gradient(135deg, #eef2ff 0%, #f8fafc 100%); border-radius: 12px; padding: 16px; margin: 1rem 0;">
  <div id="waveform" style="border-radius: 8px; overflow: hidden;"></div>
  <div style="display: flex; align-items: center; gap: 12px; margin-top: 12px;">
    <button id="playBtn" style="background: #6366f1; color: white; border: none; border-radius: 50%; width: 48px; height: 48px; cursor: pointer; font-size: 18px; display: flex; align-items: center; justify-content: center; flex-shrink: 0;">▶</button>
    <span id="currentTime" style="font-variant-numeric: tabular-nums; color: #6b7280;">0:00</span>
    <span style="color: #9ca3af;">/</span>
    <span id="duration" style="font-variant-numeric: tabular-nums; color: #6b7280;">0:00</span>
    <div style="margin-left: auto; display: flex; gap: 4px;">
      <button class="speed-btn" data-speed="0.5" style="background: transparent; color: #6b7280; border: 1px solid #e5e7eb; border-radius: 6px; padding: 4px 8px; cursor: pointer; font-size: 12px;">0.5x</button>
      <button class="speed-btn" data-speed="1" style="background: #6366f1; color: white; border: 1px solid #6366f1; border-radius: 6px; padding: 4px 8px; cursor: pointer; font-size: 12px;">1x</button>
      <button class="speed-btn" data-speed="1.5" style="background: transparent; color: #6b7280; border: 1px solid #e5e7eb; border-radius: 6px; padding: 4px 8px; cursor: pointer; font-size: 12px;">1.5x</button>
      <button class="speed-btn" data-speed="2" style="background: transparent; color: #6b7280; border: 1px solid #e5e7eb; border-radius: 6px; padding: 4px 8px; cursor: pointer; font-size: 12px;">2x</button>
    </div>
  </div>
</div>

<script src="https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.esm.js" type="module"></script>
<script type="module">
import WaveSurfer from 'https://unpkg.com/wavesurfer.js@7/dist/wavesurfer.esm.js';

const ctx = document.createElement('canvas').getContext('2d');
const gradient = ctx.createLinearGradient(0, 0, 0, 80);
gradient.addColorStop(0, '#818cf8');
gradient.addColorStop(0.5, '#a5b4fc');
gradient.addColorStop(1, '#c7d2fe');
const progressGradient = ctx.createLinearGradient(0, 0, 0, 80);
progressGradient.addColorStop(0, '#4f46e5');
progressGradient.addColorStop(0.5, '#6366f1');
progressGradient.addColorStop(1, '#818cf8');

const wavesurfer = WaveSurfer.create({{
  container: '#waveform',
  waveColor: gradient,
  progressColor: progressGradient,
  cursorColor: '#4f46e5',
  barWidth: 3,
  barRadius: 3,
  barGap: 2,
  height: 80,
  normalize: true,
  url: '/audio/podcast/{audio_filename}'
}});

const playBtn = document.getElementById('playBtn');
const currentTimeEl = document.getElementById('currentTime');
const durationEl = document.getElementById('duration');

function formatTime(seconds) {{
  const m = Math.floor(seconds / 60);
  const s = Math.floor(seconds % 60);
  return m + ':' + String(s).padStart(2, '0');
}}

wavesurfer.on('ready', () => {{
  durationEl.textContent = formatTime(wavesurfer.getDuration());
}});

wavesurfer.on('timeupdate', (time) => {{
  currentTimeEl.textContent = formatTime(time);
}});

playBtn.addEventListener('click', () => {{
  wavesurfer.playPause();
}});

wavesurfer.on('play', () => {{ playBtn.textContent = '⏸'; }});
wavesurfer.on('pause', () => {{ playBtn.textContent = '▶'; }});

document.querySelectorAll('.speed-btn').forEach(btn => {{
  btn.addEventListener('click', () => {{
    document.querySelectorAll('.speed-btn').forEach(b => {{
      b.style.background = 'transparent';
      b.style.color = '#6b7280';
      b.style.borderColor = '#e5e7eb';
    }});
    btn.style.background = '#6366f1';
    btn.style.color = 'white';
    btn.style.borderColor = '#6366f1';
    wavesurfer.setPlaybackRate(parseFloat(btn.dataset.speed));
  }});
}});
</script>'''


def generate_blog_post(
    transcript_text: str,
    audio_filename: str,
    date: str,
    site_repo: str,
    news_path: Optional[str] = None,
    audio_path: Optional[str] = None,
) -> str:
    """生成 Astro blog post markdown 文件。"""

    # 获取音频文件大小和时长
    audio_size = 0
    audio_duration = 480
    if audio_path and os.path.exists(audio_path):
        audio_size = os.path.getsize(audio_path)
        result = subprocess.run(
            ['ffprobe', '-v', 'quiet', '-show_entries', 'format=duration', '-of', 'csv=p=0', audio_path],
            capture_output=True, text=True
        )
        audio_duration = int(float(result.stdout.strip())) if result.returncode == 0 and result.stdout.strip() else 480

    # 转为可读文本
    readable = transcript_text
    readable = re.sub(r"<芊悦>(.*?)</芊悦>", r"**芊悦**：\1\n", readable, flags=re.DOTALL)
    readable = re.sub(r"<萌萌>(.*?)</萌萌>", r"**萌萌**：\1\n", readable, flags=re.DOTALL)
    readable = re.sub(r"<[^>]+>", "", readable)

    # 生成 description
    description = "每日科技播客"
    if news_path:
        desc_headlines = _extract_news_headlines(news_path, max_items=3)
        if desc_headlines:
            description = "今日看点：" + " | ".join(desc_headlines)

    # 生成新闻摘要 blockquote
    news_summary = ""
    if news_path:
        headlines = _extract_news_headlines(news_path)
        if headlines:
            news_summary = '\n<blockquote style="font-size: 0.875rem; line-height: 1.5; border-left: 3px solid #6366f1; padding: 0.5rem 1rem; margin: 1rem 0; background: #f8fafc;">\n📌 <strong>今日看点</strong>：' + ' | '.join(headlines) + '\n</blockquote>\n'

    # 解析新闻列表
    news_section = ""
    if news_path:
        news_section = parse_news_markdown(news_path)

    # 构建 audio metadata frontmatter 行
    audio_meta = ""
    if audio_size:
        audio_meta += f"\naudioSize: {audio_size}"
    if audio_duration:
        audio_meta += f"\naudioDuration: {audio_duration}"

    if news_section:
        post_content = f"""---
publishDate: {date}
title: '每日科技播客 {date}'
excerpt: '{description}'
audio: /audio/podcast/{audio_filename}{audio_meta}
category: podcast
tags:
  - podcast
  - tech-daily
author: AI Hosts
---
{news_summary}

---

## 今日科技要闻

{news_section}

---

<details>
<summary>📝 完整对话文字版（点击展开）</summary>

{readable.strip()}

</details>
"""
    else:
        post_content = f"""---
publishDate: {date}
title: '每日科技播客 {date}'
excerpt: '{description}'
audio: /audio/podcast/{audio_filename}{audio_meta}
category: podcast
tags:
  - podcast
  - tech-daily
author: AI Hosts
---

---

## 完整对话文字版

{readable.strip()}
"""

    post_dir = os.path.join(site_repo, "src", "data", "post")
    os.makedirs(post_dir, exist_ok=True)
    post_path = os.path.join(post_dir, f"{date}-daily-podcast.md")

    with open(post_path, "w", encoding="utf-8") as f:
        f.write(post_content)

    logger.info("Blog post 生成: %s", post_path)
    return post_path


def copy_audio_to_site(audio_path: str, site_repo: str) -> str:
    """复制音频文件到 site repo。"""
    dest_dir = os.path.join(site_repo, "public", "audio", "podcast")
    os.makedirs(dest_dir, exist_ok=True)
    dest_path = os.path.join(dest_dir, os.path.basename(audio_path))
    shutil.copy2(audio_path, dest_path)
    logger.info("音频复制到: %s", dest_path)
    return dest_path


# ─────────────────────────── Step 5: Git 发布 ───────────────────────────

def git_publish(site_repo: str, date: str, dry_run: bool = False) -> None:
    """Git add + commit + push。"""
    if dry_run:
        logger.info("[DRY RUN] 跳过 git 发布")
        return

    # git add
    result = subprocess.run(["git", "add", "."], cwd=site_repo, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"Git add 失败:\n{result.stderr}")

    # 检查是否有变更
    diff_check = subprocess.run(
        ["git", "diff", "--cached", "--quiet"],
        cwd=site_repo, capture_output=True,
    )
    if diff_check.returncode == 0:
        logger.info("没有变更，跳过 commit/push")
        return

    for cmd in [
        ["git", "commit", "-m", f"🎙️ 每日播客 {date}"],
        ["git", "push"],
    ]:
        logger.info("执行: %s", " ".join(cmd))
        result = subprocess.run(cmd, cwd=site_repo, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError(f"Git 命令失败: {' '.join(cmd)}\n{result.stderr}")

    logger.info("发布完成 ✅")


# ─────────────────────────── 主入口 ───────────────────────────

def run_pipeline(
    transcript_path: str,
    site_repo: Optional[str] = None,
    dry_run: bool = False,
    date: Optional[str] = None,
    news_path: Optional[str] = None,
) -> dict:
    """
    运行完整 pipeline。

    Args:
        transcript_path: 对话脚本文件路径。
        site_repo: Astro 网站 repo 路径。
        dry_run: 不执行 git push。
        date: 日期字符串，默认今天。

    Returns:
        dict 包含各步骤产物路径。
    """
    today = date or datetime.date.today().isoformat()
    results = {"date": today}

    logger.info("=== 每日科技播客 Pipeline v2 启动 [%s] ===", today)

    # Step 1: 读取并解析脚本
    transcript_text = load_transcript(transcript_path)
    segments = parse_transcript(transcript_text)
    results["transcript_path"] = transcript_path
    results["segment_count"] = len(segments)

    # Step 2: TTS 逐段合成
    audio_tmp_dir = str(DATA_DIR / "audio" / "tmp" / today)
    audio_files = synthesize_all_segments(segments, audio_tmp_dir)

    # Step 3: 合并音频
    audio_dir = str(DATA_DIR / "audio")
    os.makedirs(audio_dir, exist_ok=True)
    final_audio = os.path.join(audio_dir, f"{today}.mp3")
    merge_audio_files(audio_files, final_audio)
    results["audio_path"] = final_audio

    # Step 4 & 5: Blog post + 发布
    if site_repo:
        copy_audio_to_site(final_audio, site_repo)
        audio_filename = f"{today}.mp3"
        post_path = generate_blog_post(transcript_text, audio_filename, today, site_repo, news_path=news_path)
        results["post_path"] = post_path

        git_publish(site_repo, today, dry_run=dry_run)
        results["published"] = not dry_run
    else:
        logger.info("未指定 site-repo，跳过 blog post 和发布")

    # 清理临时文件
    shutil.rmtree(audio_tmp_dir, ignore_errors=True)

    logger.info("=== Pipeline 完成 ===")
    return results


def main():
    parser = argparse.ArgumentParser(description="每日科技播客 Pipeline v2")
    parser.add_argument("--transcript", required=True, help="对话脚本文件路径")
    parser.add_argument("--site-repo", help="Astro 网站 repo 路径")
    parser.add_argument("--date", help="日期 YYYY-MM-DD，默认今天")
    parser.add_argument("--dry-run", action="store_true", help="不执行 git push")
    parser.add_argument("--news-path", help="早报 markdown 文件路径")

    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(levelname)s: %(message)s")

    results = run_pipeline(
        transcript_path=args.transcript,
        site_repo=args.site_repo,
        dry_run=args.dry_run,
        date=args.date,
        news_path=args.news_path,
    )

    print(f"\n📊 Pipeline 结果:")
    for k, v in results.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
