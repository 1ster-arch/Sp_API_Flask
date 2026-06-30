import { useEffect, useMemo, useState } from "react";

const NAV_ITEMS = [
  { key: "lookup", label: "ASIN Lookup" },
  { key: "catalog", label: "Catalog" },
  { key: "feedback", label: "Feedback" },
  { key: "reports", label: "Reports" }
];

const TOOL_ITEMS = [
  { key: "import", label: "Data Import" },
  { key: "audit", label: "Audit" },
  { key: "config", label: "Config" }
];

function normalizeAsin(value) {
  return (value || "").trim().toUpperCase();
}

function formatPrice(price) {
  if (price === null || price === undefined || price === "") return "";
  const amount = Number(price);
  if (Number.isNaN(amount)) return `$${price}`;
  return `$${amount.toFixed(2)}`;
}

export default function App() {
  const [products, setProducts] = useState([]);
  const [query, setQuery] = useState("");
  const [activeSection, setActiveSection] = useState("lookup");
  const [isBusy, setIsBusy] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");
  const [hintMessage, setHintMessage] = useState("");
  const [showSuggestions, setShowSuggestions] = useState(false);

  useEffect(() => {
    loadProducts();
  }, []);

  const normalizedQuery = useMemo(() => normalizeAsin(query), [query]);

  const filteredProducts = useMemo(() => {
    if (!normalizedQuery) return products;
    return products.filter((item) => normalizeAsin(item.asin).includes(normalizedQuery));
  }, [products, normalizedQuery]);

  const feedbackProducts = useMemo(
    () => filteredProducts.filter((item) => item.review_topics),
    [filteredProducts]
  );

  const suggestions = useMemo(() => {
    const source = [];
    const seen = new Set();

    products.forEach((item) => {
      const asin = normalizeAsin(item.asin);
      if (!asin || seen.has(asin)) return;
      seen.add(asin);
      source.push({
        asin,
        product_details: item.product_details || "No product title available"
      });
    });

    if (!normalizedQuery) return source.slice(0, 8);
    return source
      .filter((item) => item.asin.includes(normalizedQuery))
      .slice(0, 8);
  }, [products, normalizedQuery]);

  useEffect(() => {
    if (!normalizedQuery) {
      setHintMessage("");
      setErrorMessage("");
      return;
    }

    if (filteredProducts.length === 0) {
      setErrorMessage("No matching ASIN found in loaded products.");
      setHintMessage("");
      return;
    }

    setErrorMessage("");
    if (feedbackProducts.length === 0) {
      setHintMessage("Product found. Feedback has not been returned for this ASIN yet.");
    } else {
      setHintMessage("");
    }
  }, [normalizedQuery, filteredProducts, feedbackProducts]);

  async function loadProducts() {
    try {
      const response = await fetch("/api/products");
      if (!response.ok) throw new Error(response.statusText);
      const payload = await response.json();
      setProducts(payload.products || []);
    } catch (error) {
      setErrorMessage(`Failed to load products: ${error.message}`);
    }
  }

  async function searchAsin() {
    const asin = normalizeAsin(query);
    setShowSuggestions(false);
    if (!asin) {
      setErrorMessage("Enter an ASIN before searching.");
      return;
    }

    setIsBusy(true);
    setErrorMessage("");
    try {
      const response = await fetch(`/api/fetch/${encodeURIComponent(asin)}`, { method: "POST" });
      if (!response.ok) {
        let message = response.statusText;
        try {
          const payload = await response.json();
          message = payload?.error?.description || message;
        } catch {
          // ignore parse fallback
        }
        throw new Error(message || "Fetch failed");
      }

      await loadProducts();
      setQuery(asin);
      setActiveSection("lookup");
    } catch (error) {
      setErrorMessage(`Search fetch failed: ${error.message}`);
    } finally {
      setIsBusy(false);
    }
  }

  async function fetchAsin() {
    const asin = normalizeAsin(query);
    if (!asin) {
      setErrorMessage("Enter an ASIN before fetching.");
      return;
    }

    setIsBusy(true);
    setErrorMessage("");
    try {
      const response = await fetch(`/api/fetch/${encodeURIComponent(asin)}`, { method: "POST" });
      if (!response.ok) throw new Error(response.statusText);
      await loadProducts();
      setQuery(asin);
      setActiveSection("lookup");
    } catch (error) {
      setErrorMessage(`Fetch failed: ${error.message}`);
    } finally {
      setIsBusy(false);
    }
  }

  async function reloadData() {
    setIsBusy(true);
    setErrorMessage("");
    try {
      const response = await fetch("/api/reload", { method: "POST" });
      if (!response.ok) throw new Error(response.statusText);
      await loadProducts();
      setActiveSection("lookup");
    } catch (error) {
      setErrorMessage(`Failed to reload: ${error.message}`);
    } finally {
      setIsBusy(false);
    }
  }

  async function clearAll() {
    if (!window.confirm("Clear all product data?")) return;

    setIsBusy(true);
    setErrorMessage("");
    try {
      const response = await fetch("/api/products", { method: "DELETE" });
      if (!response.ok) throw new Error(response.statusText);
      setProducts([]);
      setQuery("");
      setHintMessage("");
      setActiveSection("lookup");
    } catch (error) {
      setErrorMessage(`Failed to clear: ${error.message}`);
    } finally {
      setIsBusy(false);
    }
  }

  function showAll() {
    setQuery("");
    setShowSuggestions(false);
    setErrorMessage("");
    setHintMessage("");
    setActiveSection("lookup");
  }

  function selectSuggestion(asin) {
    setQuery(asin);
    setShowSuggestions(false);
    setActiveSection("lookup");
  }

  function renderLookupSection() {
    return (
      <section className="rounded-xl border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-4 pb-2 pt-4">
          <h2 className="text-xl font-semibold text-ink">ASIN Runtime Actions</h2>
          <p className="text-sm text-muted">Search or fetch products quickly while keeping dataset controls in one place.</p>
        </div>
        <div className="p-4">
          <div className="grid gap-3 md:grid-cols-2">
            <div className="relative">
              <input
                type="text"
                value={query}
                onFocus={() => setShowSuggestions(true)}
                onChange={(event) => {
                  setQuery(event.target.value);
                  setShowSuggestions(true);
                  setActiveSection("lookup");
                }}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    event.preventDefault();
                    searchAsin();
                  }
                }}
                placeholder="ASIN, e.g. B0CMDD18FS"
                className="h-10 w-full rounded-lg border border-slate-300 bg-slate-50 px-3 text-sm outline-none ring-blue-100 transition focus:border-blue-400 focus:ring"
              />
              {showSuggestions && suggestions.length > 0 && (
                <div className="absolute left-0 right-0 top-[calc(100%+4px)] z-20 max-h-60 overflow-y-auto rounded-lg border border-slate-200 bg-white shadow-soft">
                  {suggestions.map((item) => (
                    <button
                      key={item.asin}
                      type="button"
                      className="flex w-full flex-col border-b border-slate-100 px-3 py-2 text-left hover:bg-slate-50"
                      onClick={() => selectSuggestion(item.asin)}
                    >
                      <span className="text-sm font-semibold text-blue-700">{item.asin}</span>
                      <span className="truncate text-xs text-slate-500">{item.product_details}</span>
                    </button>
                  ))}
                </div>
              )}
            </div>
            <input
              type="text"
              value="Amazon endpoint status: Connected"
              disabled
              className="h-10 w-full rounded-lg border border-slate-300 bg-slate-50 px-3 text-sm text-slate-600"
            />
          </div>

          <div className="mt-3 flex flex-wrap gap-2">
            <button type="button" onClick={showAll} className="rounded-lg border border-blue-200 bg-blue-50 px-4 py-2 text-sm font-semibold text-blue-700">
              Show All
            </button>
            <button type="button" disabled={isBusy} onClick={reloadData} className="rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-2 text-sm font-semibold text-emerald-700 disabled:opacity-60">
              Reload Data
            </button>
            <button type="button" disabled={isBusy} onClick={fetchAsin} className="rounded-lg bg-blue-600 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-700 disabled:opacity-60">
              Fetch from API
            </button>
            <button type="button" disabled={isBusy} onClick={clearAll} className="rounded-lg border border-rose-200 bg-rose-50 px-4 py-2 text-sm font-semibold text-rose-700 disabled:opacity-60">
              Clear All
            </button>
          </div>

          {errorMessage && <p className="mt-3 rounded-lg border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-700">{errorMessage}</p>}
          {hintMessage && <p className="mt-3 rounded-lg border border-blue-200 bg-blue-50 px-3 py-2 text-sm text-blue-700">{hintMessage}</p>}
        </div>
      </section>
    );
  }

  function renderStats() {
    return (
      <div className="mt-3 flex flex-wrap gap-2">
        <span className="rounded-full border border-slate-300 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">Total Products: {products.length}</span>
        <span className="rounded-full border border-slate-300 bg-slate-50 px-3 py-1 text-xs font-semibold text-slate-700">Showing: {filteredProducts.length}</span>
      </div>
    );
  }

  function renderCatalogSection() {
    if (!products.length) {
      return (
        <section className="rounded-xl border border-line bg-panel p-10 text-center text-sm text-muted shadow-soft">
          No products loaded yet. Use Fetch from API or Reload Data to begin.
        </section>
      );
    }

    return (
      <section className="rounded-xl border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-4 pb-2 pt-4">
          <h2 className="text-xl font-semibold text-ink">Catalog Items</h2>
          <p className="text-sm text-muted">Structured listing of product attributes and API-returned data points.</p>
        </div>
        <div className="overflow-x-auto p-4">
          <table className="min-w-[980px] w-full border-collapse">
            <thead>
              <tr className="bg-[#243658] text-left text-xs text-slate-100">
                {["#", "Product Details", "ASIN", "URL", "Image", "Brand", "Origin", "Price $", "BSR", "Ratings", "Review Count"].map((label) => (
                  <th key={label} className="px-2 py-3 font-semibold">{label}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {filteredProducts.map((product, index) => (
                <tr key={`${product.asin}-${index}`} className="border-b border-slate-200 text-xs text-slate-800 hover:bg-slate-50">
                  <td className="px-2 py-2">{index + 1}</td>
                  <td className="px-2 py-2">{product.product_details || ""}</td>
                  <td className="px-2 py-2">{product.asin || ""}</td>
                  <td className="px-2 py-2">
                    {product.url ? (
                      <a className="text-blue-700 hover:underline" href={product.url} target="_blank" rel="noreferrer">
                        Open
                      </a>
                    ) : (
                      ""
                    )}
                  </td>
                  <td className="px-2 py-2">
                    {product.image_url ? <img src={product.image_url} alt="Product" className="h-14 w-14 object-contain" /> : ""}
                  </td>
                  <td className="px-2 py-2">{product.brand || ""}</td>
                  <td className="px-2 py-2">{product.origin || "N/A"}</td>
                  <td className="px-2 py-2">{formatPrice(product.price)}</td>
                  <td className="px-2 py-2">{product.bsr || ""}</td>
                  <td className="px-2 py-2">{product.ratings || ""}</td>
                  <td className="px-2 py-2">{product.review_count || ""}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    );
  }

  function renderFeedbackSection() {
    return (
      <section className="rounded-xl border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-4 pb-2 pt-4">
          <h2 className="text-xl font-semibold text-ink">Customer Feedback Topics</h2>
          <p className="text-sm text-muted">Review signal grouped into positive and negative trends per ASIN.</p>
        </div>
        <div className="p-4">
          {feedbackProducts.length === 0 && (
            <p className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-3 text-sm text-slate-600">
              No customer feedback review topics data available.
            </p>
          )}

          {feedbackProducts.map((product, idx) => (
            <div key={`${product.asin}-${idx}`} className="mb-3 overflow-hidden rounded-lg border border-slate-200 bg-slate-50">
              <div className="flex items-center gap-2 border-b border-slate-200 bg-slate-100 px-3 py-2">
                <span className="rounded bg-[#243658] px-2 py-1 text-xs font-bold text-white">{product.asin || "Unknown"}</span>
                <span className="text-xs text-slate-600">{product.product_details || product.brand || ""}</span>
              </div>
              <div className="grid gap-3 p-3 md:grid-cols-2">
                <div>
                  <h3 className="mb-2 text-sm font-semibold text-emerald-700">Positive Topics</h3>
                  {(product.review_topics?.positiveTopics || []).map((topic, index) => (
                    <div key={index} className="mb-2 rounded-lg border border-slate-200 border-l-4 border-l-emerald-600 bg-white p-2">
                      <h4 className="mb-1 text-sm font-semibold text-slate-800">{topic.topic}</h4>
                      <div className="flex flex-wrap gap-1">
                        {topic.numberOfMentions ? <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-[11px]">Mentions: {topic.numberOfMentions}</span> : null}
                        {topic.occurrencePercentage ? <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-[11px]">Occurrence: {topic.occurrencePercentage}%</span> : null}
                        {topic.starRatingImpact ? <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-[11px]">Impact: {topic.starRatingImpact}</span> : null}
                      </div>
                    </div>
                  ))}
                </div>

                <div>
                  <h3 className="mb-2 text-sm font-semibold text-rose-700">Negative Topics</h3>
                  {(product.review_topics?.negativeTopics || []).map((topic, index) => (
                    <div key={index} className="mb-2 rounded-lg border border-slate-200 border-l-4 border-l-rose-600 bg-white p-2">
                      <h4 className="mb-1 text-sm font-semibold text-slate-800">{topic.topic}</h4>
                      <div className="flex flex-wrap gap-1">
                        {topic.numberOfMentions ? <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-[11px]">Mentions: {topic.numberOfMentions}</span> : null}
                        {topic.occurrencePercentage ? <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-[11px]">Occurrence: {topic.occurrencePercentage}%</span> : null}
                        {topic.starRatingImpact ? <span className="rounded-full border border-slate-200 bg-slate-50 px-2 py-1 text-[11px]">Impact: {topic.starRatingImpact}</span> : null}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </div>
          ))}
        </div>
      </section>
    );
  }

  function renderPlaceholder(title, description) {
    return (
      <section className="rounded-xl border border-line bg-panel shadow-soft">
        <div className="border-b border-line px-4 pb-2 pt-4">
          <h2 className="text-xl font-semibold text-ink">{title}</h2>
        </div>
        <div className="p-4">
          <p className="rounded-lg border border-dashed border-slate-300 bg-slate-50 p-3 text-sm text-slate-600">{description}</p>
        </div>
      </section>
    );
  }

  return (
    <div className="grid min-h-screen grid-cols-1 lg:grid-cols-[240px_1fr]">
      <aside className="sticky top-0 h-auto border-b border-white/10 bg-gradient-to-b from-[#1c2a44] to-[#141f35] p-4 text-slate-100 lg:h-screen lg:border-b-0 lg:border-r">
        <div className="mb-4 rounded-lg border border-white/10 bg-white/10 p-2 text-sm font-semibold">SP-API Dashboard</div>

        <p className="mb-2 mt-3 px-2 text-[11px] uppercase tracking-[0.1em] text-slate-400">Navigation</p>
        <ul className="mb-3 space-y-1">
          {NAV_ITEMS.map((item) => (
            <li
              key={item.key}
              className={`cursor-pointer rounded-lg border px-2 py-2 text-sm ${
                activeSection === item.key
                  ? "border-blue-200/40 bg-blue-500/25 font-semibold"
                  : "border-transparent hover:bg-white/5"
              }`}
              onClick={() => setActiveSection(item.key)}
            >
              {item.label}
            </li>
          ))}
        </ul>

        <p className="mb-2 mt-3 px-2 text-[11px] uppercase tracking-[0.1em] text-slate-400">Tools</p>
        <ul className="space-y-1">
          {TOOL_ITEMS.map((item) => (
            <li
              key={item.key}
              className={`cursor-pointer rounded-lg border px-2 py-2 text-sm ${
                activeSection === item.key
                  ? "border-blue-200/40 bg-blue-500/25 font-semibold"
                  : "border-transparent hover:bg-white/5"
              }`}
              onClick={() => setActiveSection(item.key)}
            >
              {item.label}
            </li>
          ))}
        </ul>
      </aside>

      <main className="p-4">
        <div className="mb-4 flex flex-wrap items-center justify-between rounded-xl border border-line bg-panel px-4 py-3 shadow-soft">
          <div>
            <h1 className="text-2xl font-bold text-ink">Catalog Control Panel</h1>
            <p className="text-sm text-muted">Structured view for product lookup, API fetches, and review insights.</p>
          </div>
          <span className="rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-bold text-emerald-700">API Online</span>
        </div>

        {activeSection === "lookup" && (
          <>
            {renderLookupSection()}
            {renderStats()}
          </>
        )}
        {activeSection === "catalog" && renderCatalogSection()}
        {activeSection === "feedback" && renderFeedbackSection()}
        {activeSection === "reports" && renderPlaceholder("Reports", "Reports panel is ready. Connect your reporting logic here when those endpoints are available.")}
        {activeSection === "import" && renderPlaceholder("Data Import", "Use Reload Data in ASIN Lookup to refresh from local JSON sources.")}
        {activeSection === "audit" && renderPlaceholder("Audit", "Audit tools can be surfaced here, such as failed fetch counts, stale records, and auth health checks.")}
        {activeSection === "config" && renderPlaceholder("Config", "Configuration is currently environment-based via your backend .env values.")}
      </main>
    </div>
  );
}
