import os
from flask import Flask, jsonify, request, send_from_directory
import requests
from scraper import scrape, ScrapeError
from ai_summary import ai_available, enhance

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

app = Flask(__name__, static_folder="static", static_url_path="/static")


@app.get("/")
def index():
    return send_from_directory("static", "index.html")


@app.get("/api/config")
def config():
    return jsonify(ai_available=ai_available())


@app.post("/api/scrape")
def api_scrape():
    body = request.get_json(silent=True) or {}
    try:
        max_pages = max(1, min(int(body.get("max_pages", 12)), 30))
    except (TypeError, ValueError):
        max_pages = 12
    try:
        result = scrape(body.get("url", ""), max_pages)
    except ScrapeError as e:
        return jsonify(error=str(e)), 400
    except requests.RequestException:
        return jsonify(error="Could not connect to the site. Check the address and try again."), 502
    excerpts = result.pop("_excerpts")
    if body.get("use_ai") and ai_available():
        result["_excerpts"] = excerpts
        result["ai"] = enhance(result)
        result.pop("_excerpts")
    return jsonify(result)


if __name__ == "__main__":
 port = int(os.getenv("PORT", 5000))
 debug = os.getenv("FLASK_DEBUG", "0") == "1"
 app.run(host="0.0.0.0", port=port, debug=debug)
