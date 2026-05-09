#!/usr/bin/env python3
"""
image_generator.py
使用豆包 API 生成图片，保存为 PNG 文件。

用法：
  python3 image_generator.py --prompt "a cat" --output out.png
  IMAGE_API_KEY=xxx python3 image_generator.py ...

配置（优先级从高到低）：
  1. 环境变量 IMAGE_API_KEY
  2. config.yaml 中 image_api.api_key
"""

import os
import sys
import argparse
import base64
import json
import time
from pathlib import Path

def load_config():
    config_path = Path(__file__).parent.parent / "config.yaml"
    if not config_path.exists():
        return {}
    try:
        import yaml
        with open(config_path, encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    except ImportError:
        # 不依赖 yaml，手动解析简单格式
        config = {}
        with open(config_path, encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if ":" in line and not line.startswith("#"):
                    key, _, val = line.partition(":")
                    config[key.strip()] = val.strip()
        return config

def get_api_key(cfg):
    key = os.environ.get("IMAGE_API_KEY")
    if key:
        return key
    # 嵌套 yaml 结构
    if isinstance(cfg.get("image_api"), dict):
        return cfg["image_api"].get("api_key", "")
    return cfg.get("IMAGE_API_KEY", "")

def get_model(cfg):
    model = os.environ.get("IMAGE_MODEL")
    if model:
        return model
    if isinstance(cfg.get("image_api"), dict):
        return cfg["image_api"].get("model", "")
    return cfg.get("IMAGE_MODEL", "")

def get_base_url(cfg):
    base_url = os.environ.get("IMAGE_BASE_URL")
    if base_url:
        return base_url
    if isinstance(cfg.get("image_api"), dict):
        return cfg["image_api"].get("base_url", "")
    return ""

def is_gemini(cfg):
    """判断使用 Gemini API 还是 OpenAI 兼容 API（豆包）"""
    base_url = get_base_url(cfg)
    if base_url and "google" not in base_url:
        return False
    model = get_model(cfg)
    return "gemini" in model.lower()

def generate_image(prompt: str, output_path: str, api_key: str, model: str, base_url: str = "", use_gemini: bool = True) -> bool:
    """
    生成图片。根据配置自动选择 Gemini API 或 OpenAI 兼容 API（豆包）。
    """
    import urllib.request
    import urllib.error

    if use_gemini:
        return _generate_gemini(prompt, output_path, api_key, model)
    else:
        return _generate_openai_compat(prompt, output_path, api_key, model, base_url)


def _generate_gemini(prompt, output_path, api_key, model):
    """Gemini 官方 API 生图"""
    import urllib.request
    import urllib.error

    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]}
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "x-goog-api-key": api_key,
    }, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"[image_generator] HTTP {e.code}: {err_body}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[image_generator] 请求失败: {e}", file=sys.stderr)
        return False

    try:
        for candidate in data.get("candidates", []):
            for part in candidate.get("content", {}).get("parts", []):
                inline_data = part.get("inlineData") or part.get("inline_data")
                if inline_data:
                    img_data = base64.b64decode(inline_data["data"])
                    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                    with open(output_path, "wb") as f:
                        f.write(img_data)
                    print(f"[image_generator] 图片已保存: {output_path}", file=sys.stderr)
                    return True
    except Exception as e:
        print(f"[image_generator] 解析响应失败: {e}", file=sys.stderr)
        return False

    print(f"[image_generator] 响应中未找到图片数据", file=sys.stderr)
    return False


def _generate_openai_compat(prompt, output_path, api_key, model, base_url):
    """OpenAI 兼容 API 生图（豆包/火山引擎等）"""
    import urllib.request
    import urllib.error

    url = f"{base_url.rstrip('/')}/images/generations"
    payload = {
        "model": model,
        "prompt": prompt,
        "n": 1,
        "size": "1920x1920",
        "response_format": "b64_json"
    }
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url, data=body, headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        err_body = e.read().decode("utf-8")
        print(f"[image_generator] HTTP {e.code}: {err_body}", file=sys.stderr)
        return False
    except Exception as e:
        print(f"[image_generator] 请求失败: {e}", file=sys.stderr)
        return False

    try:
        images = data.get("data", [])
        if images:
            b64_str = images[0].get("b64_json", "")
            if b64_str:
                img_data = base64.b64decode(b64_str)
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(img_data)
                print(f"[image_generator] 图片已保存: {output_path}", file=sys.stderr)
                return True
            # 有些实现返回 url 而不是 b64
            img_url = images[0].get("url", "")
            if img_url:
                print(f"[image_generator] 返回的是URL，正在下载: {img_url}", file=sys.stderr)
                with urllib.request.urlopen(img_url, timeout=60) as img_resp:
                    img_data = img_resp.read()
                Path(output_path).parent.mkdir(parents=True, exist_ok=True)
                with open(output_path, "wb") as f:
                    f.write(img_data)
                print(f"[image_generator] 图片已保存: {output_path}", file=sys.stderr)
                return True
    except Exception as e:
        print(f"[image_generator] 解析响应失败: {e}", file=sys.stderr)
        print(f"[image_generator] 原始响应: {json.dumps(data)[:500]}", file=sys.stderr)
        return False

    print(f"[image_generator] 响应中未找到图片数据", file=sys.stderr)
    print(f"[image_generator] 原始响应: {json.dumps(data)[:500]}", file=sys.stderr)
    return False


def main():
    parser = argparse.ArgumentParser(description="豆包 API 生图")
    parser.add_argument("--prompt", required=True, help="英文图片描述")
    parser.add_argument("--output", required=True, help="输出 PNG 文件路径")
    parser.add_argument("--retry", type=int, default=2, help="失败重试次数")
    args = parser.parse_args()

    cfg = load_config()
    api_key = get_api_key(cfg)
    model = get_model(cfg)
    base_url = get_base_url(cfg)
    use_gemini = is_gemini(cfg)

    if not api_key:
        print("[image_generator] 错误：未找到 IMAGE_API_KEY", file=sys.stderr)
        sys.exit(1)

    provider = "Gemini" if use_gemini else f"OpenAI兼容({base_url})"
    print(f"[image_generator] 使用: {provider}, 模型: {model}", file=sys.stderr)

    for attempt in range(args.retry + 1):
        if attempt > 0:
            wait = 2 ** attempt
            print(f"[image_generator] 第 {attempt+1} 次重试，等待 {wait}s...", file=sys.stderr)
            time.sleep(wait)
        if generate_image(args.prompt, args.output, api_key, model, base_url, use_gemini):
            sys.exit(0)

    print(f"[image_generator] 全部重试失败: {args.output}", file=sys.stderr)
    sys.exit(1)


if __name__ == "__main__":
    main()
