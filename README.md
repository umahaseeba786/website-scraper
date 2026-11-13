# SiteScout

Enter a website address and get its pages, services, purpose and contact details.
Frontend: HTML, CSS, JavaScript. Backend: Python (Flask).

## Run it in VS Code (Windows)
1. Unzip the folder and open it in VS Code (File > Open Folder).
2. Open a terminal (Ctrl + `) and run:
   ```
   py -m venv venv
   venv\Scripts\activate
   pip install -r requirements.txt
   python app.py
   ```
3. Open http://127.0.0.1:5000 in your browser, paste a website link and press **Scan website**.

On macOS/Linux, activate with `source venv/bin/activate`.

## Optional: AI summaries
Copy `.env.example` to `.env`, add your `ANTHROPIC_API_KEY`, and restart. A checkbox
"Write the summary with AI" then appears. Without a key, the tool works with built-in extraction.

## Notes
- It reads up to 30 pages of the same site, respects robots.txt, and pauses briefly between pages.
- Pages that build their content with JavaScript may return little text; this tool reads the HTML the server sends.
- Addresses that point to private networks are blocked unless you set `ALLOW_PRIVATE=1` in `.env`.
- Only scan sites you are allowed to scan, and follow each site's terms.

## Files
`app.py` server and API · `scraper.py` crawling and extraction · `ai_summary.py` optional AI step · `static/` the web interface
