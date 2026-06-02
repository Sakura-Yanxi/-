// 后台 service worker：划词翻译的网络请求
// content script 受 Gemini 页面 CSP 限制无法直接 fetch，故请求统一在此发起

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === 'translate') {
    fetchTranslation(request.word)
      .then((result) => sendResponse(result))
      .catch(() => sendResponse(null));
    return true; // 异步响应，保持通道开放
  }
});

// 入口：单个单词查词典，词组 / 句子走整段翻译
async function fetchTranslation(input) {
  const text = input.trim();
  const isSingleWord = /^[a-zA-Z]+(?:[-'][a-zA-Z]+)*$/.test(text);

  if (!isSingleWord) return translatePhrase(text);

  let result = await lookupWord(text);

  // 连字符词查不到时回退到末段词根（over-invest → invest）
  if (!result && text.includes('-')) {
    const root = text.split('-').pop();
    if (root && root !== text) result = await lookupWord(root);
  }

  // 词典都查不到，退回整段翻译
  return result || translatePhrase(text);
}

// 带超时的 fetch + JSON，避免连不上的端点无限挂起
async function fetchJSON(url, ms = 6000) {
  const ctrl = new AbortController();
  const timer = setTimeout(() => ctrl.abort(), ms);
  try {
    const res = await fetch(url, { signal: ctrl.signal });
    return res.ok ? await res.json() : null;
  } catch {
    return null;
  } finally {
    clearTimeout(timer);
  }
}

// 单词：有道（中文释义）→ Free Dictionary（英文释义）
async function lookupWord(word) {
  const q = encodeURIComponent(word);

  const yd = await fetchJSON(`https://dict.youdao.com/jsonapi?q=${q}`);
  const w = yd?.ec?.word?.[0];
  if (w) {
    return {
      source: 'youdao',
      usphone: w.usphone || '',
      ukphone: w.ukphone || '',
      trs: (w.trs || []).map((tr) => tr.tr[0].l.i[0]),
    };
  }

  const fd = await fetchJSON(`https://api.dictionaryapi.dev/api/v2/entries/en/${q}`);
  const entry = fd?.[0];
  if (entry) {
    return {
      source: 'freedict',
      phonetic: entry.phonetic || '',
      meanings: (entry.meanings || []).map((m) => ({
        pos: m.partOfSpeech,
        definitions: (m.definitions || []).slice(0, 2).map((d) => d.definition),
      })),
    };
  }

  return null;
}

// 词组 / 句子整段翻译：依次尝试多个源，取第一个成功的
async function translatePhrase(text) {
  const q = encodeURIComponent(text);

  const sources = [
    // Google 端点（质量最好，国内连不上则靠超时跳过）
    async () => {
      const d = await fetchJSON(
        `https://translate.googleapis.com/translate_a/single?client=gtx&sl=en&tl=zh-CN&dt=t&q=${q}`
      );
      return (d?.[0] || []).map((seg) => seg[0]).join('');
    },

    // MyMemory：免费、国内可达；限流时会把英文警告塞进译文，需过滤
    async () => {
      const d = await fetchJSON(
        `https://api.mymemory.translated.net/get?q=${q}&langpair=en|zh-CN`
      );
      if (d?.responseStatus !== 200) return null;
      const tran = d?.responseData?.translatedText || '';
      // 限流警告 / 原文回显（不含中文）一律视为失败
      if (/MYMEMORY WARNING|QUERY LENGTH LIMIT|INVALID/i.test(tran)) return null;
      if (!/[一-龥]/.test(tran)) return null;
      return tran;
    },

    // 有道词典 fanyi 字段兜底
    async () => (await fetchJSON(
      `https://dict.youdao.com/jsonapi?q=${q}`
    ))?.fanyi?.tran,
  ];

  for (const get of sources) {
    const tran = await get();
    if (tran) return { source: 'phrase', text: tran };
  }

  return null;
}
