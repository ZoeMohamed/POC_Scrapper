const $ = (id) => document.getElementById(id);

function setStatus(message, type = "") {
  const status = $("status");
  status.textContent = message;
  status.className = `status ${type}`.trim();
}

function backendOrigin(value) {
  const url = new URL(value);
  if (!["http:", "https:"].includes(url.protocol)) throw new Error("URL backend tidak valid.");
  return url.origin;
}

async function loadProducts() {
  const backend = backendOrigin($("backend-url").value);
  const response = await fetch(`${backend}/api/products`, { headers: { Accept: "application/json" } });
  if (!response.ok) throw new Error(`Backend menjawab ${response.status}.`);
  const products = await response.json();
  const select = $("product-id");
  select.replaceChildren(...products.map((product) => {
    const option = document.createElement("option");
    option.value = product.id;
    option.textContent = product.name;
    return option;
  }));
  if (!products.length) throw new Error("Belum ada produk di config/products.json.");
}

async function restoreSettings() {
  const saved = await chrome.storage.local.get(["backendUrl", "ingestToken", "productId"]);
  if (saved.backendUrl) $("backend-url").value = saved.backendUrl;
  if (saved.ingestToken) $("ingest-token").value = saved.ingestToken;
  await loadProducts();
  if (saved.productId && [...$("product-id").options].some((item) => item.value === saved.productId)) {
    $("product-id").value = saved.productId;
  }
}

async function capture(event) {
  event.preventDefault();
  const button = $("capture-button");
  button.disabled = true;
  setStatus("Membaca ulasan yang sudah tampil…");

  try {
    const backendUrl = backendOrigin($("backend-url").value);
    const ingestToken = $("ingest-token").value.trim();
    const productId = $("product-id").value;
    if (!productId) throw new Error("Pilih produk dashboard terlebih dahulu.");

    await chrome.storage.local.set({ backendUrl, ingestToken, productId });
    const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
    if (!tab?.id) throw new Error("Tab aktif tidak ditemukan.");
    await chrome.scripting.executeScript({ target: { tabId: tab.id }, files: ["content.js"] });
    const captured = await chrome.tabs.sendMessage(tab.id, { type: "UMKM_CAPTURE_REVIEWS" });
    if (!captured?.ok) throw new Error(captured?.error || "Halaman tidak dapat dibaca.");
    if (!captured.reviews.length) {
      throw new Error("Ulasan belum terdeteksi. Gulir ke bagian ulasan, tampilkan beberapa kartu, lalu coba lagi.");
    }

    setStatus(`${captured.reviews.length} ulasan ditemukan. Mengirim ke dashboard…`);
    const headers = { "Content-Type": "application/json", Accept: "application/json" };
    if (ingestToken) headers["X-Ingest-Token"] = ingestToken;
    const response = await fetch(`${backendUrl}/api/ingest/marketplace`, {
      method: "POST",
      headers,
      body: JSON.stringify({
        marketplace: captured.marketplace,
        product_id: productId,
        product_url: captured.product_url,
        reviews: captured.reviews,
      }),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail || `Backend menjawab ${response.status}.`);
    setStatus(
      `${result.accepted} ulasan baru masuk live feed; ${result.duplicates} duplikat dilewati.`,
      "success"
    );
  } catch (error) {
    setStatus(error.message || "Gagal menangkap ulasan.", "error");
  } finally {
    button.disabled = false;
  }
}

$("capture-form").addEventListener("submit", capture);
$("backend-url").addEventListener("change", () => {
  loadProducts().catch((error) => setStatus(error.message, "error"));
});
restoreSettings().catch((error) => setStatus(
  `Backend belum terhubung. Jalankan aplikasi lalu coba lagi. ${error.message}`,
  "error"
));
