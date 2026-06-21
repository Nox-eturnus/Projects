from playwright.sync_api import sync_playwright

url = "https://bharatiya-jnana-sarita.info/en/article/view/66d6b61b9b7c1ba29cf7c0d5"

def on_response(response):
    # Only print things that look like API calls
    if "api" in response.url or "graphql" in response.url or "article" in response.url:
        print(f"[API] {response.status} {response.url}")

def on_console(msg):
    if msg.type == "error":
        print(f"[CONSOLE] {msg.text}")

with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, channel="chrome", args=["--disable-blink-features=AutomationControlled"])
    context = browser.new_context(viewport={"width": 1920, "height": 1080})
    page = context.new_page()
    page.on("response", on_response)
    page.on("console", on_console)
    
    print("Navigating...")
    page.goto(url, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(8000)
    
    context.close()
    browser.close()
