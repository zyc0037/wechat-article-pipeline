---
name: yc-wechat-article-generator
description: "Markdown 文章一键生成精排版公众号图文并发布到草稿箱。自动生成 AI 配图、精排版、上传图床、推送微信公众号草稿箱。"
version: 1.0.0
author: yicong
---

# 微信公众号文章生成器

Markdown → AI配图 → 精排版HTML → 发布到公众号草稿箱。全自动，一条命令搞定。

## 触发词

「发公众号」「生成公众号文章」「公众号排版」「wechat article」「微信文章」

## 前置条件

用户需要在 `config.yaml` 中填写三个 API Key：
1. **图片生成 API Key** — 用于 AI 生成配图（豆包/火山引擎）
2. **ImgBB API Key** — 用于图片托管（微信不支持 base64）
3. **limyai API Key** — 用于推送到公众号草稿箱

## 完整流程

### 第一步：准备 Markdown

将用户的文章转成带 frontmatter 和图片占位符的 Markdown 文件。

**frontmatter 格式：**
```yaml
---
title: "文章标题"
subtitle: "副标题（可选）"
---
```

**图片占位符格式：**
```
![图注描述](slug_img1_keyword.png)
```
- `slug`：文章英文缩写
- `img1`：第几张图
- `keyword`：图片核心关键词（英文）
- 图注描述写中文，AI 会自动翻译成英文 prompt

**示例：**
```markdown
---
title: "脱单是个技术问题"
subtitle: "文：yicong"
---

感情这件事，第一层是概率问题。

![一个人站在人群中寻找方向](tuodan_img1_crowd.png)

你觉得那些情场顺利的人是因为长得帅？
```

一般放 2-4 张图，分布在文章的 1/3、2/3 和结尾处。

### 第二步：运行 Pipeline

```bash
python3 scripts/run_pipeline.py \
  --input article.md \
  --output outputs/wechat \
  --filename slug_article.html
```

**可选参数：**
- `--style warm-flat` — 指定图片风格（不传则根据文章内容自动检测）

**4 种预设风格：**
| 风格 | 适用场景 |
|------|---------|
| `warm-flat` | 教程、个人成长、AI实战（默认） |
| `dark-tech` | AI/技术深度、商业分析 |
| `cool-editorial` | 系统设计、方法论、数据分析 |
| `sketch-warm` | 个人故事、认知变化、情感 |

Pipeline 会自动：
1. 扫描 Markdown 中的图片占位符
2. 根据文章内容自动选择最匹配的风格（如果没指定 --style）
3. 用豆包逐张生成配图
4. 用精排版配色方案渲染 HTML（深蓝 header + 橙色强调）
5. 在浏览器中打开预览

### 第三步：发布到公众号

```bash
python3 scripts/publish_to_wechat.py --api \
  --html outputs/wechat/slug_article.html \
  --cover outputs/wechat/images/slug_img1_keyword.png \
  --title "文章标题" \
  --summary "文章摘要（显示在消息列表）" \
  --slug "slug"
```

**两种发布模式：**
- `--api`（推荐）：通过 limyai API 直接推送到草稿箱，排版完整保留
- 不加 `--api`：复制 HTML 到剪贴板，手动粘贴到公众号编辑器

## 注意事项

- 剪贴板模式仅支持 macOS 和 Windows，Linux 用户请使用 `--api` 模式
- 图片生成需要时间，3 张图大约 1-2 分钟
- 已生成的图片不会重复生成（按文件名跳过），如需重新生成先删除 images/ 目录下对应文件
- 封面图建议用文章中的第一张配图
- Markdown 中的 `==文字==` 会渲染为黄底高亮
- 支持代码块、引用块、有序/无序列表等标准 Markdown 语法
