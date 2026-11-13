"""Crawl one website (same domain only) and pull out pages, services, purpose and contact info."""
import heapq, ipaddress, json, os, re, socket, time
from urllib import robotparser
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup

UA = "SiteScout/1.0 (local research tool)"
SKIP_EXT = re.compile(r"\.(pdf|jpe?g|png|gif|svg|webp|zip|rar|mp4|mp3|docx?|xlsx?|pptx?|css|js|ico|xml)$", re.I)
CATS = {
    "contact": ["contact", "get-in-touch", "reach-us", "enquir", "inquir", "find-us", "location"],
    "about": ["about", "who-we-are", "our-story", "company", "team", "mission"],
    "services": ["service", "solution", "product", "what-we-do", "offering", "feature", "pricing",
                 "platform", "expertise", "program", "course", "menu"],
    "blog": ["blog", "news", "article", "press", "insight", "resource"],
    "legal": ["privacy", "terms", "cookie", "legal", "policy"],
}
PRIORITY = {"home": 0, "contact": 1, "about": 1, "services": 1, "other": 2, "blog": 3, "legal": 4}
GENERIC = {"contact us", "our services", "services", "learn more", "read more", "get started", "faq", "faqs",
           "testimonials", "subscribe", "follow us", "newsletter", "menu", "search", "related", "share",
           "quick links", "about us", "home", "login", "sign in", "privacy policy", "terms", "reviews"}
SOCIAL = ("facebook.com", "instagram.com", "linkedin.com", "twitter.com", "x.com", "youtube.com",
          "tiktok.com", "github.com", "wa.me", "t.me", "pinterest.com")
EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
PHONE_RE = re.compile(r"(?<![\w.])(\+?\d[\d\s().-]{7,17}\d)(?!\w)")


class ScrapeError(Exception):
    pass


def normalize_url(raw):
    raw = (raw or "").strip()
    if not raw:
        raise ScrapeError("Enter a website address, for example https://example.com.")
    if not re.match(r"^https?://", raw, re.I):
        raw = "https://" + raw
    p = urlparse(raw)
    if not p.hostname or "." not in p.hostname and p.hostname != "localhost":
        raise ScrapeError("That doesn't look like a website address. Check it and try again.")
    return urldefrag(raw)[0]


def safe_host(host):
    if os.getenv("ALLOW_PRIVATE") == "1":
        return True
    try:
        infos = socket.getaddrinfo(host, None)
    except socket.gaierror:
        raise ScrapeError(f"Could not find {host}. Check the spelling and your internet connection.")
    return all(ipaddress.ip_address(i[4][0]).is_global for i in infos)


def fetch(session, url):
    for _ in range(6):  # follow redirects manually so every hop is checked
        p = urlparse(url)
        if p.scheme not in ("http", "https") or not p.hostname or not safe_host(p.hostname):
            raise ScrapeError("This address points to a private or unsupported location, so it was blocked.")
        r = session.get(url, timeout=10, allow_redirects=False, stream=True)
        if r.status_code in (301, 302, 303, 307, 308) and r.headers.get("Location"):
            url = urljoin(url, r.headers["Location"])
            continue
        if r.status_code >= 400:
            raise ScrapeError(f"The site answered with HTTP {r.status_code}.")
        if "html" not in r.headers.get("Content-Type", "html").lower():
            raise ScrapeError("Not an HTML page.")
        body = b""
        for chunk in r.iter_content(65536):
            body += chunk
            if len(body) > 2_000_000:
                break
        return url, body.decode(r.encoding or "utf-8", errors="replace")
    raise ScrapeError("Too many redirects.")


def classify(url, text=""):
    path = urlparse(url).path.lower()
    if path in ("", "/"):
        return "home"
    s = path + " " + text.lower()
    for cat, words in CATS.items():
        if any(w in s for w in words):
            return cat
    return "other"


def same_site(a, b):
    strip = lambda h: (h or "").lower().removeprefix("www.")
    return strip(urlparse(a).hostname) == strip(urlparse(b).hostname)


def clean(t, n=None):
    t = re.sub(r"\s+", " ", t or "").strip()
    return t[:n].rstrip() + "…" if n and len(t) > n else t


def jsonld(soup):
    out = []
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string or "")
        except (ValueError, TypeError):
            continue
        stack = [data]
        while stack:
            x = stack.pop()
            if isinstance(x, list):
                stack.extend(x)
            elif isinstance(x, dict):
                out.append(x)
                stack.extend(v for v in x.values() if isinstance(v, (dict, list)))
    return out


def parse_page(url, html):
    soup = BeautifulSoup(html, "html.parser")
    meta = lambda **k: clean((soup.find("meta", attrs=k) or {}).get("content", ""))
    info = {
        "url": url,
        "title": clean(soup.title.string if soup.title else ""),
        "description": meta(name="description") or meta(property="og:description"),
        "site_name": meta(property="og:site_name"),
        "h1": clean(soup.h1.get_text(" ")) if soup.h1 else "",
        "ld": jsonld(soup),
        "mailto": [], "tel": [], "social": [], "links": [], "has_form": bool(soup.find("form")),
        "address_tags": [clean(a.get_text(" "), 200) for a in soup.find_all("address")][:3],
    }
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        if href.startswith("mailto:"):
            info["mailto"].append(href[7:].split("?")[0])
        elif href.startswith("tel:"):
            info["tel"].append(clean(href[4:]))
        else:
            full = urldefrag(urljoin(url, href))[0]
            if urlparse(full).scheme in ("http", "https"):
                host = urlparse(full).hostname or ""
                if any(host.endswith(s) for s in SOCIAL) and not re.search(r"share|intent|sharer", full):
                    info["social"].append(full)
                info["links"].append((full, clean(a.get_text(" "), 80)))
    for t in soup(["script", "style", "noscript", "svg"]):
        t.decompose()
    info["text"] = clean(soup.get_text(" "))
    for t in soup(["nav", "footer", "header", "aside", "form"]):
        t.decompose()
    info["paragraphs"] = [clean(p.get_text(" ")) for p in soup.find_all("p") if len(clean(p.get_text(" "))) > 50][:6]
    items = []
    for h in soup.find_all(["h2", "h3", "h4"]):
        name = clean(h.get_text(" "))
        if 3 <= len(name) <= 70 and name.lower().strip(" :!?") not in GENERIC:
            nxt = h.find_next_sibling("p")
            items.append({"name": name, "description": clean(nxt.get_text(" "), 180) if nxt else ""})
    info["headings"] = items
    info["list_items"] = [clean(li.get_text(" ")) for li in soup.select("main li, article li, section li")
                          if 3 <= len(clean(li.get_text(" "))) <= 60][:15]
    return info


def crawl(start, max_pages=12, progress=lambda m: None):
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept": "text/html,*/*;q=0.8"})
    rp = robotparser.RobotFileParser()
    try:
        root = f"{urlparse(start).scheme}://{urlparse(start).netloc}"
        rp.parse(session.get(root + "/robots.txt", timeout=6).text.splitlines())
    except Exception:
        rp = None
    heap, seen, pages, labels, n = [(0, 0, start)], {start}, [], {}, 0
    while heap and len(pages) < max_pages:
        _, _, url = heapq.heappop(heap)
        if rp and not rp.can_fetch(UA, url):
            continue
        progress(f"Reading {url}")
        try:
            final, html = fetch(session, url)
        except ScrapeError as e:
            if not pages:
                raise
            continue
        except requests.RequestException as e:
            if not pages:
                raise ScrapeError("Could not connect to the site. Check the address and try again.")
            continue
        if not pages and not same_site(final, start):
            start = final
        info = parse_page(final, html)
        info["category"] = classify(final, info["title"])
        pages.append(info)
        for link, text in info["links"]:
            if not same_site(link, start) or SKIP_EXT.search(urlparse(link).path):
                continue
            labels.setdefault(link, text)
            if link not in seen and len(urlparse(link).query) < 40:
                seen.add(link)
                n += 1
                heapq.heappush(heap, (PRIORITY[classify(link, text)], n, link))
        time.sleep(0.3)  # be polite
    return pages, labels, start


def build_result(pages, labels, start):
    home = pages[0]
    by_cat = lambda c: [p for p in pages if p["category"] == c]
    crawled = {p["url"] for p in pages}
    org = next((d for p in pages for d in p["ld"] if str(d.get("@type", "")).endswith(
        ("Organization", "LocalBusiness", "Corporation", "Store", "Restaurant"))), {})

    name = home["site_name"] or org.get("name") or re.split(r"\s[|\u2013\u2014-]\s", home["title"])[0] or urlparse(start).hostname
    about = [t for p in by_cat("about") for t in p["paragraphs"][:2]][:3]
    purpose = {"summary": home["description"] or org.get("description") or (home["paragraphs"] or [""])[0],
               "headline": home["h1"], "about": about}

    services, seen = [], set()
    def add(n, d="", src=""):
        k = n.lower()
        if k not in seen and len(services) < 20:
            seen.add(k)
            services.append({"name": n, "description": d, "source": src})
    for p in by_cat("services"):
        for h in p["headings"]:
            add(h["name"], h["description"], p["url"])
        for li in p["list_items"]:
            add(li, "", p["url"])
    for link, text in labels.items():
        if text and 3 <= len(text) <= 60 and text.lower() not in GENERIC and link not in crawled \
           and classify(link, "") == "services" and urlparse(link).path.strip("/").count("/") >= 1:
            add(text, "", link)
    if not services:  # fall back to the home page's section headings
        for h in home["headings"][:8]:
            add(h["name"], h["description"], home["url"])

    emails, phones, socials, addresses = {}, {}, set(), []
    for p in pages:
        found = set(p["mailto"]) | set(EMAIL_RE.findall(p["text"]))
        for e in found:
            e = e.strip(".,;").lower()
            if not re.search(r"\.(png|jpe?g|gif|svg|webp)$|example\.|sentry|wixpress|@2x", e):
                emails[e] = True
        for t in p["tel"]:
            phones[t] = True
        if p["category"] in ("contact", "home", "about"):
            for m in PHONE_RE.findall(p["text"]):
                d = re.sub(r"\D", "", m)
                if 9 <= len(d) <= 15 and not re.match(r"\d{4}-\d{2}-\d{2}", m) and (m.startswith("+") or re.search(r"[\s().-]", m)):
                    phones.setdefault(clean(m), True)
        socials.update(p["social"])
        addresses += p["address_tags"]
    for d in [org] + [x for p in pages for x in p["ld"]]:
        a = d.get("address")
        if isinstance(a, dict) and a.get("streetAddress"):
            addresses.append(", ".join(str(a.get(k)) for k in ("streetAddress", "addressLocality", "addressRegion", "postalCode", "addressCountry") if a.get(k)))
        if d.get("telephone"):
            phones[clean(str(d["telephone"]))] = True
        if d.get("email"):
            emails[str(d["email"]).lower().removeprefix("mailto:")] = True
    domain = urlparse(start).hostname.removeprefix("www.")
    ranked = sorted(emails, key=lambda e: (not e.endswith(domain), e))[:8]
    contact_pages = [p["url"] for p in by_cat("contact")]
    contact = {"emails": ranked, "phones": list(phones)[:6], "addresses": list(dict.fromkeys(a for a in addresses if a))[:3],
              "social": sorted(socials)[:10], "contact_pages": contact_pages,
              "has_contact_form": any(p["has_form"] for p in by_cat("contact"))}

    page_list = [{"url": p["url"], "title": p["title"] or p["url"], "category": p["category"],
                  "description": clean(p["description"], 160)} for p in pages]
    others = [{"url": u, "title": t or u, "category": classify(u, t), "description": ""}
              for u, t in labels.items() if u not in crawled][:60]
    return {"url": start, "domain": domain, "site_name": clean(name, 80), "purpose": purpose, "services": services,
            "contact": contact, "pages": page_list, "other_links": others}


def scrape(raw_url, max_pages=12, progress=lambda m: None):
    started = time.time()
    pages, labels, start = crawl(normalize_url(raw_url), max_pages, progress)
    result = build_result(pages, labels, start)
    result["stats"] = {"pages_read": len(pages), "seconds": round(time.time() - started, 1)}
    # Short text excerpts, used only by the optional AI step
    order = {"home": 0, "about": 1, "services": 2, "contact": 3}
    result["_excerpts"] = [{"url": p["url"], "text": p["text"][:2500]}
                           for p in sorted(pages, key=lambda p: order.get(p["category"], 9))[:5]]
    return result
