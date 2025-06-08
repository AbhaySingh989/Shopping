import os
import google.generativeai as genai
from dotenv import load_dotenv
import time
import random
import json # Added for parsing Gemini's JSON output for Crawl4AI
import asyncio # For running async Crawl4AI code

# Selenium and BeautifulSoup for Amazon
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from bs4 import BeautifulSoup
import undetected_chromedriver as uc

# Crawl4AI imports for Flipkart
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, GeolocationConfig

# Pydantic model for structured data extraction
from pydantic import BaseModel, Field
from typing import List, Optional

class ProductInfo(BaseModel):
    title: Optional[str] = Field(default="N/A", description="Product title")
    price: Optional[str] = Field(default="N/A", description="Product price")
    url: Optional[str] = Field(default="N/A", description="Product URL")

# --- Environment Loading ---
def load_environment_variables():
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    default_pincode = os.getenv("DEFAULT_PINCODE")
    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in .env file.")
    if not default_pincode:
        # Fallback to a default if not found, with a warning.
        print("Warning: DEFAULT_PINCODE not found in .env file, using 560020 as default.")
        default_pincode = "560020"
    return api_key, default_pincode

# --- User Input ---
def get_user_product_query() -> str:
    while True:
        query = input("Please enter the product name or description: ").strip()
        if query:
            return query
        print("Input cannot be empty. Please try again.")

# --- Gemini Query Standardization ---
def get_standardized_query(original_user_query: str, api_key: str) -> str:
    print(f"Original query: {original_user_query}")
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')
        prompt = (
            "You are an e-commerce query optimization assistant. "
            "Refine the following user's product query into a concise and effective search query "
            "suitable for e-commerce platforms like Amazon and Flipkart. "
            "Focus on key product identifiers, brand, model, and relevant keywords. "
            "For example, 'samsung 23L microwave oven black' -> 'Samsung 23L microwave oven black', "
            "'Looking for a 500 gram pack of fresh red tomatoes' -> 'fresh red tomatoes 500g'. "
            "Output only the refined query string, with no conversational pleasantries or markdown."
            f"User query: \"{original_user_query}\""
        )
        response = model.generate_content(prompt)
        standardized = response.text.strip()
        # Clean potential markdown/json hints from Gemini output
        if standardized.startswith("```json"): standardized = standardized[7:]
        if standardized.startswith("```"): standardized = standardized[3:]
        if standardized.endswith("```"): standardized = standardized[:-3]
        if standardized.startswith("`") and standardized.endswith("`"): standardized = standardized[1:-1]
        standardized = standardized.replace("json", "").strip() # Remove "json" if it's at the start after backticks

        print(f"Standardized query: {standardized}")
        return standardized
    except Exception as e:
        print(f"Gemini API error during query standardization: {e}. Using original query.")
        return original_user_query

# --- Gemini Product Relevance Check ---
def is_product_relevant_gemini(user_query_for_relevance: str, product_title: str, api_key: str, product_description: str = None) -> bool:
    prompt_parts = [
        "You are a strict product relevance evaluator for an e-commerce price comparison tool.",
        "User's search query: ", user_query_for_relevance,
        "Product title found on website: ", product_title,
    ]
    if product_description and product_description != "N/A":
        prompt_parts.extend(["Product description (if available): ", product_description])

    prompt_parts.append(
        "Based *only* on the provided product title (and description, if available), "
        "is this product a DIRECT and RELEVANT match for the user's search query? "
        "Be very critical. For example, if user asks for 'iPhone 15 Pro', an 'iPhone 15 Pro Case' is NOT relevant. "
        "If user asks for 'Tynor wrist brace', a 'generic wrist support' might be less relevant than a 'Tynor branded wrist brace'. "
        "Answer with only 'yes' or 'no'."
    )
    prompt = "\n".join(prompt_parts)
    try:
        # genai should already be configured by get_standardized_query
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        gemini_response_text = response.text.strip().lower()
        print(f"Gemini relevance check for '{product_title}' vs '{user_query_for_relevance}': Response: '{gemini_response_text}'")
        return gemini_response_text == "yes"
    except Exception as e:
        print(f"Gemini API error during relevance check: {e}. Defaulting to not relevant.")
        return False

# --- Amazon Scraper (Selenium-based) ---
def scrape_amazon(search_query: str, pincode: str, api_key: str, original_user_query: str) -> dict:
    print(f"Amazon: Starting scrape for query: '{search_query}' with pincode: {pincode}")
    options = webdriver.ChromeOptions()
    user_agent = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    options.add_argument(f"user-agent={user_agent}")
    options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox") # Important for headless in many environments
    options.add_argument("--disable-dev-shm-usage") # Overcome limited resource problems
    options.add_argument("--log-level=3") # Suppress non-critical console logs

    driver = None
    print("Amazon: Initializing undetected-chromedriver...")
    try:
        driver = uc.Chrome(options=options, use_subprocess=True, advanced_elements_search=True) # Added advanced_elements_search
        print("Amazon: WebDriver initialized.")
        driver.get("https://www.amazon.in")
        print("Amazon: Navigated to homepage.")
        time.sleep(random.uniform(1.5, 2.5))

        print("Amazon: Attempting to set pincode...")
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "nav-global-location-popover-link"))).click()
        print("Amazon: Clicked location popover link.")
        time.sleep(random.uniform(1, 2)) # Wait for modal to open

        pincode_input_field_locator = (By.ID, "GLUXZipUpdateInput")
        pincode_input_field = WebDriverWait(driver, 10).until(EC.visibility_of_element_located(pincode_input_field_locator))
        print("Amazon: Pincode input field visible.")
        pincode_input_field.clear()
        pincode_input_field.send_keys(pincode)
        print(f"Amazon: Entered pincode {pincode}.")
        time.sleep(random.uniform(0.5, 1)) # Short pause for field to register input

        print("Amazon: Attempting to click pincode apply button (targeting INPUT element)...")
        apply_button_clicked = False
        pincode_apply_input_selector = "input.a-button-input[type='submit'][aria-labelledby='GLUXZipUpdate-announce']"

        try:
            apply_input_element = WebDriverWait(driver, 10).until(
                EC.visibility_of_element_located((By.CSS_SELECTOR, pincode_apply_input_selector))
            )
            print("Amazon: Pincode apply INPUT element is visible.")

            try:
                print("Amazon: Attempting JS click on INPUT...")
                driver.execute_script("arguments[0].scrollIntoView(true);", apply_input_element)
                time.sleep(0.5)
                driver.execute_script("arguments[0].click();", apply_input_element)
                print("Amazon: JS click on INPUT executed.")
                apply_button_clicked = True
            except Exception as e_js:
                print(f"Amazon: JS click on INPUT failed: {e_js}. Trying Selenium native click.")

            if not apply_button_clicked:
                try:
                    print("Amazon: Attempting Selenium native click on INPUT...")
                    apply_input_element = WebDriverWait(driver, 5).until(
                        EC.element_to_be_clickable((By.CSS_SELECTOR, pincode_apply_input_selector))
                    )
                    apply_input_element.click()
                    print("Amazon: Selenium native click on INPUT executed.")
                    apply_button_clicked = True
                except Exception as e_native:
                    print(f"Amazon: Selenium native click on INPUT failed: {e_native}. Trying ActionChains.")

            if not apply_button_clicked:
                try:
                    print("Amazon: Attempting ActionChains click on INPUT...")
                    apply_input_element = WebDriverWait(driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, pincode_apply_input_selector))
                    )
                    actions = webdriver.ActionChains(driver)
                    actions.move_to_element(apply_input_element).click().perform()
                    print("Amazon: ActionChains click on INPUT executed.")
                    apply_button_clicked = True
                except Exception as e_action:
                    print(f"Amazon: ActionChains click on INPUT failed: {e_action}.")

        except TimeoutException:
            print(f"Amazon: Pincode apply INPUT element ('{pincode_apply_input_selector}') not found or not visible within timeout.")
        except Exception as e_find:
            print(f"Amazon: Error finding the pincode apply INPUT element: {e_find}")

        if apply_button_clicked:
            try:
                WebDriverWait(driver, 10).until(EC.staleness_of(pincode_input_field))
                print(f"Amazon: Pincode {pincode} apply process completed. Modal closed (verified by input field staleness).")
            except TimeoutException:
                print(f"Amazon: Pincode modal did not close as expected after click. Pincode might not be set correctly.")
        else:
            print(f"Amazon: Pincode apply button click failed. Proceeding with search, but location may be incorrect.")

        time.sleep(random.uniform(1, 2.5))

        print(f"Amazon: Searching for product: '{search_query}'...")
        search_bar_locator = (By.ID, "twotabsearchtextbox")
        search_bar = WebDriverWait(driver, 10).until(EC.presence_of_element_located(search_bar_locator))
        search_bar.clear()
        search_bar.send_keys(search_query)
        search_bar.send_keys(Keys.ENTER)
        print("Amazon: Search submitted.")

        main_results_slot_locator = (By.CSS_SELECTOR, "div.s-main-slot")
        WebDriverWait(driver, 15).until(EC.presence_of_element_located(main_results_slot_locator))
        print("Amazon: Search results page loaded (s-main-slot found).")
        time.sleep(random.uniform(2.5, 4.5))

        soup = BeautifulSoup(driver.page_source, "html.parser")
        results = soup.select("div[data-component-type='s-search-result']", limit=10)
        print(f"Amazon: Found {len(results)} product cards in search results.")

        if not results:
            return {"title": "Not found", "price": "N/A", "url": "N/A", "status": "No product cards found on Amazon"}

        for i, item in enumerate(results[:5]):
            title, price_str, url_str = "Not found", "N/A", "N/A"
            print(f"Amazon: Processing item {i+1}")

            title_element = item.select_one('h2 span.a-text-normal[class*="a-size-"], h2 div.a-text-normal[class*="a-size-"]')
            if not title_element: title_element = item.select_one('h2 span.a-text-normal')
            if not title_element:
                h2_link = item.select_one('h2 > a')
                if h2_link: title_element = h2_link.select_one('span[dir="auto"], div[dir="auto"]')
            if title_element: title = title_element.get_text(strip=True)
            else:
                h2_tag = item.select_one('h2')
                if h2_tag: title = h2_tag.get_text(strip=True, separator=' ')

            if title != "Not found" and ("sponsored" in title.lower() or item.select_one('[data-component-type="sp-sponsored-result"]')):
                 if title.lower().startswith("sponsored") and len(title.split()) > 1: title = " ".join(title.split()[1:]).strip()
                 elif "sponsored" in title.lower() and len(title) < 20 : print(f"Amazon: Skipping item {i+1} (sponsored ad)."); continue

            if title == "Not found": print(f"Amazon: Title not found for item {i+1}.")

            price_whole_element = item.select_one('span.a-price-whole')
            price_fraction_element = item.select_one('span.a-price-fraction')
            if price_whole_element:
                price_str = price_whole_element.get_text(strip=True).replace(',', '')
                if price_fraction_element: price_str += price_fraction_element.get_text(strip=True)
            else:
                price_element_offscreen = item.select_one('span.a-price span.a-offscreen')
                if price_element_offscreen: price_str = price_element_offscreen.get_text(strip=True).replace('₹', '').replace(',', '')
            if price_str == "N/A": print(f"Amazon: Price not found for item {i+1}")

            url_element = item.select_one('h2 a.a-link-normal[href]')
            if not url_element: url_element = item.select_one('a.a-link-normal.s-no-outline[href]')
            if not url_element: url_element = item.select_one('a._link-normal_style_textLink__1_kLi[href]')
            if url_element:
                href_val = url_element['href']
                if not href_val.startswith("https://"): href_val = "https://www.amazon.in" + href_val
                url_str = href_val.split("?")[0].split("/ref=")[0]
            if url_str == "N/A": print(f"Amazon: URL not found for item {i+1}")

            print(f"Amazon: Item {i+1} Raw Extract - Title: '{title}', Price: '{price_str}', URL: '{url_str}'")

            if title and title != "Not found" and price_str != "N/A" and url_str != "N/A":
                if is_product_relevant_gemini(original_user_query, title, api_key):
                    print(f"Amazon: Gemini confirmed product '{title}' is relevant for original query '{original_user_query}'.")
                    return {"title": title, "price": price_str, "url": url_str, "status": "Available on Amazon"}
                else:
                    print(f"Amazon: Gemini deemed product '{title}' NOT relevant for original query '{original_user_query}'.")
            else:
                print(f"Amazon: Could not extract all required info for item {i+1} or title was empty.")

        return {"title": "Not found", "price": "N/A", "url": "N/A", "status": "Relevant product not found in top results on Amazon"}

    except TimeoutException as e:
        print(f"Amazon: Timeout during Amazon scraping: {e}")
        return {"title": "Error", "price": "N/A", "url": "N/A", "status": f"Timeout during Amazon scraping: {e}"}
    except Exception as e:
        print(f"Amazon: Error during Amazon scraping: {e}")
        return {"title": "Error", "price": "N/A", "url": "N/A", "status": f"Error during Amazon scraping: {e}"}
    finally:
        if driver:
            try:
                driver.quit()
                print("Amazon: WebDriver closed.")
            except OSError as e:
                if "The handle is invalid" in str(e) or (hasattr(e, 'winerror') and e.winerror == 6):
                    print("Amazon: Note: WebDriver quit with a minor OS error (handle invalid), browser likely already closed.")
                else: print(f"Amazon: Error during WebDriver quit: {e}")
            except Exception as e: print(f"Amazon: A general error occurred during WebDriver quit: {e}")

# --- Flipkart Scraper (Crawl4AI-based) ---
def extract_flipkart_data_gemini(markdown_content: str, original_query: str, api_key: str) -> List[ProductInfo]:
    prompt = f"""
Given the following Markdown content from a Flipkart search results page for the query '{original_query}',
extract the product title, price, and product page URL for up to the first 3-5 relevant products.
Ensure URLs are complete, prepending 'https://www.flipkart.com' if they are relative.
Present the output as a JSON list of objects, where each object has 'title', 'price', and 'url' keys.
The price should be a string containing only numbers and possibly a decimal point (e.g., "49990", "129.50"). Remove currency symbols (like ₹) and commas.
If a value is missing for a product, use "N/A".

Markdown content (first 15000 chars):
{markdown_content[:15000]}
"""
    print(f"Flipkart (Crawl4AI->Gemini): Sending content to Gemini for extraction. Original Query: {original_query}")
    response_text_for_error_log = "N/A"
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        response_text_for_error_log = response.text

        cleaned_response_text = response.text.strip()
        if cleaned_response_text.startswith("```json"): cleaned_response_text = cleaned_response_text[7:]
        if cleaned_response_text.startswith("```"): cleaned_response_text = cleaned_response_text[3:] # Handle case where only ``` is present
        if cleaned_response_text.endswith("```"): cleaned_response_text = cleaned_response_text[:-3]
        if cleaned_response_text.startswith("`") and cleaned_response_text.endswith("`"): cleaned_response_text = cleaned_response_text[1:-1]

        extracted_json = json.loads(cleaned_response_text)
        products = [ProductInfo(**p) for p in extracted_json]
        print(f"Flipkart (Crawl4AI->Gemini): Successfully extracted {len(products)} products via Gemini.")
        return products
    except Exception as e:
        print(f"Flipkart (Crawl4AI->Gemini): Error parsing Gemini response for data extraction: {e}. Raw response snippet: {response_text_for_error_log[:500]}")
        return []

async def scrape_flipkart_crawl4ai(search_query: str, pincode: str, api_key: str, original_user_query: str) -> dict:
    print(f"Flipkart (Crawl4AI): Starting scrape for query: '{search_query}' with pincode: {pincode}")

    search_url = f"https://www.flipkart.com/search?q={search_query.replace(' ', '+')}&pincode={pincode}"
    geo_config = GeolocationConfig(latitude=12.9716, longitude=77.5946, accuracy=1000.0)

    browser_config = BrowserConfig(
        headless=True, verbose=False,
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
    )
    run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, geolocation=geo_config, locale="en-IN")

    print(f"Flipkart (Crawl4AI): Crawling URL: {search_url} with geolocation for Bangalore.")

    async with AsyncWebCrawler(config=browser_config) as crawler:
        try:
            result = await crawler.arun(url=search_url, config=run_config)
        except Exception as e:
            error_str = str(e).lower()
            playwright_help_message = "Ensure Playwright browsers are installed by running 'crawl4ai-setup' or 'python -m playwright install --with-deps chromium' in your terminal."
            if "executable doesn't exist" in error_str or "playwright install" in error_str or "browser was not found" in error_str:
                status_msg = f"Playwright setup needed for Crawl4AI. {playwright_help_message} (Error: {e})"
            else: status_msg = f"Crawl4AI crawl error: {e}"
            print(f"Flipkart (Crawl4AI): {status_msg}")
            return {"title": "Error", "price": "N/A", "url": "N/A", "status": status_msg}

    if not result or not result.success or not result.markdown or not result.markdown.raw_markdown:
        status_msg = "Crawl4AI failed to retrieve content or got empty markdown."
        if result and result.error_message: status_msg += f" Error: {result.error_message}"
        elif result and hasattr(result, 'markdown') and result.markdown and not result.markdown.raw_markdown : status_msg += " (No markdown content generated)"
        print(f"Flipkart (Crawl4AI): {status_msg}")
        return {"title": "Not found", "price": "N/A", "url": "N/A", "status": status_msg}

    print(f"Flipkart (Crawl4AI): Crawled. Markdown length: {len(result.markdown.raw_markdown)}. Extracting with Gemini.")
    extracted_products: List[ProductInfo] = extract_flipkart_data_gemini(result.markdown.raw_markdown, original_user_query, api_key)

    if not extracted_products:
        print("Flipkart (Crawl4AI->Gemini): Gemini could not extract products from crawled content.")
        return {"title": "Not found", "price": "N/A", "url": "N/A", "status": "No products extracted from Flipkart by Gemini"}

    for product in extracted_products:
        if not product.title or product.title == "N/A": continue
        print(f"Flipkart (Crawl4AI): Checking relevance for extracted product: '{product.title}'")
        if is_product_relevant_gemini(original_user_query, product.title, api_key):
            print(f"Flipkart (Crawl4AI): Gemini confirmed product '{product.title}' is relevant.")
            return {"title": product.title, "price": product.price, "url": product.url, "status": "Available on Flipkart (via Crawl4AI)"}
        else:
            print(f"Flipkart (Crawl4AI): Product '{product.title}' NOT relevant by final Gemini check.")

    print("Flipkart (Crawl4AI): No relevant products after Gemini check from extracted data.")
    return {"title": "Not found", "price": "N/A", "url": "N/A", "status": "No relevant products found on Flipkart (Crawl4AI + Gemini)"}

def scrape_flipkart(search_query: str, pincode: str, api_key: str, original_user_query: str) -> dict:
    print(f"Flipkart (Crawl4AI): Initializing async run for query '{search_query}' (original: '{original_user_query}')")
    try:
        return asyncio.run(scrape_flipkart_crawl4ai(search_query, pincode, api_key, original_user_query))
    except RuntimeError as e:
        if " asyncio.run() cannot be called from a running event loop" in str(e):
            print("Flipkart (Crawl4AI): Detected running event loop. This script is designed for asyncio.run() from a sync context.")
            return {"title": "Error", "price": "N/A", "url": "N/A", "status": f"Async setup error: {e}"}
        print(f"Flipkart (Crawl4AI): A RuntimeError occurred: {e}")
        return {"title": "Error", "price": "N/A", "url": "N/A", "status": f"Runtime error in Crawl4AI async execution: {e}"}
    except Exception as e:
        error_str = str(e).lower()
        playwright_error_keywords = ["executable doesn't exist", "playwright install", "browser was not found", "chromium-"]
        playwright_help_message = "Ensure Playwright browsers are installed by running 'crawl4ai-setup' or 'python -m playwright install --with-deps chromium' in your terminal."

        if any(keyword in error_str for keyword in playwright_error_keywords):
            status_message = f"Playwright setup needed: Browsers not found. {playwright_help_message} (Error: {e})"
        else:
            status_message = f"General error in Crawl4AI async execution: {e}"
        print(f"Flipkart (Crawl4AI): {status_message}")
        return {"title": "Error", "price": "N/A", "url": "N/A", "status": status_message}

# --- Output Presentation ---
def parse_price(price_str: str) -> Optional[float]:
    if price_str is None or price_str == "N/A": return None
    try:
        cleaned_price = ''.join(filter(lambda x: x.isdigit() or x == '.', str(price_str).replace('₹', '').replace(',', '')))
        if not cleaned_price: return None
        if cleaned_price.count('.') > 1 or any(c.isalpha() for c in cleaned_price.replace('.', '', 1)): return None
        return float(cleaned_price)
    except ValueError: return None

def display_results(user_query: str, amazon_data: dict, flipkart_data: dict):
    print("\n---")
    print(f"Searching for: {user_query}")
    print("---\n")
    print("Amazon.in:")
    print(f"  Product: {amazon_data.get('title', 'N/A')}")
    print(f"  Price: {amazon_data.get('price', 'N/A')}")
    print(f"  Link: {amazon_data.get('url', 'N/A')}")
    print(f"  Status: {amazon_data.get('status', 'N/A')}\n")
    print("---")
    print("Flipkart.com:")
    print(f"  Product: {flipkart_data.get('title', 'N/A')}")
    print(f"  Price: {flipkart_data.get('price', 'N/A')}")
    print(f"  Link: {flipkart_data.get('url', 'N/A')}")
    print(f"  Status: {flipkart_data.get('status', 'N/A')}\n")

    amazon_price_str = amazon_data.get("price", "N/A")
    flipkart_price_str = flipkart_data.get("price", "N/A")
    amazon_status = amazon_data.get("status", "Status N/A")
    flipkart_status = flipkart_data.get("status", "Status N/A")
    amazon_price_float = parse_price(amazon_price_str)
    flipkart_price_float = parse_price(flipkart_price_str)

    recommendation = "Could not determine a recommendation based on available data."
    amz_available = "available" in amazon_status.lower() and amazon_price_float is not None
    flp_available = ("available" in flipkart_status.lower() or "via crawl4ai" in flipkart_status.lower()) and flipkart_price_float is not None

    if amz_available and flp_available:
        if amazon_price_float < flipkart_price_float: recommendation = f"Amazon.in is cheaper (Amazon: ₹{amazon_price_float:.2f}, Flipkart: ₹{flipkart_price_float:.2f})."
        elif flipkart_price_float < amazon_price_float: recommendation = f"Flipkart.com is cheaper (Flipkart: ₹{flipkart_price_float:.2f}, Amazon: ₹{amazon_price_float:.2f})."
        else: recommendation = f"Prices are similar (Amazon: ₹{amazon_price_float:.2f}, Flipkart: ₹{flipkart_price_float:.2f})."
    elif amz_available: recommendation = f"Product available on Amazon.in (₹{amazon_price_float:.2f}). Status on Flipkart.com: {flipkart_status} (Price: {flipkart_price_str})."
    elif flp_available: recommendation = f"Product available on Flipkart.com (₹{flipkart_price_float:.2f}). Status on Amazon.in: {amazon_status} (Price: {amazon_price_str})."
    else: recommendation = f"Price information unclear or product not found. Amazon: {amazon_status} (Price: {amazon_price_str}). Flipkart: {flipkart_status} (Price: {flipkart_price_str})."

    print("---")
    print(f"Recommendation: {recommendation}")
    print("---")

# --- Main Execution ---
if __name__ == "__main__":
    print("Smart Shopping List Optimizer MVP")
    print("="*30)
    api_key, default_pincode = None, None
    amazon_results = {"status": "Not Scraped yet", "title": "N/A", "price": "N/A", "url": "N/A"}
    flipkart_results = {"status": "Not Scraped yet", "title": "N/A", "price": "N/A", "url": "N/A"}
    user_query_main = ""
    try:
        api_key, default_pincode = load_environment_variables()
        user_query_main = get_user_product_query()
        standardized_query = get_standardized_query(user_query_main, api_key)
        print("-" * 30)
        print(f"Attempting to scrape Amazon for '{standardized_query}' with pincode {default_pincode}...")
        amazon_results = scrape_amazon(standardized_query, default_pincode, api_key, user_query_main)
        print("-" * 30)
        print(f"Attempting to scrape Flipkart for '{standardized_query}' with pincode {default_pincode}...")
        flipkart_results = scrape_flipkart(standardized_query, default_pincode, api_key, user_query_main)
        print("-" * 30)
    except ValueError as e: print(f"Configuration Error: {e}")
    except Exception as e:
        import traceback
        print(f"An unexpected error occurred in the main execution block: {e}")
        print(traceback.format_exc())
    finally:
        display_results(user_query_main if user_query_main else "N/A", amazon_results, flipkart_results)
        print("\nExiting Optimizer.")
