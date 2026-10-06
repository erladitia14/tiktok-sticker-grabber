// TikTok Sticker Grabber - Production Mobile Frontend Logic

let currentStickers = [];
let selectedStickerIds = new Set();

async function pasteFromClipboard() {
  const urlInput = document.getElementById("tiktok-url");
  try {
    if (navigator.clipboard && navigator.clipboard.readText) {
      const text = await navigator.clipboard.readText();
      if (text) {
        urlInput.value = text.trim();
        urlInput.focus();
      }
    } else {
      urlInput.focus();
      urlInput.select();
    }
  } catch (err) {
    urlInput.focus();
  }
}

function openAuthModal() {
  document.getElementById("auth-modal").style.display = "flex";
}

function closeAuthModal() {
  document.getElementById("auth-modal").style.display = "none";
}

async function saveImportedCookies() {
  const textarea = document.getElementById("cookie-input");
  const val = textarea.value.trim();
  if (!val) {
    alert("Masukkan data JSON cookies terlebih dahulu.");
    return;
  }

  try {
    const res = await fetch("/api/auth/import", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cookies_json: val })
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || "Gagal simpan cookies.");

    alert("Berhasil! " + data.message);
    window.location.reload();
  } catch (err) {
    alert("Error: " + err.message);
  }
}

async function logoutSession() {
  if (!confirm("Hapus sesi TikTok dari server?")) return;
  try {
    const res = await fetch("/api/auth/logout", { method: "DELETE" });
    if (res.ok) {
      alert("Sesi dihapus.");
      window.location.reload();
    }
  } catch (err) {
    alert("Error: " + err.message);
  }
}

async function startExtraction() {
  const urlInput = document.getElementById("tiktok-url");
  const url = urlInput.value.trim();
  const scrolls = parseInt(document.getElementById("opt-scrolls").value, 10);

  if (!url) {
    alert("Tempel URL video TikTok terlebih dahulu!");
    urlInput.focus();
    return;
  }

  const btn = document.getElementById("btn-extract");
  const btnText = document.getElementById("btn-text");
  const spinner = document.getElementById("btn-spinner");
  const statusCard = document.getElementById("status-card");
  const resultsHeader = document.getElementById("results-header");
  const galleryGrid = document.getElementById("gallery-grid");
  const mobileBar = document.getElementById("mobile-sticky-bar");

  btn.disabled = true;
  btnText.innerText = "Memproses...";
  spinner.style.display = "inline-block";

  statusCard.style.display = "block";
  document.getElementById("status-icon").innerText = "⚡";
  document.getElementById("status-title").innerText = "Sedang membaca komentar secara headless...";
  document.getElementById("status-desc").innerText = "Browser server sedang membuka video dan menyaring semua stiker. Mohon tunggu beberapa detik...";

  resultsHeader.style.display = "none";
  galleryGrid.style.display = "none";
  mobileBar.style.display = "none";
  galleryGrid.innerHTML = "";
  currentStickers = [];
  selectedStickerIds.clear();

  try {
    const res = await fetch("/api/extract", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, scrolls })
    });

    if (!res.ok) {
      throw new Error(await responseErrorMessage(res, "Gagal memproses video."));
    }

    const data = await res.json();
    currentStickers = data.stickers || [];
    renderGallery(currentStickers, data.diagnostics);
  } catch (err) {
    statusCard.style.display = "block";
    document.getElementById("status-icon").innerText = "⚠️";
    document.getElementById("status-title").innerText = "Gagal Mengambil Stiker";
    document.getElementById("status-desc").innerText = err.message + " (Tips: Pastikan URL publik dan buka kolom komentar dapat diakses).";
  } finally {
    btn.disabled = false;
    btnText.innerText = "Tarik Stiker";
    spinner.style.display = "none";
  }
}

function responseErrorMessage(response, fallback) {
  return response.json()
    .then(data => {
      if (typeof data === "string" && data.trim()) return data;
      const detail = data && (data.detail || data.error || data.message);
      return typeof detail === "string" && detail.trim() ? detail : fallback;
    })
    .catch(() => response.statusText ? `${fallback} (${response.status}: ${response.statusText})` : fallback);
}

function renderGallery(stickers, diagnostics = {}) {
  const statusCard = document.getElementById("status-card");
  const resultsHeader = document.getElementById("results-header");
  const galleryGrid = document.getElementById("gallery-grid");
  const mobileBar = document.getElementById("mobile-sticky-bar");
  const countEl = document.getElementById("result-count");

  diagnostics = diagnostics && typeof diagnostics === "object" ? diagnostics : {};
  const payloadCount = Number.isFinite(diagnostics.comment_payloads) ? diagnostics.comment_payloads : null;
  const commentsSeen = Number.isFinite(diagnostics.comments_seen) ? diagnostics.comments_seen : null;

  countEl.innerText = stickers.length;

  if (stickers.length === 0) {
    statusCard.style.display = "block";
    const title = document.getElementById("status-title");
    const description = document.getElementById("status-desc");

    if (payloadCount === 0) {
      document.getElementById("status-icon").innerText = "⚠️";
      title.innerText = "Komentar TikTok gagal terbaca";
      description.innerText = "Tidak ada data komentar yang diterima. Coba link lain, pastikan komentar publik, atau login sesi TikTok.";
    } else if (payloadCount > 0 && commentsSeen === 0) {
      document.getElementById("status-icon").innerText = "📭";
      title.innerText = "Tidak Ada Komentar Ditemukan";
      description.innerText = "TikTok mengirim data komentar, tetapi tidak ada komentar di dalamnya. Pastikan komentar video tersedia dan publik.";
    } else if (payloadCount > 0 && commentsSeen > 0) {
      document.getElementById("status-icon").innerText = "📭";
      title.innerText = "Tidak Ada Stiker / Reaksi Ditemukan";
      description.innerText = `Terbaca ${commentsSeen} komentar, tetapi tidak ada media yang cocok. Pastikan video memiliki stiker/GIF/foto di komentar.`;
    } else {
      document.getElementById("status-icon").innerText = "📭";
      title.innerText = "Tidak Ada Stiker / Reaksi Ditemukan";
      description.innerText = "Ekstraksi selesai tanpa hasil. Pastikan video memiliki komentar publik yang memuat stiker/GIF/foto.";
    }

    resultsHeader.style.display = "none";
    galleryGrid.style.display = "none";
    mobileBar.style.display = "none";
    return;
  }

  statusCard.style.display = "none";
  resultsHeader.style.display = "flex";
  galleryGrid.style.display = "grid";
  mobileBar.style.display = "flex";
  galleryGrid.innerHTML = "";

  selectedStickerIds = new Set(stickers.map(s => s.id));

  stickers.forEach((item) => {
    const card = document.createElement("div");
    card.className = "card-item selected";
    card.id = `card-${item.id}`;

    // Use proxy image or direct
    const imgSrc = `/api/proxy-img?url=${encodeURIComponent(item.url)}`;

    card.innerHTML = `
      <div class="card-check-wrap">
        <input type="checkbox" id="check-${item.id}" checked onchange="toggleItemSelect('${item.id}')" />
      </div>
      <div class="card-thumb">
        <img src="${imgSrc}" alt="${item.user}" loading="lazy" />
      </div>
      <div class="card-info">
        <div class="card-user">@${item.user}</div>
        <div class="card-comment" title="${item.text}">${item.text || "<i>Stiker</i>"}</div>
        <div class="card-actions">
          <button class="btn btn-primary btn-sm" onclick="downloadSingle('${item.url}', '${item.user}', '${item.id}', '${item.ext}')">
            Simpan
          </button>
          <a href="${item.url}" target="_blank" class="btn btn-secondary btn-sm">
            Lihat
          </a>
        </div>
      </div>
    `;

    galleryGrid.appendChild(card);
  });

  updateSelectedCount();
}

function toggleItemSelect(id) {
  const card = document.getElementById(`card-${id}`);
  const checkbox = document.getElementById(`check-${id}`);

  if (checkbox.checked) {
    selectedStickerIds.add(id);
    card.classList.add("selected");
  } else {
    selectedStickerIds.delete(id);
    card.classList.remove("selected");
  }

  updateSelectedCount();
}

function selectAll(state) {
  currentStickers.forEach((s) => {
    const checkbox = document.getElementById(`check-${s.id}`);
    const card = document.getElementById(`card-${s.id}`);
    if (checkbox) checkbox.checked = state;
    if (card) {
      if (state) card.classList.add("selected");
      else card.classList.remove("selected");
    }
    if (state) selectedStickerIds.add(s.id);
    else selectedStickerIds.delete(s.id);
  });
  updateSelectedCount();
}

function updateSelectedCount() {
  const topBtn = document.getElementById("btn-download-top");
  const mobBtn = document.getElementById("btn-download-mobile");
  const mobCount = document.getElementById("mobile-selected-count");

  const count = selectedStickerIds.size;
  if (topBtn) topBtn.innerText = `📦 Unduh .ZIP (${count})`;
  if (mobBtn) mobBtn.innerText = `📦 Unduh (${count}) .ZIP`;
  if (mobCount) mobCount.innerText = count;

  if (topBtn) topBtn.disabled = count === 0;
  if (mobBtn) mobBtn.disabled = count === 0;
}

function downloadSingle(url, user, id, ext) {
  const proxyUrl = `/api/proxy-img?url=${encodeURIComponent(url)}`;
  fetch(proxyUrl)
    .then(async response => {
      if (!response.ok) throw new Error(await responseErrorMessage(response, "CDN gagal mengirim gambar."));
      return response.blob();
    })
    .then(blob => {
      const a = document.createElement("a");
      const objUrl = URL.createObjectURL(blob);
      a.href = objUrl;
      a.download = `tiktok_sticker_${user}_${id}.${ext || 'webp'}`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      setTimeout(() => URL.revokeObjectURL(objUrl), 1000);
    })
    .catch(err => {
      alert("Gagal mengunduh gambar: " + err.message);
    });
}

async function downloadSelectedZip() {
  const selectedItems = currentStickers.filter(s => selectedStickerIds.has(s.id));
  if (selectedItems.length === 0) {
    alert("Pilih minimal satu stiker untuk diunduh.");
    return;
  }

  const topBtn = document.getElementById("btn-download-top");
  const mobBtn = document.getElementById("btn-download-mobile");
  if (topBtn) topBtn.disabled = true;
  if (mobBtn) mobBtn.disabled = true;

  try {
    const res = await fetch("/api/download-zip", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items: selectedItems })
    });

    if (!res.ok) throw new Error(await responseErrorMessage(res, "Gagal mengunduh file ZIP."));

    const succeeded = Number(res.headers.get("X-Download-Succeeded") || selectedItems.length);
    const failed = Number(res.headers.get("X-Download-Failed") || 0);
    const blob = await res.blob();
    const a = document.createElement("a");
    const blobUrl = URL.createObjectURL(blob);
    a.href = blobUrl;
    a.download = `tiktok_stickers_${Date.now()}.zip`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    setTimeout(() => URL.revokeObjectURL(blobUrl), 1000);
    if (failed > 0) alert(`ZIP diunduh dengan ${succeeded} file berhasil dan ${failed} file gagal.`);

  } catch (err) {
    alert("Gagal download ZIP: " + err.message);
  } finally {
    updateSelectedCount();
  }
}
