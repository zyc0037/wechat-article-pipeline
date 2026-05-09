# 微信公众号文章生成器

Markdown 一键生成精排版公众号图文，自动 AI 配图，支持直接推送到草稿箱。

## 流程

```
Markdown → AI 配图 → 精排版 HTML → 公众号草稿箱
```

## 前置条件

- Python 3.9+
- Node.js 16+
- 三个 API Key（见下方配置）

## 配置

复制 `config.yaml` 并填入你的 API Key：

```yaml
image_api:
  api_key: "你的图片生成 API Key"  # 豆包
  base_url: https://ark.cn-beijing.volces.com/api/v3  # 豆包默认
  model: <模型接入点名称(ep-xxx)>

imgbb:
  api_key: "你的 ImgBB API Key"    # https://api.imgbb.com/

wechat_api:
  api_key: "你的 limyai API Key"   # https://wx.limyai.com
```

## 使用

### 1. 准备 Markdown

```markdown
---
title: "文章标题"
subtitle: "文：作者名"
---

正文内容...

![图注描述](slug_img1_keyword.png)

更多内容...
```

### 2. 生成排版 HTML

```bash
python3 scripts/run_pipeline.py \
  --input article.md \
  --output outputs/wechat \
  --filename slug_article.html
```

可选参数：
- `--style warm-flat` — 指定图片风格（不传则自动检测）

| 风格 | 适用场景 |
|------|---------|
| `warm-flat` | 教程、个人成长、AI 实战 |
| `dark-tech` | AI/技术深度、商业分析 |
| `cool-editorial` | 系统设计、方法论、数据分析 |
| `sketch-warm` | 个人故事、认知变化、情感 |

### 3. 发布到公众号

```bash
# API 模式（推荐）
python3 scripts/publish_to_wechat.py --api \
  --html outputs/wechat/slug_article.html \
  --cover outputs/wechat/images/slug_img1_keyword.png \
  --title "文章标题" \
  --summary "文章摘要" \
  --slug "slug"

# 剪贴板模式（不加 --api）
python3 scripts/publish_to_wechat.py \
  --html outputs/wechat/slug_article.html \
  --cover outputs/wechat/images/slug_img1_keyword.png \
  --title "文章标题" \
  --summary "文章摘要" \
  --slug "slug"
```

## 注意事项

- 剪贴板模式仅支持 macOS 和 Windows，Linux 用户请使用 `--api` 模式
- 图片生成需要时间，3 张图约 1-2 分钟
- 已生成的图片不会重复生成，如需重新生成先删除 `images/` 下对应文件
- 封面图建议用文章中的第一张配图
- Markdown 中 `==文字==` 会渲染为黄底高亮
- 支持代码块、引用块、有序/无序列表等标准 Markdown 语法
