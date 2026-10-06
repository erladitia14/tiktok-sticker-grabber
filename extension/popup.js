document.getElementById("open-tiktok-btn").addEventListener("click", () => {
  chrome.tabs.create({ url: "https://www.tiktok.com" });
});
