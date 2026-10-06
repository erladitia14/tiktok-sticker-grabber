/**
 * TikTok Sticker & Media Grabber - Content Script
 */

(function () {
  if (window.__TT_STICKER_GRABBER_INITIALIZED__) return;
  window.__TT_STICKER_GRABBER_INITIALIZED__ = true;

  // Store unique stickers: key = url -> { url, user, text, id, type }
  const capturedStickers = new Map();
  let isAutoScrolling = false;
  let autoScrollInterval = null;

  // Create Floating Action Button (FAB)
  const fab = document.createElement("div");
  fab.id = "tt-sticker-fab";
  fab.innerHTML = `
    <span>🎁 Stiker Komen</span>
    <span class="fab-badge" id="tt-fab-count">0</span>
  `;
  document.body.appendChild(fab);

  // Create Drawer Modal
  const modal = document.createElement("div");
  modal.id = "tt-sticker-modal";
  modal.innerHTML = `
    <div class="tt-modal-header">
      <h3>
        TikTok Sticker Grabber
        <span id="tt-modal-count">0 Ditemukan</span>
      </h3>
      <button class="tt-close-btn" id="tt-close-modal" title="Tutup">✕</button>
    </div>

    <div class="tt-actions-bar">
      <button class="tt-btn tt-btn-primary" id="tt-download-zip-btn">
        📦 Unduh Semua (.ZIP)
      </button>
      <button class="tt-btn tt-btn-secondary" id="tt-autoscroll-btn">
        📜 Auto Scroll Komen
      </button>
      <button class="tt-btn tt-btn-secondary" id="tt-clear-btn">
        🧹 Reset
      </button>
    </div>

    <div class="tt-gallery-container" id="tt-gallery">
      <div class="tt-gallery-empty" id="tt-empty-msg">
        <div style="font-size: 32px; margin-bottom: 8px;">🔍</div>
        Buka kolom komentar video TikTok.<br/>
        Stiker & media yang muncul akan otomatis kedeteksi di sini!
      </div>
    </div>

    <div class="tt-modal-footer">
      <span>Auto-detect via DOM & Network</span>
      <span id="tt-scroll-status" style="color: #25f4ee;"></span>
    </div>
  `;
  document.body.appendChild(modal);

  // Event Listeners for UI
  fab.addEventListener("click", () => {
    modal.classList.toggle("active");
    scanDOMForStickers();
  });

  document.getElementById("tt-close-modal").addEventListener("click", () => {
    modal.classList.remove("active");
  });

  document.getElementById("tt-download-zip-btn").addEventListener("click", downloadAllAsZip);
  document.getElementById("tt-autoscroll-btn").addEventListener("click", toggleAutoScroll);
  document.getElementById("tt-clear-btn").addEventListener("click", clearStickers);

  // Helper: check if element is inside an avatar container
  function isAvatar(img) {
    const parent = img.closest('[class*="Avatar"], [data-e2e*="avatar"], a[href^="/@"]');
    if (parent && !img.closest('p, [class*="CommentText"], [class*="comment-text"]')) {
      return true;
    }
    const width = img.naturalWidth || img.width || 0;
    const height = img.naturalHeight || img.height || 0;
    if (width > 0 && width <= 48 && height > 0 && height <= 48) {
      if (img.className.toLowerCase().includes("avatar")) return true;
    }
    return false;
  }

  // Scan comments in DOM for stickers & image attachments
  function scanDOMForStickers() {
    // Select potential comment containers
    const commentNodes = document.querySelectorAll(
      '[data-e2e="comment-item"], [class*="DivCommentItemContainer"], [class*="CommentItem"], [class*="DivCommentContentContainer"]'
    );

    commentNodes.forEach((node) => {
      // Find commenter username
      const userEl = node.querySelector('[data-e2e*="comment-username"], a[href*="/@"] span, [class*="SpanUserName"]');
      const user = userEl ? userEl.innerText.trim().replace(/^@/, "") : "user";

      // Find comment text
      const textEl = node.querySelector('p[data-e2e*="comment-level"], [class*="PCommentText"], p');
      const text = textEl ? textEl.innerText.trim() : "";

      // Find images within this comment node
      const imgs = node.querySelectorAll("img");
      imgs.forEach((img) => {
        const src = img.src;
        if (!src || !src.startsWith("http")) return;

        // Skip user profile avatars
        if (isAvatar(img)) return;

        // Check if image belongs to TikTok CDN or GIF providers
        const isLikelyMedia =
          src.includes("tiktokcdn") ||
          src.includes("byteimg") ||
          src.includes("giphy.com") ||
          src.includes("tenor.com") ||
          src.includes("tos-");

        if (isLikelyMedia) {
          addSticker(src, user, text);
        }
      });
    });

    // Also scan any standalone media container in comment section
    const standaloneImgs = document.querySelectorAll(
      '[data-e2e="search-comment-container"] img, [class*="DivCommentListContainer"] img'
    );
    standaloneImgs.forEach((img) => {
      const src = img.src;
      if (!src || !src.startsWith("http") || isAvatar(img)) return;
      if (src.includes("tiktokcdn") || src.includes("byteimg") || src.includes("giphy.com") || src.includes("tenor.com")) {
        addSticker(src, "tiktok_user", "");
      }
    });
  }

  function getFileExtension(url) {
    if (url.includes(".gif")) return "gif";
    if (url.includes(".png")) return "png";
    if (url.includes(".webp") || url.includes("tplv-tiktokx-origin") || url.includes("tos-")) return "webp";
    if (url.includes(".jpg") || url.includes(".jpeg")) return "jpg";
    return "webp";
  }

  function addSticker(url, user, text) {
    // Deduplicate by clean base URL without temporary sign tokens if possible, or exact URL
    const cleanUrl = url.split("?")[0];
    if (capturedStickers.has(cleanUrl) || capturedStickers.has(url)) return;

    const ext = getFileExtension(url);
    const stickerData = {
      id: "stk_" + (capturedStickers.size + 1),
      url: url,
      cleanUrl: cleanUrl,
      user: user || "unknown",
      text: text || "",
      ext: ext,
      date: new Date().toLocaleTimeString()
    };

    capturedStickers.set(cleanUrl, stickerData);
    updateUI();
  }

  function updateUI() {
    const count = capturedStickers.size;
    const badge = document.getElementById("tt-fab-count");
    const modalCount = document.getElementById("tt-modal-count");
    if (badge) badge.innerText = count;
    if (modalCount) modalCount.innerText = `${count} Ditemukan`;

    const gallery = document.getElementById("tt-gallery");
    const emptyMsg = document.getElementById("tt-empty-msg");

    if (count > 0 && emptyMsg) {
      emptyMsg.style.display = "none";
    }

    // Render cards that aren't rendered yet
    capturedStickers.forEach((stk) => {
      if (document.getElementById(`card-${stk.id}`)) return;

      const card = document.createElement("div");
      card.className = "tt-card";
      card.id = `card-${stk.id}`;
      card.innerHTML = `
        <div class="tt-card-img-wrap">
          <img src="${stk.url}" alt="${stk.user}" loading="lazy" />
        </div>
        <div class="tt-card-meta">
          <div class="tt-card-user">@${stk.user}</div>
          <div class="tt-card-comment" title="${stk.text}">${stk.text || "<i>Sticker / Reaction</i>"}</div>
          <div class="tt-card-actions">
            <button class="tt-btn tt-btn-primary tt-btn-xs btn-download-single" data-id="${stk.id}">
              Unduh .${stk.ext}
            </button>
            <a href="${stk.url}" target="_blank" class="tt-btn tt-btn-secondary tt-btn-xs" style="text-decoration:none;">
              Lihat
            </a>
          </div>
        </div>
      `;

      card.querySelector(".btn-download-single").addEventListener("click", () => {
        downloadSingle(stk);
      });

      gallery.appendChild(card);
    });
  }

  function downloadSingle(stk) {
    fetch(stk.url)
      .then((res) => res.blob())
      .then((blob) => {
        const a = document.createElement("a");
        const blobUrl = URL.createObjectURL(blob);
        a.href = blobUrl;
        a.download = `tiktok_sticker_${stk.user}_${stk.id}.${stk.ext}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        URL.revokeObjectURL(blobUrl);
      })
      .catch((err) => {
        console.error("Gagal download stiker:", err);
        window.open(stk.url, "_blank");
      });
  }

  async function downloadAllAsZip() {
    if (capturedStickers.size === 0) {
      alert("Belum ada stiker yang ditemukan. Buka komentar dulu!");
      return;
    }

    if (typeof JSZip === "undefined") {
      alert("JSZip library belum siap.");
      return;
    }

    const btn = document.getElementById("tt-download-zip-btn");
    const originalText = btn.innerHTML;
    btn.innerHTML = `⏳ Mengompres (0/${capturedStickers.size})...`;
    btn.classList.add("loading");

    try {
      const zip = new JSZip();
      const folder = zip.folder("tiktok_stickers");
      let index = 1;

      for (const [_, stk] of capturedStickers) {
        try {
          const res = await fetch(stk.url);
          const blob = await res.blob();
          const filename = `${String(index).padStart(2, "0")}_${stk.user}_${stk.id}.${stk.ext}`;
          folder.file(filename, blob);
          btn.innerHTML = `⏳ Mengompres (${index}/${capturedStickers.size})...`;
          index++;
        } catch (e) {
          console.warn("Gagal fetch stiker:", stk.url, e);
        }
      }

      btn.innerHTML = "💾 Membuat file ZIP...";
      const content = await zip.generateAsync({ type: "blob" });
      const a = document.createElement("a");
      const url = URL.createObjectURL(content);
      a.href = url;
      a.download = `tiktok_stickers_${Date.now()}.zip`;
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(url);
    } catch (err) {
      console.error("Error creating zip:", err);
      alert("Gagal membuat zip: " + err.message);
    } finally {
      btn.innerHTML = originalText;
      btn.classList.remove("loading");
    }
  }

  function toggleAutoScroll() {
    const btn = document.getElementById("tt-autoscroll-btn");
    const status = document.getElementById("tt-scroll-status");

    if (isAutoScrolling) {
      clearInterval(autoScrollInterval);
      isAutoScrolling = false;
      btn.innerHTML = "📜 Auto Scroll Komen";
      btn.classList.remove("tt-btn-primary");
      btn.classList.add("tt-btn-secondary");
      status.innerText = "";
    } else {
      isAutoScrolling = true;
      btn.innerHTML = "⏹ Berhenti Scroll";
      btn.classList.add("tt-btn-primary");
      btn.classList.remove("tt-btn-secondary");
      status.innerText = "⚡ Sedang auto-scroll komentar...";

      autoScrollInterval = setInterval(() => {
        // Find comment scroll container or window
        const scrollContainer = document.querySelector(
          '[class*="DivCommentListContainer"], [class*="DivCommentContainer"], [data-e2e="search-comment-container"]'
        );

        if (scrollContainer) {
          scrollContainer.scrollTop += 600;
        } else {
          window.scrollBy(0, 500);
        }

        // Scan after scrolling
        scanDOMForStickers();
      }, 1200);
    }
  }

  function clearStickers() {
    capturedStickers.clear();
    const gallery = document.getElementById("tt-gallery");
    gallery.innerHTML = `
      <div class="tt-gallery-empty" id="tt-empty-msg">
        <div style="font-size: 32px; margin-bottom: 8px;">🔍</div>
        Buka kolom komentar video TikTok.<br/>
        Stiker & media yang muncul akan otomatis kedeteksi di sini!
      </div>
    `;
    updateUI();
  }

  // MutationObserver to auto-detect stickers in real time as user scrolls naturally
  const observer = new MutationObserver(() => {
    scanDOMForStickers();
  });

  observer.observe(document.body, {
    childList: true,
    subtree: true
  });

  // Initial scan
  setTimeout(scanDOMForStickers, 1500);
})();
