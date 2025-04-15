import asyncio
import pickle
import logging
from datetime import datetime
import subprocess
import json
import os
from playwright.async_api import async_playwright

# === Config ===
URL = "https://my.exness.com/mfp/st/strategy?account=110284373&from_fav=true"
API_URL = "https://my.exness.com/v4/st/v1/managers/accounts/110284373/open-trades/"
POLL_INTERVAL = 0.3  # <-- polling frequency here
RETRY_DELAY = 10
COOKIE_PATH = "cookies.pkl"
SELENIUM_SCRIPT = "selenium_login.py"

ORDER_LOG_FILE = "orders_log.jsonl"
CLOSED_LOG_FILE = "orders_closed.jsonl"
STATE_FILE = "state.json"
LIVE_OUTPUT_FILE = "latest.json"

# === Logging setup ===
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")

# === State Tracking & File IO ===
def load_state():
    if os.path.exists(STATE_FILE):
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"open_orders": [], "closed_orders": []}

def save_state(state):
    with open(STATE_FILE, "w") as f:
        json.dump(state, f)

def log_order_to_file(file_path, order_data):
    with open(file_path, "a") as f:
        json.dump(order_data, f)
        f.write("\n")

def update_live_output(open_order=None, closed_order=None):
    latest = {
        "timestamp": datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        "latest_open": open_order,
        "latest_closed": closed_order
    }
    with open(LIVE_OUTPUT_FILE, "w") as f:
        json.dump(latest, f, indent=2)

# === Cookie Handling ===
def load_cookies():
    try:
        with open(COOKIE_PATH, "rb") as f:
            return pickle.load(f)
    except Exception as e:
        logging.error("⚠️ Failed to load cookies: %s", e)
        return []

def refresh_cookies_with_selenium():
    try:
        logging.info("🟠 Launching Selenium to refresh cookies...")
        result = subprocess.run(["python", SELENIUM_SCRIPT], capture_output=True, text=True, timeout=300)
        if result.returncode == 0:
            logging.info("✅ Cookies refreshed via Selenium.")
        else:
            logging.error("❌ Selenium login failed:\n%s", result.stderr)
            raise RuntimeError("Selenium failed")
    except Exception as e:
        logging.error("💥 Error running Selenium: %s", e)
        raise

# === Main Monitoring Loop ===
async def monitor_page(page, api_url, poll_interval, state):
    while True:
        try:
            data = await page.evaluate(f"""
                () => fetch("{api_url}", {{
                    method: "GET",
                    credentials: "include"
                }}).then(r => r.ok ? r.json() : Promise.reject(r.status))
            """)
        except Exception as e:
            logging.warning("⚠️ Temporary fetch error: %s", e)
            await asyncio.sleep(poll_interval)
            continue  # skip one cycle and retry

        orders = data.get("result", [])
        current_ids = {str(order["order_id"]) for order in orders}
        new_open = [o for o in orders if str(o["order_id"]) not in state["open_orders"]]
        closed = [oid for oid in state["open_orders"] if oid not in current_ids]

        latest_open = None
        latest_closed = None

        for order in new_open:
            oid = str(order["order_id"])
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            logging.info("🟢 [%s] New Order: %s — %s %s @ %s",
                         timestamp, oid, order['symbol'], order['trade_type'], order['open_price'])

            log_order_to_file(ORDER_LOG_FILE, {
                "timestamp": timestamp,
                "type": "NEW",
                "order_id": oid,
                "symbol": order['symbol'],
                "trade_type": order['trade_type'],
                "open_price": order['open_price'],
                "raw": order
            })
            state["open_orders"].append(oid)
            latest_open = {
                "timestamp": timestamp,
                "order_id": oid,
                "symbol": order['symbol'],
                "trade_type": order['trade_type'],
                "open_price": order['open_price']
            }

        for oid in closed:
            timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            logging.info("🔴 [%s] Order Closed: %s", timestamp, oid)

            log_order_to_file(CLOSED_LOG_FILE, {
                "timestamp": timestamp,
                "type": "CLOSED",
                "order_id": oid
            })
            state["open_orders"].remove(oid)
            state["closed_orders"].append(oid)
            latest_closed = {
                "timestamp": timestamp,
                "order_id": oid
            }

        save_state(state)
        update_live_output(open_order=latest_open, closed_order=latest_closed)

        await asyncio.sleep(poll_interval)

# === Master Execution Control ===
async def start_monitoring():
    state = load_state()

    async with async_playwright() as p:
        while True:
            cookies = load_cookies()
            if not cookies:
                refresh_cookies_with_selenium()
                cookies = load_cookies()

            try:
                browser = await p.chromium.launch(headless=False)
                context = await browser.new_context()
                await context.add_cookies(cookies)
                page = await context.new_page()

                logging.info("🌐 Navigating to strategy page...")
                await page.goto(URL)
                await page.wait_for_load_state("networkidle")
                logging.info("✅ Page loaded. Starting polling every %.1fs...", POLL_INTERVAL)

                await monitor_page(page, API_URL, POLL_INTERVAL, state)

            except Exception as e:
                logging.error("💥 Critical error. Restarting in %ss: %s", RETRY_DELAY, e)
                try:
                    await browser.close()
                except:
                    pass
                refresh_cookies_with_selenium()
                await asyncio.sleep(RETRY_DELAY)

# === Run with Safe Exit ===
if __name__ == "__main__":
    try:
        asyncio.run(start_monitoring())
    except KeyboardInterrupt:
        logging.info("🛑 Monitoring stopped by user.")
