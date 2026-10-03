(() => {
  if (globalThis.__umkmReviewBridgeLoaded) return;
  globalThis.__umkmReviewBridgeLoaded = true;

  const normalize = (value) => String(value || "").replace(/\s+/g, " ").trim();
  const isVisible = (node) => Boolean(node && node.getClientRects().length);
  const directText = (node) => normalize(
    [...(node?.childNodes || [])]
      .filter((child) => child.nodeType === Node.TEXT_NODE)
      .map((child) => child.textContent)
      .join(" ")
  );
  const nonReviewPatterns = [
    /^(membantu|\d+\s+orang terbantu|lihat balasan)$/i,
    /^(lebih dari\s+)?\d+\s+(hari|minggu|bulan|tahun)\s+lalu$/i,
    /^beritahu pengguna lain mengapa anda(?:\s+sangat)?\s+menyukai produk ini/i,
    /^(ulasan|rating|foto|video|filter|urutkan)$/i,
  ];
  const isReviewText = (text) => (
    text.length >= 8
    && /[a-z]{2}/i.test(text)
    && !nonReviewPatterns.some((pattern) => pattern.test(text))
  );

  function marketplaceFromHost(hostname) {
    const host = hostname.toLowerCase();
    if (host === "tokopedia.com" || host.endsWith(".tokopedia.com")) return "tokopedia";
    if (host === "shopee.co.id" || host.endsWith(".shopee.co.id")) return "shopee";
    if (["tiktok.com", "tiktokshop.com", "tiktokglobalshop.com"].some(
      (domain) => host === domain || host.endsWith(`.${domain}`)
    )) return "tiktokshop";
    throw new Error("Halaman ini bukan halaman Tokopedia, Shopee, atau TikTok Shop.");
  }

  const selectors = {
    tokopedia: {
      cards: [
        "[data-testid='review-card']",
        "[data-testid='comment-review-card']",
        "article[data-testid*='review' i]",
        "[data-testid*='ReviewCard']",
        "[class*='css-1k1a7gr']",
        "article[class*='review' i]",
      ],
      text: [
        "[data-testid='review-content']",
        "[data-testid='comment-review']",
        "[data-testid*='reviewContent' i]",
        "[data-testid*='review-content' i]",
        "p",
      ],
    },
    shopee: {
      cards: [
        "[data-testid='product-rating']",
        ".shopee-product-rating__list-item",
        ".product-ratings__list > *",
        "[class*='ratings__list'] > *",
        "[class*='product-rating'] [class*='item']",
        "[class*='rating__list'] > div",
        "div.product-rating",
        "[class*='product-rating']",
        "[class*='ProductRating']",
      ],
      text: [
        "[data-testid='review-content']",
        ".shopee-product-rating__content",
        ".Zmy311",
        "[class*='karmaj5']",
        "[class*='review-content' i]",
        "[class*='comment' i]",
        "[class*='content' i]",
        "p",
      ],
    },
    tiktokshop: {
      cards: [
        "[data-e2e='product-review-item']",
        "[data-e2e*='review-item' i]",
        "[data-testid*='review-item' i]",
        "[class*='ReviewItem']",
        "[class*='review-item' i]",
        "li[class*='review' i]",
      ],
      text: [
        "[data-e2e='review-content']",
        "[data-e2e*='review-content' i]",
        "[data-testid*='review-content' i]",
        "[class*='ReviewContent']",
        "[class*='review-content' i]",
        "p",
      ],
    },
  };

  function firstWorkingSelector(candidates) {
    for (const selector of candidates) {
      const nodes = [...document.querySelectorAll(selector)].filter(isVisible);
      if (nodes.length) return nodes;
    }
    return [];
  }

  function heuristicReviewCards() {
    const helperPattern = /^(membantu|\d+\s+orang terbantu)$/i;
    const datePattern = /(?:\d+\s+(?:hari|minggu|bulan|tahun)\s+lalu|lebih dari\s+\d+\s+tahun lalu)/i;
    const anchors = [...document.querySelectorAll("button, span, div")]
      .filter(isVisible)
      .filter((node) => helperPattern.test(directText(node)));
    const cards = [];
    const seen = new Set();

    for (const anchor of anchors) {
      let current = anchor.parentElement;
      for (let depth = 0; current && depth < 9; depth += 1, current = current.parentElement) {
        const text = normalize(current.innerText);
        if (text.length > 3000) break;
        if (!datePattern.test(text) || !/lihat balasan/i.test(text)) continue;
        if (!seen.has(current)) {
          seen.add(current);
          cards.push(current);
        }
        break;
      }
    }
    return cards;
  }

  function heuristicReviewText(card) {
    const candidates = [...card.querySelectorAll("p, span, div")]
      .filter(isVisible)
      .map(directText)
      .filter((text) => text.length <= 500 && isReviewText(text));
    return [...new Set(candidates)].sort((a, b) => b.length - a.length)[0] || "";
  }

  function reviewText(card, candidates) {
    for (const selector of candidates) {
      const texts = [...card.querySelectorAll(selector)]
        .filter(isVisible)
        .map((node) => normalize(node.textContent))
        .filter((text) => text.length <= 2000 && isReviewText(text))
        .filter((text) => !/^balasan penjual\b/i.test(text));
      if (texts.length) return texts.sort((a, b) => b.length - a.length)[0];
    }
    return heuristicReviewText(card);
  }

  function reviewRating(card) {
    const labels = [...card.querySelectorAll("[aria-label]")]
      .map((node) => normalize(node.getAttribute("aria-label")))
      .filter((label) => /bintang|star|rating/i.test(label));
    for (const label of labels) {
      const match = label.match(/(?:^|\s)([1-5](?:[.,]\d)?)(?:\s|$)/);
      if (match) return Number(match[1].replace(",", "."));
    }
    const filledStars = card.querySelectorAll([
      ".shopee-rating-stars__lit",
      "[class*='star'][class*='lit']",
      "[class*='star'][class*='active']",
      ".icon-rating-solid--on",
      "[data-testid='star-icon'].active",
      "svg[fill='#EE4D2D']",
      "svg[fill='#FD973B']",
    ].join(",")).length;
    if (filledStars > 0) return Math.min(5, filledStars);
    return null;
  }

  function reviewDate(card) {
    const raw = card.querySelector("time[datetime]")?.getAttribute("datetime");
    if (!raw) return null;
    const parsed = new Date(raw);
    return Number.isNaN(parsed.getTime()) ? null : parsed.toISOString();
  }

  function smallHash(value) {
    let hash = 2166136261;
    for (let index = 0; index < value.length; index += 1) {
      hash ^= value.charCodeAt(index);
      hash = Math.imul(hash, 16777619);
    }
    return (hash >>> 0).toString(16).padStart(8, "0");
  }

  function externalId(card, text, rating) {
    const candidate = normalize(
      card.getAttribute("data-review-id") || card.id || card.getAttribute("data-id")
    );
    if (candidate && !/^(review[-_ ]?card|review[-_ ]?item)$/i.test(candidate)) {
      return candidate.slice(0, 200);
    }
    return `visible-${smallHash(`${text}|${rating || ""}`)}`;
  }

  function capture() {
    const marketplace = marketplaceFromHost(location.hostname);
    const config = selectors[marketplace];
    const selectedCards = firstWorkingSelector(config.cards);
    const cards = (selectedCards.length ? selectedCards : heuristicReviewCards()).slice(0, 100);
    const seen = new Set();
    const reviews = [];

    for (const card of cards) {
      const text = reviewText(card, config.text);
      if (!text) continue;
      const rating = reviewRating(card);
      const external_id = externalId(card, text, rating);
      if (seen.has(external_id)) continue;
      seen.add(external_id);
      reviews.push({
        external_id,
        text,
        ...(rating ? { rating } : {}),
        ...(reviewDate(card) ? { created_at: reviewDate(card) } : {}),
      });
    }

    return {
      marketplace,
      product_url: location.href,
      page_title: document.title,
      reviews,
    };
  }

  chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
    if (message?.type !== "UMKM_CAPTURE_REVIEWS") return false;
    try {
      sendResponse({ ok: true, ...capture() });
    } catch (error) {
      sendResponse({ ok: false, error: error.message || "Gagal membaca halaman." });
    }
    return false;
  });
})();
