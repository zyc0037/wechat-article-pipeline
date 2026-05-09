# yc-wechat-article

Markdown 写完，一条命令发到公众号草稿箱。AI 配图、精排版、上传图床、推送，全自动。

## 前置准备

三个 key，都免费，10 分钟拿齐。

### 01 图片生成：豆包方舟 API Key

用来让 AI 给文章画配图。

1. 打开 [火山引擎方舟控制台](https://console.volcengine.com/ark)
2. 注册/登录
3. 创建 API Key，复制

拿到的东西：

- API Key
- 模型接入点名称（格式 `ep-xxx`，创建推理接入点时会生成）

### 02 图床：ImgBB API Key

公众号 API 不接受本地图片，必须是在线链接。ImgBB 免费帮你把图片传上去拿 URL。单张最大 32MB，够用。

1. 打开 [imgbb.com](https://imgbb.com) 注册
2. 打开 [api.imgbb.com](https://api.imgbb.com)（注意是另一个地址）
3. 点「Get API key」，复制

拿到的东西：

- API Key
- 上传地址：`https://api.imgbb.com/1/upload`（不用改）

### 03 公众号发布：limyai API Key

微信官方接入流程极复杂——开放平台基础接入就要两三周，还要服务器、域名、备案。用第三方省事，单公众号免费。

1. 打开 [limyai](https://wx.limyai.com) 注册
2. 登录后台
3. 「公众号管理」→「添加公众号」→ 扫码绑定
4. 「开放平台」→「创建密钥」→ 复制

拿到的东西：

- API Key
- API 地址：`https://wx.limyai.com/api/openapi`（不用改）

## 配置

打开 `config.yaml`，三个 key 填进去：

```yaml
image_api:
  api_key: "你的豆包 API Key"
  base_url: https://ark.cn-beijing.volces.com/api/v3
  model: <模型接入点名称(ep-xxx)>

imgbb:
  api_key: "你的 ImgBB API Key"

wechat_api:
  api_key: "你的 limyai API Key"
```

其他的不用动。模型、图片风格、上传地址都配好了。

## 项目结构

```
yc-wechat-article/
├── SKILL.md              ← Claude Code 读这个知道怎么用
├── config.yaml           ← 三个 key 填这里
└── scripts/
    ├── run_pipeline.py       ← 总控：扫描文章 → 生图 → 排版
    ├── image_generator.py    ← 调豆包画图
    ├── convert.js            ← Markdown → 公众号排版 HTML
    └── publish_to_wechat.py  ← 上传到草稿箱
```

## 使用

### 用法 1：Markdown 写完直接发

跟 Claude Code 说「发公众号」，给它 Markdown 文件路径。它自动：

1. 扫描文章里的图片占位符
2. 根据内容自动选配图风格
3. 逐张生成配图
4. 做成公众号排版 HTML
5. 传到草稿箱

### 用法 2：从想法开始

1. 用「思考模式」提示词把模糊想法理清楚
2. 用「发布模式」提示词让 AI 写成完整文章
3. 输出 Markdown 后喊「发公众号」，Skill 接管

## 四种配图风格


| 风格               | 适用场景              |
| ---------------- | ----------------- |
| `warm-flat`      | 教程、个人成长、AI 实战（默认） |
| `dark-tech`      | AI/技术深度、商业分析      |
| `cool-editorial` | 系统设计、方法论、数据分析     |
| `sketch-warm`    | 个人故事、认知变化、情感      |


自动匹配逻辑：扫描文章关键词。AI、代码、技术多的走 `dark-tech`，感情、成长、故事多的走 `sketch-warm`。选不对就手动指定。

## Markdown 格式

```markdown
---
title: "文章标题"
subtitle: "文：作者名"
---

正文内容...

![图注描述](slug_img1_keyword.png)

更多内容...
```

- `slug`：文章英文缩写
- `img1`：第几张图
- `keyword`：图片核心关键词（英文）
- 图注写中文，AI 自动翻译成英文 prompt
- 一般放 2-4 张，分布在 1/3、2/3、结尾处

## 注意事项

- 3 张图大约 1-2 分钟，别急
- 已生成的图不会重复生成，想重来先删 `images/` 下对应文件
- 封面图建议用第一张配图
- `==文字==` 渲染为黄底高亮
- 支持代码块、引用块、列表等标准 Markdown 语法
- HTML 校验会自动拦截 `<style>`、`linear-gradient`、`<div>`——这些微信不支持，发出去会出问题
- 图片过图床是因为公众号 API 对 HTML 体积有限制，base64 的 2-5MB 直接提交会报错

## 为什么不能跳过总控直接跑 convert.js

图片生成是异步的，返回成功不代表文件写进磁盘。`run_pipeline.py` 内部做了文件验证——等文件真正存在且大小 > 0 才继续。直接跑 `convert.js`，图全是裂的。
