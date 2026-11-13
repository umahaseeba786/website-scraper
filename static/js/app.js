const $ = (id) => document.getElementById(id);
let lastResult = null;

function el(tag, props = {}, ...kids) {
  const n = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) k === "text" ? (n.textContent = v) : n.setAttribute(k, v);
  kids.flat().forEach((c) => c != null && n.append(c));
  return n;
}
const link = (href, label) => el("a", { href, target: "_blank", rel: "noopener noreferrer", text: label || href });
const empty = (t) => el("p", { class: "empty", text: t });
const setStatus = (t, cls = "") => { $("status").textContent = t; $("status").className = "status " + cls; };

function render(r) {
  lastResult = r;
  $("siteName").textContent = r.site_name;
  const a = $("siteLink"); a.href = r.url; a.textContent = r.domain;
  $("stats").textContent = `· ${r.stats.pages_read} pages read in ${r.stats.seconds}s`;

  const pb = $("purposeBody"); pb.replaceChildren();
  const ai = r.ai && !r.ai.error ? r.ai : null;
  const summary = (ai && ai.purpose) || r.purpose.summary;
  if (summary) pb.append(el("p", { class: "lede", text: summary }));
  if (r.purpose.headline && r.purpose.headline !== summary) pb.append(el("p", { class: "sub", text: "Home page headline: " + r.purpose.headline }));
  r.purpose.about.forEach((t) => pb.append(el("p", { class: "sub", text: t })));
  if (!pb.children.length) pb.append(empty("This site doesn't state its purpose in text we could read. Try scanning more pages."));
  if (ai) pb.append(el("p", { class: "note", text: "Summary written by AI from the pages read. Check it against the site." }));
  if (r.ai && r.ai.error) pb.append(el("p", { class: "note", text: r.ai.error + ". Showing text taken directly from the site." }));

  const services = ai && ai.services.length ? ai.services : r.services;
  const sb = $("servicesBody"); sb.replaceChildren();
  if (services.length) sb.append(el("ul", { class: "svc" }, services.map((s) => el("li", {}, el("b", { text: s.name }), s.description ? el("span", { text: s.description }) : null))));
  else sb.append(empty("No services were found. The site may list them in images or load them with JavaScript."));
  if (services.length && !ai) sb.append(el("p", { class: "note", text: "Taken from service-related pages and headings. Some items may not be services." }));

  const pg = $("pagesBody"); pg.replaceChildren();
  const row = (p) => el("li", {}, el("span", { class: "chip " + p.category, text: p.category }), el("div", {}, link(p.url, p.title), el("small", { text: p.description || p.url })));
  pg.append(el("ul", { class: "pg" }, r.pages.map(row)));
  if (r.other_links.length) pg.append(el("details", {}, el("summary", { text: `${r.other_links.length} more pages found but not read` }), el("ul", { class: "pg" }, r.other_links.map(row))));

  const c = r.contact, cb = $("contactBody"); cb.replaceChildren();
  const dl = el("dl");
  const add = (label, nodes) => nodes.length && dl.append(el("dt", { text: label }), el("dd", {}, el("ul", {}, nodes.map((n) => el("li", {}, n)))));
  add("Email", c.emails.map((e) => el("a", { href: "mailto:" + e, text: e })));
  add("Phone", c.phones.map((p) => el("a", { href: "tel:" + p.replace(/[^\d+]/g, ""), text: p })));
  add("Address", c.addresses.map((t) => document.createTextNode(t)));
  add("Social", c.social.map((u) => link(u, u.replace(/^https?:\/\/(www\.)?/, ""))));
  add("Contact page", c.contact_pages.map((u) => link(u, u)));
  if (c.has_contact_form) dl.append(el("dt", { text: "Form" }), el("dd", { text: "The contact page has a message form." }));
  cb.append(dl.children.length ? dl : empty("No contact details were found on the pages read. Try reading more pages."));

  $("results").hidden = false;
  $("results").scrollIntoView({ behavior: "smooth" });
}

$("form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const url = $("url").value.trim();
  if (!url) return setStatus("Enter a website address first, for example https://example.com.", "error");
  $("go").disabled = true; $("results").hidden = true;
  setStatus("Scanning. This usually takes 10–40 seconds.", "busy");
  try {
    const res = await fetch("/api/scrape", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url, max_pages: +$("max").value, use_ai: !$("aiLabel").hidden && $("ai").checked }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "The scan failed.");
    setStatus(""); render(data);
  } catch (err) {
    setStatus(err.message.includes("fetch") ? "Can't reach the SiteScout server. Make sure app.py is still running." : err.message, "error");
  } finally { $("go").disabled = false; }
});

$("try").addEventListener("click", () => { $("url").value = "https://example.com"; $("form").requestSubmit(); });
$("copy").addEventListener("click", async () => {
  await navigator.clipboard.writeText(JSON.stringify(lastResult, null, 2));
  $("copy").textContent = "Copied"; setTimeout(() => ($("copy").textContent = "Copy as JSON"), 1500);
});
$("download").addEventListener("click", () => {
  const a = el("a", { href: URL.createObjectURL(new Blob([JSON.stringify(lastResult, null, 2)], { type: "application/json" })), download: lastResult.domain + ".json" });
  a.click(); URL.revokeObjectURL(a.href);
});
fetch("/api/config").then((r) => r.json()).then((c) => { $("aiLabel").hidden = !c.ai_available; }).catch(() => {});
