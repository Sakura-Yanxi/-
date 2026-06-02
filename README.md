# Sakura — Gemini 增强工具

一个用于 [Gemini](https://gemini.google.com/) / AI Studio 页面的 Chrome 扩展（Manifest V3），提供两个功能：

1. **可视化放大** — 检测 Gemini 生成的可视化 iframe，在右上角加「🔍 放大」按钮，点击后让 iframe 进入浏览器原生全屏（保留完整交互，ESC 退出）。*仅 Gemini / AI Studio。*
2. **划词翻译** — 选中英文文本弹窗翻译：单个单词显示音标 + 词性 + 释义；词组 / 句子显示整段中文。*支持 Gemini、AI Studio、DeepSeek、通义千问、豆包。*

纯前端实现，无构建步骤，无第三方依赖。

## 安装

> 未上架 Chrome 网上应用店，需以开发者模式手动加载。

1. 下载本仓库（`git clone` 或下载 ZIP 解压）
2. 打开 `chrome://extensions/`
3. 开启右上角「开发者模式」
4. 点「加载已解压的扩展程序」→ 选择本文件夹
5. 打开 Gemini 页面即可使用

改代码后，在扩展页点刷新 🔄，再刷新 Gemini 页面。

## 文件

| 文件 | 作用 |
| --- | --- |
| `manifest.json` | 扩展配置（MV3） |
| `background.js` | service worker：划词翻译的词典 API 请求 |
| `content.js` / `content.css` | 检测可视化 iframe、注入放大按钮、全屏 |
| `translation.js` / `translation.css` | 划词翻译弹窗（仅渲染，网络请求走 background） |
| `icons/` | 扩展图标 |

## 两点设计说明

**为什么用原生全屏放大，而不是把 iframe 内容提取出来？**
Gemini 的可视化在跨域安全沙箱 iframe（`scf.usercontent.goog`）里，受同源策略限制无法读取内部 HTML，搬运/克隆到别处会因 origin 校验而空白。`requestFullscreen()` 不移动节点、不重新加载，浏览器把全屏元素提升到 top layer，自动绕过页面的 stacking context，是唯一能保留交互的放大方式。

**为什么划词翻译走 background？**
Gemini 页面有严格 CSP，content script 里直接 `fetch` 外部接口会被拦截。所以请求通过 `chrome.runtime.sendMessage` 交给 `background.js`（service worker 不受页面 CSP 限制）发起，结果回传渲染。

按选中内容分流，每条链取第一个成功的源（均带 6 秒超时，连不上自动跳过）：

- **单个单词** → 有道词典（中文释义）→ Free Dictionary（英文释义）
- **词组 / 句子** → MyMemory → 有道 fanyi → Google 翻译

> Google 端点国内多半连不上，故排在末位靠超时跳过；MyMemory 免费且国内可达，是句子翻译的主力。

## 说明

- 翻译使用有道、Free Dictionary、MyMemory、Google 等公开接口，仅供个人学习使用；这些接口非官方授权，可能随时变更或失效。
- 可视化放大仅在 Gemini / AI Studio 生效（依赖其特有的沙箱 iframe）；划词翻译额外支持 DeepSeek、通义千问、豆包。
- 扩展不收集、不上传任何用户数据，所有网络请求只用于翻译查询。

## License

[MIT](LICENSE) © Sakura
