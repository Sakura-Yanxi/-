// 内容脚本 - 检测 Gemini 的可视化 iframe，注入「放大」按钮

// 已处理过的 iframe（用元素本身标记，避免尺寸变化导致重复）
const tagged = new WeakSet();

// 找到值得放大的 iframe：sandbox 沙箱 iframe 或 srcdoc，且足够大
function findVizFrames() {
  const frames = [...document.querySelectorAll('iframe[sandbox], iframe[srcdoc]')];
  return frames.filter((f) => {
    const r = f.getBoundingClientRect();
    return r.width > 200 && r.height > 150;
  });
}

// 给一个 iframe 注入放大按钮（放在其父元素里，跟随 iframe 位置）
function addButton(iframe) {
  if (tagged.has(iframe)) return;

  const parent = iframe.parentElement;
  if (!parent) return;
  tagged.add(iframe);

  // 补上全屏权限（改属性不会触发 reload）
  const sandbox = iframe.getAttribute('sandbox');
  if (sandbox && !sandbox.includes('allow-fullscreen')) {
    iframe.setAttribute('sandbox', sandbox + ' allow-fullscreen');
  }
  iframe.setAttribute('allowfullscreen', 'true');
  iframe.classList.add('gemini-viz-enhancer-target');

  // 确保父元素能作为定位上下文
  const pos = getComputedStyle(parent).position;
  if (pos === 'static') parent.style.position = 'relative';

  const btn = document.createElement('button');
  btn.className = 'gemini-viz-enhancer-btn';
  btn.textContent = '🔍 放大';
  btn.addEventListener('click', (e) => {
    e.preventDefault();
    e.stopPropagation();
    zoomIframe(iframe);
  });

  parent.appendChild(btn);
}

// 放大：让 iframe 进入浏览器原生全屏
// 不移动节点、不克隆 → 不 reload、不丢握手状态、自动绕过 stacking context
function zoomIframe(iframe) {
  const req = iframe.requestFullscreen
    || iframe.webkitRequestFullscreen
    || iframe.mozRequestFullScreen;

  if (!req) {
    alert('当前浏览器不支持全屏');
    return;
  }

  req.call(iframe).catch((err) => {
    console.error('全屏失败:', err);
    alert('无法全屏显示：' + err.message);
  });
}

// 扫描并注入
function scan() {
  findVizFrames().forEach(addButton);
}

// 初始多次扫描（内容加载有延迟）
[1000, 2500, 5000].forEach((t) => setTimeout(scan, t));

// 持续监听 DOM 变化
const observer = new MutationObserver(() => scan());
observer.observe(document.body, { childList: true, subtree: true });

