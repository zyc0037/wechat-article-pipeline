#!/usr/bin/env python3
from __future__ import annotations
"""
publish_to_wechat.py
发布到微信公众号草稿箱。

两种发布模式：
  1. 剪贴板模式（默认）：HTML → ImgBB 替换 → 复制到剪贴板（public.html）→ 打开公众号编辑器
     用户只需 Cmd+V 粘贴即可，排版 100% 保留
  2. API 模式（--api）：通过 limyai API 推送草稿（含排版），需设置 contentFormat=html

用法：
  # 剪贴板模式（推荐）
  python3 publish_to_wechat.py \
    --html outputs/wechat/slug_article.html \
    --cover outputs/slug_cover_main.png \
    --title "文章标题" \
    --summary "摘要" \
    --slug "slug"

  # API 模式（推荐，排版完整保留）
  python3 publish_to_wechat.py --api \
    --html outputs/wechat/slug_article.html \
    --cover outputs/slug_cover_main.png \
    --title "文章标题" \
    --summary "摘要" \
    --slug "slug"
"""

import os
import sys
import re
import json
import base64
import time
import argparse
import subprocess
import urllib.request
import urllib.error
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
                if stripped.endswith(":") and not line.startswith(" "):
                    current_section = stripped[:-1]
                    config[current_section] = {}
                elif ":" in stripped and current_section:
                    key, _, val = stripped.partition(":")
                    if isinstance(config.get(current_section), dict):
                        config[current_section][key.strip()] = val.strip()
                elif ":" in stripped:
                    key, _, val = stripped.partition(":")
                    config[key.strip()] = val.strip()
        return config


def get_cfg_value(cfg, section, key, env_var=None):
    if env_var:
        val = os.environ.get(env_var)
        if val:
            return val
    if isinstance(cfg.get(section), dict):
        return cfg[section].get(key, "")
    return ""


def upload_to_imgbb(image_data: bytes, api_key: str, upload_url: str, name: str = "image", retries: int = 3) -> str:
    """上传图片到 ImgBB，返回公网 URL。失败返回空字符串。"""
    b64 = base64.b64encode(image_data).decode("utf-8")

    for attempt in range(retries):
        if attempt > 0:
            wait = 2 ** attempt
            print(f"[publish] ImgBB 上传重试 {attempt+1}/{retries}，等待 {wait}s...")
            time.sleep(wait)

        try:
            body = f"key={api_key}&image={urllib.request.quote(b64)}&name={name}"
            req = urllib.request.Request(
                upload_url,
                data=body.encode("utf-8"),
                headers={"Content-Type": "application/x-www-form-urlencoded"},
                method="POST"
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                if data.get("success"):
                    url = data["data"]["url"]
                    print(f"[publish]   ✅ ImgBB 上传成功: {url[:60]}...")
                    return url
                else:
                    print(f"[publish]   ImgBB 返回失败: {data}", file=sys.stderr)
        except Exception as e:
            print(f"[publish]   ImgBB 上传异常: {e}", file=sys.stderr)

    return ""


def replace_base64_images(html: str, imgbb_api_key: str, imgbb_upload_url: str) -> tuple[str, bool]:
    """
    扫描 HTML 中所有 base64 图片，上传到 ImgBB，替换为公网 URL。
    返回 (新HTML, 是否全部成功)
    """
    pattern = r'src="(data:image/[^;]+;base64,[^"]+)"'
    matches = list(re.finditer(pattern, html))
    print(f"[publish] 发现 {len(matches)} 张 base64 图片，开始上传...")

    all_success = True
    for i, m in enumerate(matches):
        data_uri = m.group(1)
        header, b64_data = data_uri.split(",", 1)
        ext = "png"
        if "jpeg" in header or "jpg" in header:
            ext = "jpg"
        elif "webp" in header:
            ext = "webp"
        image_data = base64.b64decode(b64_data)
        name = f"img_{i+1}.{ext}"
        print(f"[publish] 上传图片 {i+1}/{len(matches)}: {name} ({len(image_data)//1024}KB)")

        url = upload_to_imgbb(image_data, imgbb_api_key, imgbb_upload_url, name=name)
        if url:
            html = html.replace(data_uri, url, 1)
        else:
            print(f"[publish] ❌ 图片 {name} 上传失败，停止", file=sys.stderr)
            all_success = False
            return html, False

    return html, all_success


def copy_html_to_clipboard(html: str) -> bool:
    """
    将 HTML 写入剪贴板，粘贴到富文本编辑器时排版 100% 保留。
    macOS: 使用 Swift + AppKit（public.html 类型）
    Windows: 使用 PowerShell（Clipboard.SetText with HTML format）
    """
    import platform
    system = platform.system()

    if system == "Darwin":
        return _clipboard_macos(html)
    elif system == "Windows":
        return _clipboard_windows(html)
    else:
        print(f"[publish] ❌ 不支持的操作系统: {system}，请手动复制 HTML", file=sys.stderr)
        return False


def _clipboard_macos(html: str) -> bool:
    """macOS: Swift + AppKit 写入 public.html 类型。"""
    tmp_path = "/tmp/_wechat_publish_clipboard.html"
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(html)

    swift_code = f'''
import AppKit
let html = try! String(contentsOfFile: "{tmp_path}", encoding: .utf8)
let pb = NSPasteboard.general
pb.clearContents()
pb.setString(html, forType: .html)
pb.setString("文章内容已复制，请在公众号编辑器中 Cmd+V 粘贴", forType: .string)
'''

    try:
        result = subprocess.run(
            ["swift", "-e", swift_code],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            print("[publish] ✅ HTML 已复制到剪贴板（macOS public.html 格式）")
            return True
        else:
            print(f"[publish] ❌ 剪贴板写入失败: {result.stderr}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"[publish] ❌ Swift 执行失败: {e}", file=sys.stderr)
        return False
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def _clipboard_windows(html: str) -> bool:
    """Windows: PowerShell 写入 CF_HTML 格式剪贴板。"""
    # 写入临时文件避免命令行转义问题
    tmp_path = os.path.join(os.environ.get("TEMP", "C:\\Temp"), "_wechat_publish_clipboard.html")
    with open(tmp_path, "w", encoding="utf-8") as f:
        f.write(html)

    ps_script = f'''
$html = [System.IO.File]::ReadAllText("{tmp_path}", [System.Text.Encoding]::UTF8)
Add-Type -AssemblyName System.Windows.Forms
[System.Windows.Forms.Clipboard]::SetText($html, [System.Windows.Forms.TextDataFormat]::Html)
Write-Output "ok"
'''
    try:
        result = subprocess.run(
            ["powershell", "-NoProfile", "-Command", ps_script],
            capture_output=True, text=True, timeout=15
        )
        if result.returncode == 0 and "ok" in result.stdout:
            print("[publish] ✅ HTML 已复制到剪贴板（Windows CF_HTML 格式）")
            return True
        else:
            print(f"[publish] ❌ 剪贴板写入失败: {result.stderr}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"[publish] ❌ PowerShell 执行失败: {e}", file=sys.stderr)
        return False
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def open_wechat_editor():
    """打开公众号后台的图文编辑器页面。"""
    import webbrowser
    url = "https://mp.weixin.qq.com/"
    try:
        webbrowser.open(url)
        print(f"[publish] 🌐 已打开公众号后台: {url}")
        print("[publish] 📋 请在编辑器中新建图文 → Ctrl+V 粘贴内容")
    except Exception as e:
        print(f"[publish] ⚠️ 无法打开浏览器: {e}", file=sys.stderr)
        print(f"[publish] 请手动打开: {url}", file=sys.stderr)


def get_wechat_appid(api_base: str, api_key: str) -> str:
    """获取已绑定公众号的第一个 appid。"""
    url = f"{api_base}/wechat-accounts"
    body = json.dumps({}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            accounts = (data.get("data") or {}).get("accounts") or data.get("accounts") or []
            if accounts:
                appid = accounts[0].get("wechatAppid") or accounts[0].get("appid") or accounts[0].get("id", "")
                name = accounts[0].get("name", "")
                print(f"[publish] 公众号: 「{name}」appid: {appid}")
                return appid
            print(f"[publish] ⚠️ 未找到已绑定公众号，响应: {json.dumps(data)[:200]}", file=sys.stderr)
    except Exception as e:
        print(f"[publish] 获取公众号 appid 失败: {e}", file=sys.stderr)
    return ""


def publish_draft(api_base: str, api_key: str, appid: str, title: str, summary: str,
                  html_content: str, cover_url: str) -> str:
    """推送草稿，返回 publicationId。"""
    url = f"{api_base}/wechat-publish"
    payload = {
        "wechatAppid": appid,
        "title": title,
        "digest": summary,
        "content": html_content,
        "contentFormat": "html",
    }
    if cover_url:
        payload["thumb_media_url"] = cover_url
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "X-API-KEY": api_key,
            "Content-Type": "application/json",
        },
        method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            print(f"[publish] 发布响应: {json.dumps(data)[:300]}")
            pub_id = (data.get("data") or {}).get("id") or data.get("id") or data.get("media_id", "")
            return str(pub_id) if pub_id else "ok"
    except urllib.error.HTTPError as e:
        err = e.read().decode("utf-8")
        print(f"[publish] ❌ 发布 HTTP {e.code}: {err}", file=sys.stderr)
    except Exception as e:
        print(f"[publish] ❌ 发布失败: {e}", file=sys.stderr)
    return ""


def main():
    parser = argparse.ArgumentParser(description="推送公众号草稿箱")
    parser.add_argument("--html", required=True, help="排版后的 HTML 文件路径")
    parser.add_argument("--cover", required=True, help="封面图 PNG 路径")
    parser.add_argument("--title", required=True, help="文章标题")
    parser.add_argument("--summary", required=True, help="文章摘要")
    parser.add_argument("--slug", required=True, help="文章 slug（用于命名）")
    parser.add_argument("--api", action="store_true", help="使用 API 模式发布（排版会丢失）")
    args = parser.parse_args()

    html_file = Path(args.html)
    cover_file = Path(args.cover)

    if not html_file.exists():
        print(f"[publish] ❌ HTML 文件不存在: {html_file}", file=sys.stderr)
        sys.exit(1)
    if not cover_file.exists():
        print(f"[publish] ⚠️ 封面图不存在: {cover_file}，将不设置封面", file=sys.stderr)

    cfg = load_config()
    imgbb_key = get_cfg_value(cfg, "imgbb", "api_key", "IMGBB_API_KEY")
    imgbb_url = get_cfg_value(cfg, "imgbb", "upload_url", "IMGBB_UPLOAD_URL") or "https://api.imgbb.com/1/upload"

    if not imgbb_key:
        print("[publish] ❌ 缺少 ImgBB API Key，检查 config.yaml", file=sys.stderr)
        sys.exit(1)

    # 读取 HTML
    html_content = html_file.read_text(encoding="utf-8")

    # 替换 base64 图片为 ImgBB URL（两种模式都需要）
    html_content, ok = replace_base64_images(html_content, imgbb_key, imgbb_url)
    if not ok:
        sys.exit(1)

    if args.api:
        # ===== API 模式 =====
        wechat_base = get_cfg_value(cfg, "wechat_api", "api_base", "WECHAT_API_BASE") or "https://wx.limyai.com/api/openapi"
        wechat_key = get_cfg_value(cfg, "wechat_api", "api_key", "WECHAT_API_KEY")
        if not wechat_key:
            print("[publish] ❌ 缺少微信 API Key，检查 config.yaml", file=sys.stderr)
            sys.exit(1)

        # 上传封面图（可选）
        cover_url = ""
        if cover_file.exists():
            print(f"[publish] 上传封面图: {cover_file.name}")
            cover_data = cover_file.read_bytes()
            cover_url = upload_to_imgbb(cover_data, imgbb_key, imgbb_url, name=f"{args.slug}_cover.png")
            if not cover_url:
                print("[publish] ⚠️ 封面图上传失败，将不设置封面", file=sys.stderr)
        else:
            print("[publish] ⚠️ 无封面图，跳过封面上传")

        appid = get_wechat_appid(wechat_base, wechat_key)
        if not appid:
            print("[publish] ❌ 无法获取公众号 appid，停止", file=sys.stderr)
            sys.exit(1)

        print(f"[publish] 推送草稿：《{args.title}》")
        pub_id = publish_draft(wechat_base, wechat_key, appid, args.title, args.summary, html_content, cover_url)

        if pub_id:
            print(f"\n✅ 公众号文章已推送草稿箱（API模式，contentFormat=html）")
            print(f"   publicationId：{pub_id}")
            print(f"   查看路径：公众号后台 → 内容管理 → 草稿箱")
        else:
            print("\n❌ API 发布失败，自动回退到剪贴板模式...", file=sys.stderr)
            # 回退到剪贴板模式
            if copy_html_to_clipboard(html_content):
                open_wechat_editor()
            else:
                sys.exit(1)
    else:
        # ===== 剪贴板模式（默认，推荐） =====
        print(f"[publish] 使用剪贴板模式发布：《{args.title}》")

        if copy_html_to_clipboard(html_content):
            open_wechat_editor()
            print(f"\n✅ 发布准备完成")
            print(f"   📋 HTML 已复制到剪贴板（含排版 + 图片）")
            print(f"   🌐 公众号后台已打开")
            print(f"   👉 操作：新建图文 → Ctrl/Cmd+V 粘贴 → 设置标题封面 → 发布")
            print(f"")
            print(f"   标题：{args.title}")
            print(f"   摘要：{args.summary}")
            print(f"   封面：{cover_file}")
        else:
            print("\n❌ 剪贴板写入失败", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
