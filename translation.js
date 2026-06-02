// 划词翻译：选中英文文本，在后台查询词典/翻译并弹窗显示

let popup = null;

// 词性英文转缩写
const POS_MAP = {
  noun: 'n.', verb: 'v.', adjective: 'adj.', adverb: 'adv.',
  pronoun: 'pron.', preposition: 'prep.', conjunction: 'conj.',
  interjection: 'int.', determiner: 'det.'
};

function createPopup() {
  if (popup) return popup;
  popup = document.createElement('div');
  popup.className = 'gemini-translation-popup';
  popup.innerHTML = `
    <div class="translation-header">
      <span class="translation-word"></span>
      <button class="translation-close">×</button>
    </div>
    <div class="translation-content"></div>
  `;
  document.body.appendChild(popup);
  popup.querySelector('.translation-close').addEventListener('click', (e) => {
    e.stopPropagation();
    hidePopup();
  });
  return popup;
}

function showPopup(text, x, y) {
  const el = createPopup();
  el.querySelector('.translation-word').textContent = text;
  el.querySelector('.translation-content').innerHTML =
    '<div class="translation-loading">翻译中...</div>';

  el.style.display = 'flex';
  el.style.left = `${x}px`;
  el.style.top = `${y + 10}px`;

  // 避免超出屏幕
  requestAnimationFrame(() => {
    const r = el.getBoundingClientRect();
    if (r.right > window.innerWidth) el.style.left = `${window.innerWidth - r.width - 10}px`;
    if (r.bottom > window.innerHeight) el.style.top = `${y - r.height - 10}px`;
  });

  // 后台查询（绕过页面 CSP）
  chrome.runtime.sendMessage({ action: 'translate', word: text }, (data) => {
    const content = el.querySelector('.translation-content');
    if (chrome.runtime.lastError) {
      content.innerHTML = '<div class="translation-error">连接后台失败，请重试</div>';
      return;
    }
    content.innerHTML = render(data);
  });
}

function hidePopup() {
  if (popup) popup.style.display = 'none';
}

// 渲染翻译结果
function render(data) {
  if (!data) return '<div class="translation-error">未找到翻译</div>';

  let html = '';

  if (data.source === 'youdao') {
    if (data.usphone || data.ukphone) {
      html += '<div class="translation-phonetic">';
      if (data.usphone) html += `<span>美 [${data.usphone}]</span> `;
      if (data.ukphone) html += `<span>英 [${data.ukphone}]</span>`;
      html += '</div>';
    }
    html += '<div class="translation-meanings">';
    for (const item of data.trs) {
      const { pos, meaning } = splitPos(item);
      html += `<div class="translation-meaning"><span class="pos-tag">${pos}</span>${meaning}</div>`;
    }
    html += '</div>';
  } else if (data.source === 'freedict') {
    if (data.phonetic) {
      html += `<div class="translation-phonetic"><span>${data.phonetic}</span></div>`;
    }
    html += '<div class="translation-meanings">';
    for (const m of data.meanings) {
      const pos = POS_MAP[m.pos?.toLowerCase()] || m.pos;
      for (const def of m.definitions) {
        const short = def.length > 50 ? def.slice(0, 50) + '...' : def;
        html += `<div class="translation-meaning"><span class="pos-tag">${pos}</span>${short}</div>`;
      }
    }
    html += '</div>';
  } else if (data.source === 'phrase') {
    // 词组/句子：整段译文
    html += `<div class="translation-meanings"><div class="translation-meaning">${data.text}</div></div>`;
  }

  return html || '<div class="translation-error">未找到翻译</div>';
}

// 从有道释义中分离词性缩写
function splitPos(text) {
  const m = text.match(/^(n\.|v\.|adj\.|adv\.|prep\.|conj\.|pron\.|int\.|vi\.|vt\.|aux\.)\s*/);
  if (m) return { pos: m[1], meaning: text.slice(m[0].length).trim() };
  return { pos: '', meaning: text };
}

// 判断是否为「需要翻译的英文」：含字母、不含中文、长度合理
function isEnglishSelection(text) {
  if (!text || text.length > 200) return false;
  if (/[一-鿿]/.test(text)) return false; // 含中文则不翻译
  return /[a-zA-Z]/.test(text);
}

// 选中英文时触发
document.addEventListener('mouseup', (e) => {
  if (popup && popup.contains(e.target)) return;

  setTimeout(() => {
    const text = window.getSelection().toString().trim();
    if (isEnglishSelection(text)) {
      const r = window.getSelection().getRangeAt(0).getBoundingClientRect();
      showPopup(text, r.left + r.width / 2, r.bottom + window.scrollY);
    } else if (popup) {
      hidePopup();
    }
  }, 10);
});

document.addEventListener('scroll', hidePopup, true);
