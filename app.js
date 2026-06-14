const fileInput = document.querySelector("#fileInput");
const dropZone = document.querySelector("#dropZone");
const imageList = document.querySelector("#imageList");
const exportBtn = document.querySelector("#exportBtn");
const clearBtn = document.querySelector("#clearBtn");
const summary = document.querySelector("#summary");
const quality = document.querySelector("#quality");
const qualityValue = document.querySelector("#qualityValue");
const pageSize = document.querySelector("#pageSize");
const maxEdge = document.querySelector("#maxEdge");
const fileName = document.querySelector("#fileName");
const template = document.querySelector("#imageCardTemplate");

const images = [];
let draggedId = null;

fileInput.addEventListener("change", (event) => addFiles(event.target.files));

["dragenter", "dragover"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.add("is-over");
  });
});

["dragleave", "drop"].forEach((eventName) => {
  dropZone.addEventListener(eventName, (event) => {
    event.preventDefault();
    dropZone.classList.remove("is-over");
  });
});

dropZone.addEventListener("drop", (event) => addFiles(event.dataTransfer.files));
quality.addEventListener("input", () => {
  qualityValue.textContent = `${Math.round(Number(quality.value) * 100)}%`;
});
clearBtn.addEventListener("click", clearImages);
exportBtn.addEventListener("click", exportPdf);

async function addFiles(fileList) {
  const files = Array.from(fileList).filter((file) => file.type.startsWith("image/"));
  const loaded = await Promise.all(files.map(loadImageFile));
  images.push(...loaded);
  fileInput.value = "";
  render();
}

function loadImageFile(file) {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(file);
    const img = new Image();

    img.onload = () => {
      resolve({
        id: crypto.randomUUID(),
        file,
        url,
        width: img.naturalWidth,
        height: img.naturalHeight,
      });
    };
    img.onerror = () => {
      URL.revokeObjectURL(url);
      reject(new Error(`无法读取图片：${file.name}`));
    };
    img.src = url;
  });
}

function render() {
  imageList.replaceChildren();

  images.forEach((item) => {
    const card = template.content.firstElementChild.cloneNode(true);
    const preview = card.querySelector("img");
    const title = card.querySelector("strong");
    const meta = card.querySelector("span");

    card.dataset.id = item.id;
    preview.src = item.url;
    preview.alt = item.file.name;
    title.textContent = item.file.name;
    meta.textContent = `${item.width} x ${item.height}px · ${formatBytes(item.file.size)}`;

    card.querySelector(".move-up").addEventListener("click", () => moveImage(item.id, -1));
    card.querySelector(".move-down").addEventListener("click", () => moveImage(item.id, 1));
    card.querySelector(".remove").addEventListener("click", () => removeImage(item.id));

    card.addEventListener("dragstart", () => {
      draggedId = item.id;
      card.classList.add("dragging");
    });
    card.addEventListener("dragend", () => {
      draggedId = null;
      card.classList.remove("dragging");
    });
    card.addEventListener("dragover", (event) => {
      event.preventDefault();
      reorderByDrag(item.id);
    });

    imageList.append(card);
  });

  const totalSize = images.reduce((sum, item) => sum + item.file.size, 0);
  summary.textContent = images.length
    ? `${images.length} 张截图 · 原始大小 ${formatBytes(totalSize)}`
    : "还没有选择截图";
  exportBtn.disabled = images.length === 0;
  clearBtn.disabled = images.length === 0;
}

function moveImage(id, offset) {
  const from = images.findIndex((item) => item.id === id);
  const to = from + offset;
  if (from < 0 || to < 0 || to >= images.length) return;
  const [item] = images.splice(from, 1);
  images.splice(to, 0, item);
  render();
}

function reorderByDrag(targetId) {
  if (!draggedId || draggedId === targetId) return;
  const from = images.findIndex((item) => item.id === draggedId);
  const to = images.findIndex((item) => item.id === targetId);
  if (from < 0 || to < 0) return;
  const [item] = images.splice(from, 1);
  images.splice(to, 0, item);
  render();
}

function removeImage(id) {
  const index = images.findIndex((item) => item.id === id);
  if (index < 0) return;
  URL.revokeObjectURL(images[index].url);
  images.splice(index, 1);
  render();
}

function clearImages() {
  images.forEach((item) => URL.revokeObjectURL(item.url));
  images.length = 0;
  render();
}

async function exportPdf() {
  if (!images.length) return;
  if (!window.jspdf?.jsPDF) {
    alert("PDF 库还没有加载完成，请检查网络后刷新页面。");
    return;
  }

  exportBtn.disabled = true;
  exportBtn.textContent = "生成中...";

  try {
    const { jsPDF } = window.jspdf;
    let doc = null;

    for (const [index, item] of images.entries()) {
      const compressed = await imageToJpeg(item, Number(quality.value));
      const page = getPageSize(item);
      const orientation = page.width > page.height ? "landscape" : "portrait";

      if (!doc) {
        doc = new jsPDF({ unit: "pt", format: [page.width, page.height], orientation });
      } else {
        doc.addPage([page.width, page.height], orientation);
      }

      const fit = contain(item.width, item.height, page.width, page.height);
      doc.addImage(compressed, "JPEG", fit.x, fit.y, fit.width, fit.height, undefined, "FAST");

      exportBtn.textContent = `生成中 ${index + 1}/${images.length}`;
      await waitForFrame();
    }

    doc.save(normalizePdfName(fileName.value));
  } catch (error) {
    console.error(error);
    alert(error.message || "生成 PDF 时出错。");
  } finally {
    exportBtn.textContent = "生成 PDF";
    exportBtn.disabled = images.length === 0;
  }
}

function imageToJpeg(item, jpegQuality) {
  return new Promise((resolve, reject) => {
    const img = new Image();
    img.onload = () => {
      const limit = Number(maxEdge.value);
      const scale = limit > 0 ? Math.min(1, limit / Math.max(item.width, item.height)) : 1;
      const canvas = document.createElement("canvas");
      canvas.width = Math.round(item.width * scale);
      canvas.height = Math.round(item.height * scale);
      const ctx = canvas.getContext("2d", { alpha: false });
      ctx.fillStyle = "#ffffff";
      ctx.fillRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      resolve(canvas.toDataURL("image/jpeg", jpegQuality));
    };
    img.onerror = () => reject(new Error(`压缩失败：${item.file.name}`));
    img.src = item.url;
  });
}

function getPageSize(item) {
  if (pageSize.value === "a4") return { width: 595.28, height: 841.89 };
  if (pageSize.value === "letter") return { width: 612, height: 792 };
  return pxToPoints(item.width, item.height);
}

function pxToPoints(width, height) {
  const maxSide = 1600;
  const scale = Math.min(1, maxSide / Math.max(width, height));
  return {
    width: Math.max(120, width * scale * 0.75),
    height: Math.max(120, height * scale * 0.75),
  };
}

function contain(sourceWidth, sourceHeight, targetWidth, targetHeight) {
  const ratio = Math.min(targetWidth / sourceWidth, targetHeight / sourceHeight);
  const width = sourceWidth * ratio;
  const height = sourceHeight * ratio;
  return {
    x: (targetWidth - width) / 2,
    y: (targetHeight - height) / 2,
    width,
    height,
  };
}

function formatBytes(bytes) {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const power = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  return `${(bytes / 1024 ** power).toFixed(power ? 1 : 0)} ${units[power]}`;
}

function normalizePdfName(value) {
  const trimmed = value.trim() || "ipad-screenshots.pdf";
  return trimmed.toLowerCase().endsWith(".pdf") ? trimmed : `${trimmed}.pdf`;
}

function waitForFrame() {
  return new Promise((resolve) => requestAnimationFrame(resolve));
}
