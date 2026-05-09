#!/usr/bin/env python3
"""
run_pipeline.py
总控脚本：Markdown → 生图 → HTML 排版

执行顺序：
  1. 扫描 Markdown 中的图片占位符 ![图注](SLUG_imgN_keyword.png)
  2. 为每个占位符生成英文 prompt
  3. 调用 image_generator.py 逐张生图，等落盘后继续
  4. 所有图片就绪后，调用 convert.js 渲染 HTML

用法：
  python3 run_pipeline.py --input article.md --output outputs/wechat --filename slug_article.html
"""

import os
import sys
import re
import subprocess
import argparse
import time
from pathlib import Path

SCRIPTS_DIR = Path(__file__).parent
SKILL_DIR = SCRIPTS_DIR.parent


def load_config():
    config_path = SKILL_DIR / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml
        with open(config_path, encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        config = {}
        current_section = None
        with open(config_path, encoding='utf-8') as f:
            for line in f:
                stripped = line.strip()
                if not stripped or stripped.startswith("#"):
                    continue
                if stripped.endswith(":") and not stripped.startswith(" "):
                    current_section = stripped[:-1]
                    config[current_section] = {}
                elif ":" in stripped and current_section:
                    key, _, val = stripped.partition(":")
                    config[current_section][key.strip()] = val.strip()
                elif ":" in stripped:
                    key, _, val = stripped.partition(":")
                    config[key.strip()] = val.strip()
        return config


def get_api_key(cfg):
    key = os.environ.get("IMAGE_API_KEY")
    if key:
        return key
    if isinstance(cfg.get("image_api"), dict):
        return cfg["image_api"].get("api_key", "")
    return ""


def get_model(cfg):
    model = os.environ.get("IMAGE_MODEL")
    if model:
        return model
    if isinstance(cfg.get("image_api"), dict):
        return cfg["image_api"].get("model", "")
    return ""


def get_base_url(cfg):
    base_url = os.environ.get("IMAGE_BASE_URL")
    if base_url:
        return base_url
    if isinstance(cfg.get("image_api"), dict):
        return cfg["image_api"].get("base_url", "")
    return ""


def extract_placeholders(md_content):
    """
    提取所有图片占位符，返回 list of (full_match, alt, filename, keyword)
    占位符格式：![图注](SLUG_imgN_keyword.png)
    """
    pattern = r'!\[([^\]]*)\]\(([^)]+\.png)\)'
    results = []
    for m in re.finditer(pattern, md_content):
        alt = m.group(1)
        filename = m.group(2)
        # 从文件名提取 keyword（最后一个 _ 之后，去掉 .png）
        parts = filename.rsplit("_", 1)
        keyword = parts[-1].replace(".png", "") if len(parts) > 1 else filename.replace(".png", "")
        results.append({
            "alt": alt,
            "filename": filename,
            "keyword": keyword,
        })
    return results


def auto_detect_style(md_content):
    """
    根据文章内容自动判断最合适的图片风格。
    规则：关键词匹配，命中最多的风格胜出。
    """
    # 每个风格的关键词权重表
    style_keywords = {
        "dark-tech": [
            "AI", "人工智能", "模型", "算法", "代码", "编程", "API", "GPT", "Claude",
            "技术", "架构", "系统", "数据", "深度学习", "神经网络", "自动化",
            "Prompt", "Token", "LLM", "Agent", "智能体", "工具链",
        ],
        "cool-editorial": [
            "方法论", "框架", "模型", "体系", "策略", "分析", "复盘", "SOP",
            "商业", "增长", "转化率", "漏斗", "ROI", "指标", "数据驱动",
            "系统化", "结构化", "流程", "拆解", "底层逻辑",
        ],
        "sketch-warm": [
            "感情", "感悟", "故事", "朋友", "经历", "成长", "人生",
            "想通", "认知", "焦虑", "迷茫", "选择", "勇气", "孤独",
            "内心", "情感", "回忆", "温暖", "治愈", "脱单", "恋爱",
        ],
        "warm-flat": [
            "教程", "指南", "怎么做", "步骤", "实操", "工具", "效率",
            "技巧", "干货", "入门", "上手", "搭建", "配置", "安装",
            "推荐", "清单", "盘点", "对比", "测评",
        ],
    }

    scores = {}
    content_lower = md_content.lower()
    for style_name, keywords in style_keywords.items():
        score = sum(1 for kw in keywords if kw.lower() in content_lower)
        scores[style_name] = score

    # 取得分最高的；平分时按优先级：sketch-warm > warm-flat > cool-editorial > dark-tech
    priority = ["sketch-warm", "warm-flat", "cool-editorial", "dark-tech"]
    best = max(priority, key=lambda s: (scores.get(s, 0), -priority.index(s)))

    if scores.get(best, 0) == 0:
        return "warm-flat"  # 全部零分时用通用默认
    return best


def load_style(cfg, style_name, md_content=None):
    """
    从 config.yaml 加载指定风格预设。
    style_name=None 且 md_content 有值时，自动检测风格。
    返回 (style_dict, detected_name)。
    """
    styles = cfg.get("image_styles") or {}

    # 1. 命令行显式指定
    if style_name and style_name in styles:
        return styles[style_name], style_name

    # 2. 自动检测
    if md_content and not style_name:
        detected = auto_detect_style(md_content)
        if detected in styles:
            return styles[detected], detected

    # 3. config 默认值
    default = (cfg.get("image_api") or {}).get("default_style", "")
    if default and default in styles:
        return styles[default], default

    return None, None


def build_prompt(alt, keyword, style=None):
    """
    根据图注 + 风格预设生成结构化英文图片 prompt。

    结构：
      Subject: {场景描述，从 alt 文本来}
      Style: {从风格预设的 prompt_suffix 来，保证全文统一}
      Negative: {统一的负面提示}

    如果没有风格预设，使用通用后缀兜底。
    """
    # --- Subject ---
    if alt and len(alt) > 20:
        scene = alt
    elif alt:
        scene = f"{alt}, {keyword}" if keyword else alt
    else:
        scene = keyword

    # --- Style suffix ---
    if style and style.get("prompt_suffix"):
        style_suffix = style["prompt_suffix"].strip()
    else:
        # 兜底：没有风格预设时用通用指令
        style_suffix = (
            "flat vector illustration, clean modern design, "
            "soft warm color palette, generous whitespace, "
            "simplified silhouettes, no text no words no letters, "
            "wide 16:9 composition"
        )

    # --- Negative ---
    negative = "Absolutely no text, no letters, no numbers, no watermarks, no signatures, no human faces."

    return f"{scene}. {style_suffix}. {negative}"


def generate_images(placeholders, images_dir, api_key, model, base_url="", style=None):
    """逐张生图，等落盘后继续。返回成功/失败列表。"""
    success = []
    failed = []
    images_dir = Path(images_dir)
    images_dir.mkdir(parents=True, exist_ok=True)

    for i, ph in enumerate(placeholders):
        output_path = images_dir / ph["filename"]
        print(f"[pipeline] 生图 {i+1}/{len(placeholders)}: {ph['filename']}")

        if output_path.exists():
            print(f"[pipeline]   已存在，跳过生成")
            success.append(ph)
            continue

        prompt = build_prompt(ph["alt"], ph["keyword"], style=style)
        print(f"[pipeline]   prompt: {prompt}")

        env = os.environ.copy()
        env["IMAGE_API_KEY"] = api_key
        env["IMAGE_MODEL"] = model
        if base_url:
            env["IMAGE_BASE_URL"] = base_url

        result = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "image_generator.py"),
             "--prompt", prompt,
             "--output", str(output_path),
             "--retry", "2"],
            env=env,
            capture_output=True,
            text=True
        )

        if result.returncode == 0 and output_path.exists():
            # 等文件真正落盘
            for _ in range(5):
                if output_path.stat().st_size > 0:
                    break
                time.sleep(0.5)
            print(f"[pipeline]   ✅ 生图成功 ({output_path.stat().st_size // 1024}KB)")
            success.append(ph)
        else:
            print(f"[pipeline]   ⚠️ 生图失败，跳过")
            if result.stderr:
                print(f"[pipeline]   stderr: {result.stderr.strip()}")
            failed.append(ph)

    return success, failed


def run_convert(input_file, output_file, images_dir):
    """调用 convert.js 渲染 HTML。"""
    node_result = subprocess.run(
        ["node", str(SCRIPTS_DIR / "convert.js"),
         "--input", str(input_file),
         "--output", str(output_file),
         "--images-dir", str(images_dir)],
        capture_output=True,
        text=True
    )
    if node_result.stdout:
        print(node_result.stdout.strip())
    if node_result.returncode != 0:
        print(f"[pipeline] ❌ convert.js 失败:", file=sys.stderr)
        print(node_result.stderr, file=sys.stderr)
        return False
    return True


def main():
    parser = argparse.ArgumentParser(description="公众号文章发布总控脚本")
    parser.add_argument("--input", required=True, help="输入 Markdown 文件路径")
    parser.add_argument("--output", required=True, help="输出目录（如 outputs/wechat）")
    parser.add_argument("--filename", required=True, help="输出 HTML 文件名（如 slug_article.html）")
    parser.add_argument("--style", default=None, help="图片风格预设（warm-flat/dark-tech/cool-editorial/sketch-warm），默认读 config.yaml")
    args = parser.parse_args()

    input_file = Path(args.input).resolve()
    output_dir = Path(args.output)
    output_file = output_dir / args.filename
    images_dir = output_dir / "images"

    # 检查输入文件
    if not input_file.exists():
        print(f"[pipeline] ❌ 输入文件不存在: {input_file}", file=sys.stderr)
        sys.exit(1)

    cfg = load_config()
    api_key = get_api_key(cfg)
    model = get_model(cfg)
    base_url = get_base_url(cfg)

    if not api_key:
        print("[pipeline] ❌ 未找到 IMAGE_API_KEY（检查 config.yaml 或环境变量）", file=sys.stderr)
        sys.exit(1)

    # 读取 Markdown（提前读，供风格自动检测使用）
    md_content = input_file.read_text(encoding="utf-8")

    # 加载风格预设（无 --style 时根据文章内容自动检测）
    style, style_name = load_style(cfg, args.style, md_content=md_content)
    if style:
        auto_tag = "（自动检测）" if not args.style else ""
        print(f"[pipeline] 图片风格: {style.get('name', style_name)} — {style.get('description', '')} {auto_tag}")
    else:
        print(f"[pipeline] 图片风格: 通用默认（未匹配到预设）")

    provider = f"豆包/火山引擎({base_url})"
    print(f"[pipeline] 输入: {input_file}")
    print(f"[pipeline] 输出: {output_file}")
    print(f"[pipeline] 生图模型: {model} ({provider})")

    # 扫描占位符
    placeholders = extract_placeholders(md_content)
    print(f"[pipeline] 发现 {len(placeholders)} 个图片占位符")

    # 生图
    if placeholders:
        success, failed = generate_images(placeholders, images_dir, api_key, model, base_url=base_url, style=style)
        print(f"[pipeline] 生图完成：成功 {len(success)} 张，失败 {len(failed)} 张")
    else:
        print("[pipeline] 无图片占位符，跳过生图步骤")
        images_dir.mkdir(parents=True, exist_ok=True)

    # 渲染 HTML
    print("[pipeline] 开始渲染 HTML...")
    output_dir.mkdir(parents=True, exist_ok=True)
    if not run_convert(input_file, output_file, images_dir):
        sys.exit(1)

    size_kb = output_file.stat().st_size / 1024
    print(f"[pipeline] ✅ 完成！HTML: {output_file} ({size_kb:.1f} KB)")

    # 自动在浏览器中打开 HTML，方便用户复制粘贴到公众号编辑器
    import webbrowser
    abs_path = output_file.resolve()
    webbrowser.open(f"file://{abs_path}")
    print(f"[pipeline] 🌐 已在浏览器中打开 HTML")
    print(f"[pipeline] 📋 操作步骤：浏览器中 Ctrl/Cmd+A 全选 → Ctrl/Cmd+C 复制 → 粘贴到公众号编辑器")


if __name__ == "__main__":
    main()
