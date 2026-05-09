#!/usr/bin/env node
/**
 * convert.js — 公众号精排版风格
 *
 * 微信渲染器硬约束：
 *   - 无 <style> 标签
 *   - 无 <div> 标签（用 <section>）
 *   - 无 linear-gradient
 *   - 图片必须 base64 data URI
 */

const fs = require("fs");
const path = require("path");

const args = process.argv.slice(2);
function getArg(name) {
  const idx = args.indexOf(name);
  return idx !== -1 ? args[idx + 1] : null;
}

const inputFile = getArg("--input");
const outputFile = getArg("--output");
const imagesDir = getArg("--images-dir") || path.dirname(inputFile || ".");

if (!inputFile || !outputFile) {
  console.error("用法: node convert.js --input <md> --output <html> [--images-dir <dir>]");
  process.exit(1);
}

const mdContent = fs.readFileSync(inputFile, "utf-8");

// ── 颜色常量（配色方案）──────────────────────────────────────────────────────
const C = {
  deepBlue: "#1a1a2e",       // 主背景深蓝（header、引用块）
  orange: "#e76f51",          // 强调橙色（PART标签、左边框、代码文字）
  lightPink: "#f5d0c5",      // 章节编号淡粉色
  highlightYellow: "rgb(255,243,176)",  // 高亮文字黄底
  codeBg: "rgb(243,244,246)", // 代码/术语灰底
  textMain: "#333333",        // 正文主色
  textDark: "#1a1a2e",        // 标题深色
  textLight: "#999999",       // 辅助说明文字
  white: "#ffffff",
};

// ── 样式常量 ─────────────────────────────────────────────────────────────────
const S = {
  // Header 区（深蓝底、白字、居中）
  header: `background-color:${C.deepBlue};color:${C.white};padding:56px 24px 44px;text-align:center`,
  headerTitle: `font-size:26px;font-weight:bold;line-height:1.5;color:${C.white};margin-bottom:12px;letter-spacing:1px`,
  headerSub: `font-size:14px;color:${C.textLight};margin-bottom:0;letter-spacing:0.5px`,

  // 正文容器
  body: `max-width:100%;padding:24px 20px 48px;margin:0 auto`,

  // 正文段落（核心样式）
  p: `margin-bottom:18px;text-align:justify;font-size:16px;color:${C.textMain};line-height:2`,

  // 章节标题三层结构
  sectionWrap: `margin-top:48px;margin-bottom:24px`,
  sectionNum: `font-size:36px;font-weight:bold;color:${C.lightPink};letter-spacing:2px;line-height:1;margin:0`,
  sectionPart: `font-size:11px;font-weight:bold;color:${C.orange};letter-spacing:4px;margin:0`,
  sectionTitle: `font-size:20px;font-weight:bold;color:${C.textDark};line-height:1.4;margin:0`,

  // 高亮文字（黄底加粗）
  highlight: `background-color:${C.highlightYellow};padding:2px 4px;font-weight:bold;color:${C.textDark}`,

  // 代码/术语标签
  code: `background-color:${C.codeBg};color:${C.orange};padding:2px 6px;border-radius:3px;font-size:14px;font-family:monospace`,

  // 代码块
  pre: `background-color:${C.codeBg};padding:16px 20px;border-radius:8px;overflow-x:auto;font-size:13px;line-height:1.7;margin:20px 0;font-family:monospace;color:${C.textMain}`,

  // 引用/高亮块（深蓝底、白字、左橙边框）
  quoteBlock: `background-color:${C.deepBlue};color:${C.white};padding:24px 20px;border-radius:8px;margin:28px 0;font-size:16px;line-height:1.9;border-left:4px solid ${C.orange}`,
  quoteText: `margin:0;color:${C.white}`,
  quoteAuthor: `margin:8px 0 0;color:${C.textLight};font-size:14px`,

  // 问题块（浅色版引用）
  questionBlock: `background-color:rgb(240,248,255);padding:24px 20px;border-radius:8px;margin:28px 0;font-size:16px;line-height:1.9;border-left:4px solid #2a9d8f`,

  // 引用行 ▎ text
  quoteLine: `border-left:3px solid #e0e0e0;padding:10px 16px;margin:20px 0;color:#888;font-size:15px;line-height:1.8`,

  // 图片
  imgWrap: `margin:28px 0;text-align:center`,
  img: `max-width:100%;height:auto;border-radius:6px`,

  // 粗体强调链接
  boldLink: `color:${C.orange};font-weight:bold;border-bottom:2px solid ${C.orange};padding-bottom:1px`,
  link: `color:${C.orange};text-decoration:none`,

  // 分割线
  hr: `border:none;height:1px;background:#eee;margin:32px auto;width:40%`,

  // 列表
  ul: `padding-left:20px;margin:16px 0`,
  ol: `padding-left:20px;margin:16px 0`,
  li: `margin:8px 0;line-height:1.9;font-size:16px;color:${C.textMain}`,

  // 尾部签名
  footer: `margin-top:48px;padding-top:20px;text-align:center;font-size:14px;color:${C.textLight};line-height:2`,
};

// ── 解析 frontmatter ──────────────────────────────────────────────────────────
function parseFrontmatter(md) {
  const match = md.match(/^---\n([\s\S]*?)\n---\n([\s\S]*)$/);
  if (!match) return { meta: {}, body: md };
  const meta = {};
  match[1].split("\n").forEach(line => {
    const [k, ...vParts] = line.split(":");
    if (k) meta[k.trim()] = vParts.join(":").trim().replace(/^["']|["']$/g, "");
  });
  return { meta, body: match[2] };
}

// ── Markdown → HTML ──────────────────────────────────────────────────────────
function mdToHtml(md, title) {
  let html = md;
  let sectionCounter = 0;

  // 代码块
  html = html.replace(/```[\w]*\n([\s\S]*?)```/g, (_, code) => {
    const escaped = code.replace(/</g, "&lt;").replace(/>/g, "&gt;");
    return `<pre style="${S.pre}"><code>${escaped}</code></pre>`;
  });

  // 行内代码
  html = html.replace(/`([^`]+)`/g, `<span style="${S.code}">$1</span>`);

  // H2 标题 → 章节编号结构（01 PART 标题）
  html = html.replace(/^#{2}\s+(.+)$/gm, (_, text) => {
    sectionCounter++;
    const num = String(sectionCounter).padStart(2, "0");
    return `<section style="${S.sectionWrap}">` +
      `<p style="${S.sectionNum}">${num}</p>` +
      `<p style="${S.sectionPart}">PART</p>` +
      `<p style="${S.sectionTitle}">${text}</p>` +
      `</section>`;
  });

  // H3 标题
  html = html.replace(/^#{3}\s+(.+)$/gm,
    `<p style="font-size:18px;font-weight:bold;margin:32px 0 12px;color:${C.textDark}">$1</p>`);

  // H4 标题
  html = html.replace(/^#{4}\s+(.+)$/gm,
    `<p style="font-size:16px;font-weight:bold;margin:24px 0 10px;color:${C.textMain}">$1</p>`);

  // 高亮块 :::highlight ... :::（深蓝底引用风格）
  html = html.replace(/:::highlight\n([\s\S]*?):::/g, (_, content) => {
    return `<section style="${S.quoteBlock}"><p style="${S.quoteText}">${content.trim()}</p></section>`;
  });

  // 问题块 :::question ... :::
  html = html.replace(/:::question\n([\s\S]*?):::/g, (_, content) => {
    return `<section style="${S.questionBlock}"><p style="margin:0">${content.trim()}</p></section>`;
  });

  // 引用行 ▎ text
  html = html.replace(/^▎\s+(.+)$/gm,
    `<section style="${S.quoteBlock}"><p style="${S.quoteText}">$1</p></section>`);

  // ==高亮== → 黄底加粗
  html = html.replace(/==([^=]+)==/g, `<span style="${S.highlight}">$1</span>`);

  // 粗体/斜体
  html = html.replace(/\*\*\*([^*]+)\*\*\*/g, '<strong><em>$1</em></strong>');
  html = html.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
  html = html.replace(/\*([^*]+)\*/g, '<em>$1</em>');

  // 图片占位符
  html = html.replace(/!\[([^\]]*)\]\(([^)]+\.png)\)/g, (_, alt, src) => {
    return `__IMG_PLACEHOLDER__${src}__ALT__${alt}__END_IMG__`;
  });

  // 链接
  html = html.replace(/\[([^\]]+)\]\(([^)]+)\)/g, `<a href="$2" style="${S.link}">$1</a>`);

  // 分割线
  html = html.replace(/^---+$/gm, `<hr style="${S.hr}">`);

  // 无序列表
  html = html.replace(/((?:^[ \t]*[-*+]\s+.+\n?)+)/gm, (block) => {
    const items = block.trim().split(/\n/).map(line => {
      const text = line.replace(/^[ \t]*[-*+]\s+/, "");
      return `<li style="${S.li}">${text}</li>`;
    }).join("\n");
    return `<ul style="${S.ul}">${items}</ul>\n`;
  });

  // 有序列表
  html = html.replace(/((?:^\d+\.\s+.+\n?)+)/gm, (block) => {
    const items = block.trim().split(/\n/).map(line => {
      const text = line.replace(/^\d+\.\s+/, "");
      return `<li style="${S.li}">${text}</li>`;
    }).join("\n");
    return `<ol style="${S.ol}">${items}</ol>\n`;
  });

  // 段落处理
  const blocks = html.split(/\n\n+/);
  html = blocks.map(block => {
    block = block.trim();
    if (!block) return "";
    if (/^<[^>]+>|^__IMG_PLACEHOLDER__|^<pre|^<ul|^<ol|^<section|^<hr|^<p /.test(block)) {
      return block;
    }
    return `<p style="${S.p}">${block}</p>`;
  }).join("\n\n");

  return html;
}

// ── 图片 base64 内嵌 ──────────────────────────────────────────────────────────
function embedImages(html, imagesDir) {
  return html.replace(/__IMG_PLACEHOLDER__(.*?)__ALT__(.*?)__END_IMG__/g, (_, src, alt) => {
    const imgPath = path.resolve(imagesDir, src);
    if (!fs.existsSync(imgPath)) {
      console.warn(`[convert.js] 图片未找到，跳过: ${imgPath}`);
      return `<p style="color:#ccc;font-style:italic;text-align:center;margin:24px 0">[图：${alt || src}]</p>`;
    }
    const ext = path.extname(src).toLowerCase().replace(".", "") || "png";
    const mimeType = ext === "jpg" ? "image/jpeg" : `image/${ext}`;
    const b64 = fs.readFileSync(imgPath).toString("base64");
    return `<section style="${S.imgWrap}">` +
      `<img src="data:${mimeType};base64,${b64}" style="${S.img}">` +
      `</section>`;
  });
}

// ── 校验 ──────────────────────────────────────────────────────────────────────
function validateHtml(html) {
  const errors = [];
  if (/<style[\s>]/i.test(html)) errors.push("<style> 标签存在");
  if (/linear-gradient/i.test(html)) errors.push("linear-gradient 存在");
  if (/<div[\s>]/i.test(html)) errors.push("<div> 标签存在");
  const imgSrcs = [...html.matchAll(/<img[^>]+src=["']([^"']+)["']/gi)].map(m => m[1]);
  const nonBase64 = imgSrcs.filter(s => !s.startsWith("data:"));
  if (nonBase64.length > 0) errors.push(`图片非 base64: ${nonBase64.join(", ")}`);
  return errors;
}

// ── 主流程 ────────────────────────────────────────────────────────────────────
const { meta, body } = parseFrontmatter(mdContent);
const title = meta.title || "无标题";
const subtitle = meta.subtitle || "";

// 构建 header（深蓝底白字标题区）
const headerHtml = `<section style="${S.header}">` +
  `<p style="${S.headerTitle}">${title}</p>` +
  (subtitle ? `<p style="${S.headerSub}">${subtitle}</p>` : "") +
  `</section>`;

// 构建正文
let articleHtml = mdToHtml(body, title);
articleHtml = embedImages(articleHtml, imagesDir);

// 组装完整 HTML
const fullHtml = `${headerHtml}\n<section style="${S.body}">\n${articleHtml}\n</section>`;

// 校验
const errors = validateHtml(fullHtml);
if (errors.length > 0) {
  console.error("[convert.js] HTML 校验失败：");
  errors.forEach(e => console.error("  ❌ " + e));
  process.exit(1);
}

fs.mkdirSync(path.dirname(outputFile), { recursive: true });
fs.writeFileSync(outputFile, fullHtml, "utf-8");

const sizeKB = (fs.statSync(outputFile).size / 1024).toFixed(1);
console.log(`[convert.js] ✅ HTML 已生成: ${outputFile} (${sizeKB} KB)`);
