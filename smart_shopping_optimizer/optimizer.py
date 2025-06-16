import os
import google.generativeai as genai
from dotenv import load_dotenv
import time
import random
import json
import asyncio

# Selenium and BeautifulSoup for Amazon
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import TimeoutException, NoSuchElementException, ElementClickInterceptedException
from bs4 import BeautifulSoup
import undetected_chromedriver as uc

# Crawl4AI imports for Flipkart & Zepto
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode, GeolocationConfig

# Pydantic model for structured data extraction
from pydantic import BaseModel, Field
from typing import List, Optional

# --- Global Platform Definitions ---
SUPPORTED_PLATFORMS = {
    "1": "Amazon.in",
    "2": "Flipkart.com",
    "3": "Zepto",
    "4": "Swiggy Instamart",
    "5": "Blinkit",
}
AVAILABLE_SCRAPERS = ["Amazon.in", "Flipkart.com"]
EXPERIMENTAL_SCRAPERS = ["Zepto", "Swiggy Instamart", "Blinkit"] # Platforms for research/crawl testing

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

def get_platform_selection() -> List[str]:
    print("\nSelect platforms to scrape:")

    current_choices = {}
    all_available_names_for_A_option = []

    # Populate current_choices and identify fully available scrapers
    for key, name in SUPPORTED_PLATFORMS.items():
        if name in AVAILABLE_SCRAPERS or name in EXPERIMENTAL_SCRAPERS:
            current_choices[key] = name
            if name in AVAILABLE_SCRAPERS:
                all_available_names_for_A_option.append(name)

    # Display choices
    for key, name in current_choices.items():
        status_label = ""
        if name in EXPERIMENTAL_SCRAPERS and name not in AVAILABLE_SCRAPERS: # Ensure it's only experimental
            status_label = "(Experimental)" # Updated label
        elif name not in AVAILABLE_SCRAPERS and name not in EXPERIMENTAL_SCRAPERS: # Should ideally not be reached if lists are correct
             status_label = "(Not Yet Implemented)"
        print(f"  {key}. {name} {status_label}")

    all_option_prompt = f"All Fully Available ({', '.join(all_available_names_for_A_option) if all_available_names_for_A_option else 'None'})"
    print(f"  A. {all_option_prompt}")

    selected_platforms = []
    while True:
        prompt_input_keys = [k for k,v in current_choices.items()] # All selectable keys
        choice_str = input(f"Enter numbers (e.g., {','.join(prompt_input_keys)}), or 'A' for ({', '.join(all_available_names_for_A_option)}): ").strip().upper()

        if not choice_str:
            print("Selection cannot be empty. Please try again.")
            continue

        chosen_keys = [c.strip() for c in choice_str.split(',')]
        temp_selection = set()
        valid_selection = True

        if 'A' in chosen_keys:
            for platform_name in all_available_names_for_A_option:
                temp_selection.add(platform_name)
            # Allow 'A' to be combined with specific experimental platform numbers
            # chosen_keys.remove('A') # No longer remove, process all keys

        for key in chosen_keys:
            if key == 'A': continue

            if key in current_choices:
                # Allow selection of experimental scrapers by their number
                if current_choices[key] in AVAILABLE_SCRAPERS or current_choices[key] in EXPERIMENTAL_SCRAPERS:
                    temp_selection.add(current_choices[key])
                else: # Platform listed in SUPPORTED_PLATFORMS but not in AVAILABLE or EXPERIMENTAL
                    print(f"Notice: {current_choices[key]} is not fully implemented or available for selection yet.")
                    # Do not add to temp_selection or mark as invalid, just inform and skip.
            else:
                print(f"Invalid choice: {key}. Please select from the available numbers or 'A'.")
                valid_selection = False
                temp_selection.clear()
                break

        if valid_selection and temp_selection:
            selected_platforms = sorted(list(temp_selection), key=lambda x: [k_sort for k_sort,v_sort in SUPPORTED_PLATFORMS.items() if v_sort == x][0])
            break
        elif valid_selection and not temp_selection and 'A' not in chosen_keys :
             print("No valid platforms selected. Please try again.")
        elif not valid_selection:
            pass

    if not selected_platforms and 'A' in chosen_keys and not all_available_names_for_A_option:
        print("No fully available platforms to select with 'A'. Please choose specific numbers if available.")
    elif selected_platforms:
        print(f"You selected: {', '.join(selected_platforms)}")
    else:
        print("No platforms were selected to scrape.") # Should ideally not be reached if loop logic is correct

    return selected_platforms

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
        if standardized.startswith("```") and standardized.endswith("```"):
            standardized = standardized[3:-3].strip()
        if standardized.lower().startswith("json"):
             standardized = standardized[4:].strip()
        if standardized.startswith("`") and standardized.endswith("`"):
            standardized = standardized[1:-1].strip()
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
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    driver = None
    print("Amazon: Initializing undetected-chromedriver...")
    try:
        driver = uc.Chrome(options=options, use_subprocess=True, advanced_elements_search=True)
        print("Amazon: WebDriver initialized.")
        driver.get("https://www.amazon.in")
        print("Amazon: Navigated to homepage.")
        time.sleep(random.uniform(1.5, 2.5))
        print("Amazon: Attempting to set pincode...")
        WebDriverWait(driver, 10).until(EC.element_to_be_clickable((By.ID, "nav-global-location-popover-link"))).click()
        print("Amazon: Clicked location popover link.")
        time.sleep(random.uniform(1, 2))
        pincode_input_field_locator = (By.ID, "GLUXZipUpdateInput")
        pincode_input_field = WebDriverWait(driver, 10).until(EC.visibility_of_element_located(pincode_input_field_locator))
        print("Amazon: Pincode input field visible.")
        pincode_input_field.clear(); pincode_input_field.send_keys(pincode)
        print(f"Amazon: Entered pincode {pincode}.")
        time.sleep(random.uniform(0.5, 1))
        print("Amazon: Attempting to click pincode apply button (targeting INPUT element)...")
        apply_button_clicked = False
        pincode_apply_input_selector = "input.a-button-input[type='submit'][aria-labelledby='GLUXZipUpdate-announce']"
        try:
            apply_input_element = WebDriverWait(driver, 10).until(EC.visibility_of_element_located((By.CSS_SELECTOR, pincode_apply_input_selector)))
            print("Amazon: Pincode apply INPUT element is visible.")
            try:
                print("Amazon: Attempting JS click on INPUT...")
                driver.execute_script("arguments[0].scrollIntoView(true);", apply_input_element); time.sleep(0.5)
                driver.execute_script("arguments[0].click();", apply_input_element)
                print("Amazon: JS click on INPUT executed."); apply_button_clicked = True
            except Exception as e_js:
                print(f"Amazon: JS click on INPUT failed: {e_js}. Trying Selenium native click.")
                if not apply_button_clicked:
                    try:
                        print("Amazon: Attempting Selenium native click on INPUT...")
                        apply_input_element = WebDriverWait(driver, 5).until(EC.element_to_be_clickable((By.CSS_SELECTOR, pincode_apply_input_selector)))
                        apply_input_element.click()
                        print("Amazon: Selenium native click on INPUT executed."); apply_button_clicked = True
                    except Exception as e_native:
                        print(f"Amazon: Selenium native click on INPUT failed: {e_native}. Trying ActionChains.")
                        if not apply_button_clicked:
                            try:
                                print("Amazon: Attempting ActionChains click on INPUT...")
                                apply_input_element = WebDriverWait(driver, 5).until(EC.presence_of_element_located((By.CSS_SELECTOR, pincode_apply_input_selector)))
                                actions = webdriver.ActionChains(driver); actions.move_to_element(apply_input_element).click().perform()
                                print("Amazon: ActionChains click on INPUT executed."); apply_button_clicked = True
                            except Exception as e_action: print(f"Amazon: ActionChains click on INPUT failed: {e_action}.")
        except TimeoutException: print(f"Amazon: Pincode apply INPUT element ('{pincode_apply_input_selector}') not found or not visible within timeout.")
        except Exception as e_find: print(f"Amazon: Error finding the pincode apply INPUT element: {e_find}")
        if apply_button_clicked:
            WebDriverWait(driver, 10).until(EC.staleness_of(pincode_input_field))
            print(f"Amazon: Pincode {pincode} apply process completed. Modal likely closed.")
        else:
            print(f"Amazon: Pincode apply button click potentially failed. Proceeding with search anyway.")
            try: driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE); print("Amazon: Sent ESCAPE key."); time.sleep(0.5)
            except: pass
        time.sleep(random.uniform(1, 2.5))
        print(f"Amazon: Searching for product: '{search_query}'...")
        search_bar_locator = (By.ID, "twotabsearchtextbox")
        search_bar = WebDriverWait(driver, 10).until(EC.presence_of_element_located(search_bar_locator))
        search_bar.clear(); search_bar.send_keys(search_query); search_bar.send_keys(Keys.ENTER)
        print("Amazon: Search submitted.")
        main_results_slot_locator = (By.CSS_SELECTOR, "div.s-main-slot")
        WebDriverWait(driver, 15).until(EC.presence_of_element_located(main_results_slot_locator))
        print("Amazon: Search results page loaded (s-main-slot found)."); time.sleep(random.uniform(2.5, 4.5))
        soup = BeautifulSoup(driver.page_source, "html.parser")
        results = soup.select("div[data-component-type='s-search-result']", limit=10)
        print(f"Amazon: Found {len(results)} product cards in search results.")
        if not results: return {"title": "Not found", "price": "N/A", "url": "N/A", "status": "No product cards found on Amazon"}
        for i, item in enumerate(results[:5]):
            title, price_str, url_str = "Not found", "N/A", "N/A"
            print(f"Amazon: Processing item {i+1}")
            title_element = item.select_one('h2 span.a-text-normal[class*="a-size-"], h2 div.a-text-normal[class*="a-size-"]')
            if not title_element: title_element = item.select_one('h2 span.a-text-normal')
            if not title_element:
                h2_link = item.select_one('h2 > a');
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
            else: print(f"Amazon: Could not extract all required info for item {i+1} or title was empty.")
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
                driver.quit(); print("Amazon: WebDriver closed.")
            except OSError as e:
                if "The handle is invalid" in str(e) or (hasattr(e, 'winerror') and e.winerror == 6): print("Amazon: Note: WebDriver quit with a minor OS error (handle invalid), browser likely already closed.")
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
        if cleaned_response_text.startswith("```"): cleaned_response_text = cleaned_response_text[3:]
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
    browser_config = BrowserConfig(headless=True, verbose=False, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
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
        else: status_message = f"General error in Crawl4AI async execution: {e}"
        print(f"Flipkart (Crawl4AI): {status_message}")
        return {"title": "Error", "price": "N/A", "url": "N/A", "status": status_message}

# --- Zepto Scraper (Initial Crawl4AI Structure) ---
async def scrape_zepto_crawl4ai(search_query: str, pincode: str, api_key: str, original_user_query: str) -> dict:
    print(f"Zepto (Crawl4AI): Starting scrape for query: '{search_query}' with pincode: {pincode}")
    search_slug = search_query.lower().replace(' ', '-')
    search_url = f"https://www.zeptonow.com/search/{search_slug}"
    print(f"Zepto (Crawl4AI): Target URL: {search_url}")
    geo_config = GeolocationConfig(latitude=12.9716, longitude=77.5946, accuracy=1000.0) # Bangalore
    browser_config = BrowserConfig(headless=True, verbose=False, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, geolocation=geo_config, locale="en-IN")
    print(f"Zepto (Crawl4AI): Attempting to crawl URL: {search_url} with geolocation for Bangalore.")
    async with AsyncWebCrawler(config=browser_config) as crawler:
        try:
            result = await crawler.arun(url=search_url, config=run_config)
        except Exception as e:
            error_str = str(e).lower()
            playwright_help_message = "Ensure Playwright browsers are installed by running 'crawl4ai-setup' or 'python -m playwright install --with-deps chromium' in your terminal."
            if "executable doesn't exist" in error_str or "playwright install" in error_str or "browser was not found" in error_str:
                status_msg = f"Playwright setup needed for Crawl4AI (Zepto). {playwright_help_message} (Error: {e})"
            else: status_msg = f"Crawl4AI crawl error (Zepto): {e}"
            print(f"Zepto (Crawl4AI): {status_msg}")
            return {"title": "Error", "price": "N/A", "url": "N/A", "status": status_msg}
    if not result or not result.success:
        status_msg = f"Crawl4AI failed to retrieve content from Zepto for URL: {search_url}."
        if hasattr(result, 'status_code') and result.status_code:
            status_msg += f" Status Code: {result.status_code}."
        if result and result.error_message:
            status_msg += f" Error: {result.error_message}."
        if result and result.content and ("Access Denied" in result.content or "Something went wrong" in result.content or "rate limit" in result.content.lower()):
            status_msg += " (Potential block or error page detected by Zepto)."
        print(f"Zepto (Crawl4AI): {status_msg}")
        return {"title": "Error", "price": "N/A", "url": search_url, "status": status_msg}
    if not result.markdown or not result.markdown.raw_markdown:
        status_msg = f"Crawl4AI retrieved content from Zepto for URL: {search_url}, but no Markdown was generated."
        if hasattr(result, 'status_code') and result.status_code:
            status_msg += f" Status Code: {result.status_code}."
        if result.content:
             status_msg += " (HTML content was present but could not be converted to markdown by Crawl4AI)."
             print(f"Zepto (Crawl4AI): HTML content snippet (first 500 chars for {search_url}): {result.content[:500]}")
        else:
            status_msg += " (No HTML content found either)."
        print(f"Zepto (Crawl4AI): {status_msg}")
        return {"title": "Not found", "price": "N/A", "url": search_url, "status": status_msg}
    print(f"Zepto (Crawl4AI): Successfully crawled. Markdown length: {len(result.markdown.raw_markdown)}.")
    # print("Zepto (Crawl4AI): Markdown snippet (first 1000 chars):") # Optional: for debugging
    # print(result.markdown.raw_markdown[:1000])

    extracted_products: List[ProductInfo] = extract_zepto_data_gemini(result.markdown.raw_markdown, original_user_query, api_key)
    if not extracted_products:
        print("Zepto (Crawl4AI->Gemini): Gemini could not extract products from crawled content.")
        return {"title": "Not found", "price": "N/A", "url": search_url, "status": "No products extracted from Zepto by Gemini (Crawl4AI)"}

    for product in extracted_products:
        if not product.title or product.title == "N/A":
            print("Zepto (Crawl4AI): Skipping product with no title.")
            continue
        print(f"Zepto (Crawl4AI): Checking relevance for extracted product: '{product.title}'")
        if is_product_relevant_gemini(original_user_query, product.title, api_key):
            print(f"Zepto (Crawl4AI): Gemini confirmed product '{product.title}' is relevant.")
            return {"title": product.title, "price": product.price, "url": product.url, "status": "Available on Zepto (via Crawl4AI)"}
        else:
            print(f"Zepto (Crawl4AI): Product '{product.title}' NOT relevant by final Gemini check.")

    print("Zepto (Crawl4AI): No relevant products after Gemini check from extracted data.")
    return {"title": "Not found", "price": "N/A", "url": search_url, "status": "No relevant products found on Zepto (Crawl4AI + Gemini)"}

def scrape_zepto(search_query: str, pincode: str, api_key: str, original_user_query: str) -> dict:
    print(f"Zepto (Crawl4AI): Initializing async run for query '{search_query}' (original: '{original_user_query}')")
    try:
        return asyncio.run(scrape_zepto_crawl4ai(search_query, pincode, api_key, original_user_query))
    except RuntimeError as e:
        if " asyncio.run() cannot be called from a running event loop" in str(e):
            print("Zepto (Crawl4AI): Detected running event loop. This script is designed for asyncio.run() from a sync context.")
            return {"title": "Error", "price": "N/A", "url": "N/A", "status": f"Async setup error (Zepto): {e}"}
        print(f"Zepto (Crawl4AI): A RuntimeError occurred: {e}")
        return {"title": "Error", "price": "N/A", "url": "N/A", "status": f"Runtime error in Crawl4AI async execution (Zepto): {e}"}
    except Exception as e:
        error_str = str(e).lower()
        playwright_error_keywords = ["executable doesn't exist", "playwright install", "browser was not found", "chromium-"]
        playwright_help_message = "Ensure Playwright browsers are installed by running 'crawl4ai-setup' or 'python -m playwright install --with-deps chromium' in your terminal."
        if any(keyword in error_str for keyword in playwright_error_keywords):
            status_message = f"Playwright setup needed for Crawl4AI (Zepto). {playwright_help_message} (Error: {e})"
        else: status_message = f"General error in Crawl4AI async execution (Zepto): {e}"
        print(f"Zepto (Crawl4AI): {status_message}")
        return {"title": "Error", "price": "N/A", "url": "N/A", "status": status_message}

# --- Swiggy Instamart Scraper (Initial Crawl4AI Structure) ---
async def scrape_swiggy_instamart_crawl4ai(search_query: str, pincode: str, api_key: str, original_user_query: str) -> dict:
    print(f"Swiggy Instamart (Crawl4AI): Starting scrape for query: '{search_query}' with pincode: {pincode}")
    # Note: Pincode is not directly used in Swiggy Instamart search URLs typically, location is handled by session/browser context.
    # Swiggy Instamart's search URL structure might change. This is a best guess.
    search_slug = search_query.lower().replace(' ', '-')
    search_url = f"https://instamart.swiggy.com/search/{search_slug}" # Or potentially www.swiggy.com/instamart/search/
    print(f"Swiggy Instamart (Crawl4AI): Target URL: {search_url}")

    # Geolocation might be important for Swiggy Instamart to show relevant stores/availability
    geo_config = GeolocationConfig(latitude=12.9716, longitude=77.5946, accuracy=1000.0) # Bangalore
    browser_config = BrowserConfig(headless=True, verbose=False, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, geolocation=geo_config, locale="en-IN")

    print(f"Swiggy Instamart (Crawl4AI): Attempting to crawl URL: {search_url} with geolocation for Bangalore.")
    async with AsyncWebCrawler(config=browser_config) as crawler:
        try:
            result = await crawler.arun(url=search_url, config=run_config)
        except Exception as e:
            error_str = str(e).lower()
            playwright_help_message = "Ensure Playwright browsers are installed by running 'crawl4ai-setup' or 'python -m playwright install --with-deps chromium' in your terminal."
            if "executable doesn't exist" in error_str or "playwright install" in error_str or "browser was not found" in error_str:
                status_msg = f"Playwright setup needed for Crawl4AI (Swiggy Instamart). {playwright_help_message} (Error: {e})"
            else: status_msg = f"Crawl4AI crawl error (Swiggy Instamart): {e}"
            print(f"Swiggy Instamart (Crawl4AI): {status_msg}")
            return {"title": "Error", "price": "N/A", "url": "N/A", "status": status_msg}

    if not result or not result.success:
        status_msg = f"Crawl4AI failed to retrieve content from Swiggy Instamart for URL: {search_url}."
        if hasattr(result, 'status_code') and result.status_code:
            status_msg += f" Status Code: {result.status_code}."
        if result and result.error_message:
            status_msg += f" Error: {result.error_message}."
        # Check for common blocking patterns in content if available
        if result and result.content and ("Access Denied" in result.content or "Something went wrong" in result.content or "Looks like you are lost" in result.content or "rate limit" in result.content.lower()):
            status_msg += " (Potential block or error page detected by Swiggy Instamart)."
        print(f"Swiggy Instamart (Crawl4AI): {status_msg}")
        return {"title": "Error", "price": "N/A", "url": search_url, "status": status_msg}

    if not result.markdown or not result.markdown.raw_markdown:
        status_msg = f"Crawl4AI retrieved content from Swiggy Instamart for URL: {search_url}, but no Markdown was generated."
        if hasattr(result, 'status_code') and result.status_code:
            status_msg += f" Status Code: {result.status_code}."
        if result.content:
             status_msg += " (HTML content was present but could not be converted to markdown by Crawl4AI)."
             print(f"Swiggy Instamart (Crawl4AI): HTML content snippet (first 500 chars for {search_url}): {result.content[:500]}")
        else:
            status_msg += " (No HTML content found either)."
        print(f"Swiggy Instamart (Crawl4AI): {status_msg}")
        return {"title": "Not found", "price": "N/A", "url": search_url, "status": status_msg}

    print(f"Swiggy Instamart (Crawl4AI): Successfully crawled. Markdown length: {len(result.markdown.raw_markdown)}.")
    # print("Swiggy Instamart (Crawl4AI): Markdown snippet (first 1000 chars):") # Optional: for debugging
    # print(result.markdown.raw_markdown[:1000]) # Log a snippet for initial review

    extracted_products: List[ProductInfo] = extract_swiggy_data_gemini(result.markdown.raw_markdown, original_user_query, api_key)
    if not extracted_products:
        print("Swiggy Instamart (Crawl4AI->Gemini): Gemini could not extract products.")
        return {"title": "Not found", "price": "N/A", "url": search_url, "status": "No products extracted from Swiggy Instamart by Gemini"}

    for product in extracted_products:
        if not product.title or product.title == "N/A": continue
        print(f"Swiggy Instamart (Crawl4AI): Checking relevance for extracted product: '{product.title}'")
        if is_product_relevant_gemini(original_user_query, product.title, api_key):
            print(f"Swiggy Instamart (Crawl4AI): Gemini confirmed product '{product.title}' is relevant.")
            return {"title": product.title, "price": product.price, "url": product.url, "status": "Available on Swiggy Instamart (via Crawl4AI)"}
        else:
            print(f"Swiggy Instamart (Crawl4AI): Product '{product.title}' NOT relevant by final Gemini check.")

    print("Swiggy Instamart (Crawl4AI): No relevant products after Gemini check from extracted data.")
    return {"title": "Not found", "price": "N/A", "url": search_url, "status": "No relevant products found on Swiggy Instamart (Crawl4AI + Gemini)"}

# --- Helper function to extract Zepto data using Gemini ---
def extract_zepto_data_gemini(markdown_content: str, original_query: str, api_key: str) -> List[ProductInfo]:
    prompt = f"""
Given the following Markdown content from a Zepto search results page for the query '{original_query}',
extract the product title, price, and product page URL for up to the first 3-5 relevant products.
Ensure URLs are complete. Zepto URLs might be relative; if so, prepend 'https://www.zeptonow.com'.
Present the output as a JSON list of objects, where each object has 'title', 'price', and 'url' keys.
The price should be a string containing only numbers and possibly a decimal point (e.g., "120", "55.50"). Remove currency symbols (like ₹) and commas.
If a value is missing for a product, use "N/A".

Markdown content (first 15000 chars):
{markdown_content[:15000]}
"""
    print(f"Zepto (Crawl4AI->Gemini): Sending content to Gemini for extraction. Original Query: {original_query}")
    response_text_for_error_log = "N/A"
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        response_text_for_error_log = response.text
        cleaned_response_text = response.text.strip()
        if cleaned_response_text.startswith("```json"): cleaned_response_text = cleaned_response_text[7:]
        if cleaned_response_text.startswith("```"): cleaned_response_text = cleaned_response_text[3:]
        if cleaned_response_text.endswith("```"): cleaned_response_text = cleaned_response_text[:-3]
        if cleaned_response_text.startswith("`") and cleaned_response_text.endswith("`"): cleaned_response_text = cleaned_response_text[1:-1]
        extracted_json = json.loads(cleaned_response_text)
        # Ensure URLs are absolute
        for item in extracted_json:
            if 'url' in item and item['url'] != "N/A" and not item['url'].startswith('http'):
                item['url'] = f"https://www.zeptonow.com{item['url'] if item['url'].startswith('/') else '/' + item['url']}"
        products = [ProductInfo(**p) for p in extracted_json]
        print(f"Zepto (Crawl4AI->Gemini): Successfully extracted {len(products)} products via Gemini.")
        return products
    except Exception as e:
        print(f"Zepto (Crawl4AI->Gemini): Error parsing Gemini response for data extraction: {e}. Raw response snippet: {response_text_for_error_log[:500]}")
        return []

# --- Helper function to extract Swiggy Instamart data using Gemini ---
def extract_swiggy_data_gemini(markdown_content: str, original_query: str, api_key: str) -> List[ProductInfo]:
    prompt = f"""
You are an expert data extractor. Given the following Markdown content, which is the result of a web crawl of a Swiggy Instamart search results page for the query '{original_query}',
your task is to extract product information.

Identify up to the first 3-5 relevant product listings. For each product, extract:
1.  'title': The name or title of the product.
2.  'price': The price of the product. This should be a string containing only numbers and possibly a decimal point (e.g., "120", "55.50"). Remove currency symbols (like ₹) and commas.
3.  'url': The product page URL. Ensure URLs are complete. Swiggy Instamart URLs might be relative; if so, prepend 'https://instamart.swiggy.com'.

Look for patterns that typically represent product items, such as list items, item cards, or distinct sections in the markdown.
The title, price, and URL for a single product are usually found close to each other.

Present the output as a JSON list of objects. Each object should have 'title', 'price', and 'url' keys.
If a value for a specific field (e.g., price or URL) is missing for a product, use the string "N/A" for that field.
If no products can be reliably extracted, return an empty list.

Markdown content (first 15000 chars):
{markdown_content[:15000]}
"""
    print(f"Swiggy Instamart (Crawl4AI->Gemini): Sending content to Gemini for extraction. Original Query: {original_query}")
    response_text_for_error_log = "N/A"
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        response_text_for_error_log = response.text
        cleaned_response_text = response.text.strip()
        if cleaned_response_text.startswith("```json"): cleaned_response_text = cleaned_response_text[7:]
        if cleaned_response_text.startswith("```"): cleaned_response_text = cleaned_response_text[3:]
        if cleaned_response_text.endswith("```"): cleaned_response_text = cleaned_response_text[:-3]
        if cleaned_response_text.startswith("`") and cleaned_response_text.endswith("`"): cleaned_response_text = cleaned_response_text[1:-1]
        extracted_json = json.loads(cleaned_response_text)
        # Ensure URLs are absolute
        for item in extracted_json:
            if 'url' in item and item['url'] != "N/A" and not item['url'].startswith('http'):
                item['url'] = f"https://instamart.swiggy.com{item['url'] if item['url'].startswith('/') else '/' + item['url']}"
        products = [ProductInfo(**p) for p in extracted_json]
        print(f"Swiggy Instamart (Crawl4AI->Gemini): Successfully extracted {len(products)} products via Gemini.")
        return products
    except Exception as e:
        print(f"Swiggy Instamart (Crawl4AI->Gemini): Error parsing Gemini response for data extraction: {e}. Raw response snippet: {response_text_for_error_log[:500]}")
        return []

def scrape_swiggy_instamart(search_query: str, pincode: str, api_key: str, original_user_query: str) -> dict:
    print(f"Swiggy Instamart (Crawl4AI): Initializing async run for query '{search_query}' (original: '{original_user_query}')")
    try:
        return asyncio.run(scrape_swiggy_instamart_crawl4ai(search_query, pincode, api_key, original_user_query))
    except RuntimeError as e:
        if " asyncio.run() cannot be called from a running event loop" in str(e):
            print("Swiggy Instamart (Crawl4AI): Detected running event loop. This script is designed for asyncio.run() from a sync context.")
            return {"title": "Error", "price": "N/A", "url": "N/A", "status": f"Async setup error (Swiggy Instamart): {e}"}
        print(f"Swiggy Instamart (Crawl4AI): A RuntimeError occurred: {e}")
        return {"title": "Error", "price": "N/A", "url": "N/A", "status": f"Runtime error in Crawl4AI async execution (Swiggy Instamart): {e}"}
    except Exception as e:
        error_str = str(e).lower()
        playwright_error_keywords = ["executable doesn't exist", "playwright install", "browser was not found", "chromium-"]
        playwright_help_message = "Ensure Playwright browsers are installed by running 'crawl4ai-setup' or 'python -m playwright install --with-deps chromium' in your terminal."
        if any(keyword in error_str for keyword in playwright_error_keywords):
            status_message = f"Playwright setup needed for Crawl4AI (Swiggy Instamart). {playwright_help_message} (Error: {e})"
        else: status_message = f"General error in Crawl4AI async execution (Swiggy Instamart): {e}"
        print(f"Swiggy Instamart (Crawl4AI): {status_message}")
        return {"title": "Error", "price": "N/A", "url": "N/A", "status": status_message}

# --- Blinkit Scraper (Initial Crawl4AI Structure) ---
async def scrape_blinkit_crawl4ai(search_query: str, pincode: str, api_key: str, original_user_query: str) -> dict:
    print(f"Blinkit (Crawl4AI): Starting scrape for query: '{search_query}' with pincode: {pincode}")
    # Blinkit's search URL might vary. Using a common pattern.
    # Pincode is often handled by website's location services, not directly in basic search URL.
    search_slug = search_query.lower().replace(' ', '-') # Basic slug, Blinkit might have specific slugification
    search_url = f"https://blinkit.com/s/?q={search_slug}"
    print(f"Blinkit (Crawl4AI): Target URL: {search_url}")

    geo_config = GeolocationConfig(latitude=12.9716, longitude=77.5946, accuracy=1000.0) # Bangalore
    browser_config = BrowserConfig(headless=True, verbose=False, user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36")
    run_config = CrawlerRunConfig(cache_mode=CacheMode.BYPASS, geolocation=geo_config, locale="en-IN")

    print(f"Blinkit (Crawl4AI): Attempting to crawl URL: {search_url} with geolocation for Bangalore.")
    async with AsyncWebCrawler(config=browser_config) as crawler:
        try:
            result = await crawler.arun(url=search_url, config=run_config)
        except Exception as e:
            error_str = str(e).lower()
            playwright_help_message = "Ensure Playwright browsers are installed by running 'crawl4ai-setup' or 'python -m playwright install --with-deps chromium' in your terminal."
            if "executable doesn't exist" in error_str or "playwright install" in error_str or "browser was not found" in error_str:
                status_msg = f"Playwright setup needed for Crawl4AI (Blinkit). {playwright_help_message} (Error: {e})"
            else: status_msg = f"Crawl4AI crawl error (Blinkit): {e}"
            print(f"Blinkit (Crawl4AI): {status_msg}")
            return {"title": "Error", "price": "N/A", "url": "N/A", "status": status_msg}

    if not result or not result.success:
        status_msg = f"Crawl4AI failed to retrieve content from Blinkit for URL: {search_url}."
        if hasattr(result, 'status_code') and result.status_code:
            status_msg += f" Status Code: {result.status_code}."
        if result and result.error_message:
            status_msg += f" Error: {result.error_message}."
        if result and result.content and ("Access Denied" in result.content or "Something went wrong" in result.content or "rate limit" in result.content.lower() or "not available in your area" in result.content.lower()):
            status_msg += " (Potential block, error page, or geo-restriction detected by Blinkit)."
        print(f"Blinkit (Crawl4AI): {status_msg}")
        return {"title": "Error", "price": "N/A", "url": search_url, "status": status_msg}

    if not result.markdown or not result.markdown.raw_markdown:
        status_msg = f"Crawl4AI retrieved content from Blinkit for URL: {search_url}, but no Markdown was generated."
        if hasattr(result, 'status_code') and result.status_code:
            status_msg += f" Status Code: {result.status_code}."
        if result.content:
             status_msg += " (HTML content was present but could not be converted to markdown by Crawl4AI)."
             print(f"Blinkit (Crawl4AI): HTML content snippet (first 500 chars for {search_url}): {result.content[:500]}")
        else:
            status_msg += " (No HTML content found either)."
        print(f"Blinkit (Crawl4AI): {status_msg}")
        return {"title": "Not found", "price": "N/A", "url": search_url, "status": status_msg}

    print(f"Blinkit (Crawl4AI): Successfully crawled. Markdown length: {len(result.markdown.raw_markdown)}.")
    # print("Blinkit (Crawl4AI): Markdown snippet (first 1000 chars):") # Optional: for debugging
    # print(result.markdown.raw_markdown[:1000])

    extracted_products: List[ProductInfo] = extract_blinkit_data_gemini(result.markdown.raw_markdown, original_user_query, api_key)
    if not extracted_products:
        print("Blinkit (Crawl4AI->Gemini): Gemini could not extract products.")
        return {"title": "Not found", "price": "N/A", "url": search_url, "status": "No products extracted from Blinkit by Gemini"}

    for product in extracted_products:
        if not product.title or product.title == "N/A": continue
        print(f"Blinkit (Crawl4AI): Checking relevance for extracted product: '{product.title}'")
        if is_product_relevant_gemini(original_user_query, product.title, api_key):
            print(f"Blinkit (Crawl4AI): Gemini confirmed product '{product.title}' is relevant.")
            return {"title": product.title, "price": product.price, "url": product.url, "status": "Available on Blinkit (via Crawl4AI)"}
        else:
            print(f"Blinkit (Crawl4AI): Product '{product.title}' NOT relevant by final Gemini check.")

    print("Blinkit (Crawl4AI): No relevant products after Gemini check from extracted data.")
    return {"title": "Not found", "price": "N/A", "url": search_url, "status": "No relevant products found on Blinkit (Crawl4AI + Gemini)"}

# --- Helper function to extract Blinkit data using Gemini ---
def extract_blinkit_data_gemini(markdown_content: str, original_query: str, api_key: str) -> List[ProductInfo]:
    prompt = f"""
You are an expert data extractor. Given the following Markdown content, which is the result of a web crawl of a Blinkit search results page for the query '{original_query}',
your task is to extract product information.

Identify up to the first 3-5 relevant product listings. For each product, extract:
1.  'title': The name or title of the product.
2.  'price': The price of the product. This should be a string containing only numbers and possibly a decimal point (e.g., "100", "45.50"). Remove currency symbols (like ₹) and commas.
3.  'url': The product page URL. Ensure URLs are complete. Blinkit URLs might be relative; if so, prepend 'https://blinkit.com'.

Look for patterns that typically represent product items, such as list items, item cards, or distinct sections in the markdown.
The title, price, and URL for a single product are usually found close to each other.

Present the output as a JSON list of objects. Each object should have 'title', 'price', and 'url' keys.
If a value for a specific field (e.g., price or URL) is missing for a product, use the string "N/A" for that field.
If no products can be reliably extracted, return an empty list.

Markdown content (first 15000 chars):
{markdown_content[:15000]}
"""
    print(f"Blinkit (Crawl4AI->Gemini): Sending content to Gemini for extraction. Original Query: {original_query}")
    response_text_for_error_log = "N/A"
    try:
        model = genai.GenerativeModel('gemini-1.5-flash')
        response = model.generate_content(prompt)
        response_text_for_error_log = response.text
        cleaned_response_text = response.text.strip()
        if cleaned_response_text.startswith("```json"): cleaned_response_text = cleaned_response_text[7:]
        if cleaned_response_text.startswith("```"): cleaned_response_text = cleaned_response_text[3:]
        if cleaned_response_text.endswith("```"): cleaned_response_text = cleaned_response_text[:-3]
        if cleaned_response_text.startswith("`") and cleaned_response_text.endswith("`"): cleaned_response_text = cleaned_response_text[1:-1]
        extracted_json = json.loads(cleaned_response_text)
        # Ensure URLs are absolute
        for item in extracted_json:
            if 'url' in item and item['url'] != "N/A" and not item['url'].startswith('http'):
                item['url'] = f"https://blinkit.com{item['url'] if item['url'].startswith('/') else '/' + item['url']}"
        products = [ProductInfo(**p) for p in extracted_json]
        print(f"Blinkit (Crawl4AI->Gemini): Successfully extracted {len(products)} products via Gemini.")
        return products
    except Exception as e:
        print(f"Blinkit (Crawl4AI->Gemini): Error parsing Gemini response for data extraction: {e}. Raw response snippet: {response_text_for_error_log[:500]}")
        return []

def scrape_blinkit(search_query: str, pincode: str, api_key: str, original_user_query: str) -> dict:
    print(f"Blinkit (Crawl4AI): Initializing async run for query '{search_query}' (original: '{original_user_query}')")
    try:
        return asyncio.run(scrape_blinkit_crawl4ai(search_query, pincode, api_key, original_user_query))
    except RuntimeError as e:
        if " asyncio.run() cannot be called from a running event loop" in str(e):
            print("Blinkit (Crawl4AI): Detected running event loop. This script is designed for asyncio.run() from a sync context.")
            return {"title": "Error", "price": "N/A", "url": "N/A", "status": f"Async setup error (Blinkit): {e}"}
        print(f"Blinkit (Crawl4AI): A RuntimeError occurred: {e}")
        return {"title": "Error", "price": "N/A", "url": "N/A", "status": f"Runtime error in Crawl4AI async execution (Blinkit): {e}"}
    except Exception as e:
        error_str = str(e).lower()
        playwright_error_keywords = ["executable doesn't exist", "playwright install", "browser was not found", "chromium-"]
        playwright_help_message = "Ensure Playwright browsers are installed by running 'crawl4ai-setup' or 'python -m playwright install --with-deps chromium' in your terminal."
        if any(keyword in error_str for keyword in playwright_error_keywords):
            status_message = f"Playwright setup needed for Crawl4AI (Blinkit). {playwright_help_message} (Error: {e})"
        else: status_message = f"General error in Crawl4AI async execution (Blinkit): {e}"
        print(f"Blinkit (Crawl4AI): {status_message}")
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

def display_results(user_query: str, results_by_platform: dict):
    print("\n---")
    print(f"Searching for: {user_query}")
    print("---\n")

    # Iterate through results_by_platform if we change to that structure later
    # For now, explicitly access amazon_results and flipkart_results
    amazon_data = results_by_platform.get("Amazon.in", {"status": "Not Selected", "title": "N/A", "price": "N/A", "url": "N/A"})
    flipkart_data = results_by_platform.get("Flipkart.com", {"status": "Not Selected", "title": "N/A", "price": "N/A", "url": "N/A"})
    zepto_data = results_by_platform.get("Zepto", {"status": "Not Selected", "title": "N/A", "price": "N/A", "url": "N/A"})
    swiggy_data = results_by_platform.get("Swiggy Instamart", {"status": "Not Selected", "title": "N/A", "price": "N/A", "url": "N/A"})
    blinkit_data = results_by_platform.get("Blinkit", {"status": "Not Selected", "title": "N/A", "price": "N/A", "url": "N/A"})


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
    print("---")
    print("Zepto:")
    print(f"  Product: {zepto_data.get('title', 'N/A')}")
    print(f"  Price: {zepto_data.get('price', 'N/A')}")
    print(f"  Link: {zepto_data.get('url', 'N/A')}")
    print(f"  Status: {zepto_data.get('status', 'N/A')}\n")
    print("---")
    print("Swiggy Instamart:")
    print(f"  Product: {swiggy_data.get('title', 'N/A')}")
    print(f"  Price: {swiggy_data.get('price', 'N/A')}")
    print(f"  Link: {swiggy_data.get('url', 'N/A')}")
    print(f"  Status: {swiggy_data.get('status', 'N/A')}\n")
    print("---")
    print("Blinkit:")
    print(f"  Product: {blinkit_data.get('title', 'N/A')}")
    print(f"  Price: {blinkit_data.get('price', 'N/A')}")
    print(f"  Link: {blinkit_data.get('url', 'N/A')}")
    print(f"  Status: {blinkit_data.get('status', 'N/A')}\n")

    amazon_price_str = amazon_data.get("price", "N/A")
    flipkart_price_str = flipkart_data.get("price", "N/A")
    # Zepto, Swiggy Instamart & Blinkit prices not used in recommendation yet as they are experimental / crawl-only

    amazon_status = amazon_data.get("status", "Status N/A")
    flipkart_status = flipkart_data.get("status", "Status N/A")
    zepto_status = zepto_data.get("status", "Status N/A")
    swiggy_status = swiggy_data.get("status", "Status N/A")
    blinkit_status = blinkit_data.get("status", "Status N/A")

    amazon_price_float = parse_price(amazon_price_str)
    flipkart_price_float = parse_price(flipkart_price_str)

    recommendation = "Could not determine a recommendation based on available data."
    amz_available = "available" in amazon_status.lower() and amazon_price_float is not None
    flp_available = ("available" in flipkart_status.lower() or "via crawl4ai" in flipkart_status.lower()) and flipkart_price_float is not None

    # Current recommendation only considers Amazon and Flipkart
    if amz_available and flp_available:
        if amazon_price_float < flipkart_price_float: recommendation = f"Amazon.in is cheaper (Amazon: ₹{amazon_price_float:.2f}, Flipkart: ₹{flipkart_price_float:.2f})."
        elif flipkart_price_float < amazon_price_float: recommendation = f"Flipkart.com is cheaper (Flipkart: ₹{flipkart_price_float:.2f}, Amazon: ₹{amazon_price_float:.2f})."
        else: recommendation = f"Prices are similar (Amazon: ₹{amazon_price_float:.2f}, Flipkart: ₹{flipkart_price_float:.2f})."
    elif amz_available: recommendation = f"Product available on Amazon.in (₹{amazon_price_float:.2f}). Status on Flipkart.com: {flipkart_status} (Price: {flipkart_price_str})."
    elif flp_available: recommendation = f"Product available on Flipkart.com (₹{flipkart_price_float:.2f}). Status on Amazon.in: {amazon_status} (Price: {amazon_price_str})."
    else:
        amazon_display_status = amazon_status if "Not Selected" not in amazon_status and "Not Scraped" not in amazon_status else "Not Queried/Error"
        flipkart_display_status = flipkart_status if "Not Selected" not in flipkart_status and "Not Scraped" not in flipkart_status else "Not Queried/Error"
        recommendation = f"Price information unclear or product not found on Amazon/Flipkart. Amazon: {amazon_display_status}. Flipkart: {flipkart_display_status}."

    # Add Zepto status to recommendation string if it was queried
    if "Not Selected" not in zepto_status and "Not Scraped" not in zepto_status :
        recommendation += f" Zepto Status: {zepto_status}."
    # Add Swiggy Instamart status to recommendation string if it was queried
    if "Not Selected" not in swiggy_status and "Not Scraped" not in swiggy_status :
        recommendation += f" Swiggy Instamart Status: {swiggy_status}."
    # Add Blinkit status to recommendation string if it was queried
    if "Not Selected" not in blinkit_status and "Not Scraped" not in blinkit_status :
        recommendation += f" Blinkit Status: {blinkit_status}."


    print("---")
    print(f"Recommendation: {recommendation}")
    print("---")

# --- Main Execution ---
if __name__ == "__main__":
    print("Smart Shopping List Optimizer MVP")
    print("="*30)
    api_key, default_pincode = None, None

    platform_results = {
        "Amazon.in": {"status": "Not Selected", "title": "N/A", "price": "N/A", "url": "N/A"},
        "Flipkart.com": {"status": "Not Selected", "title": "N/A", "price": "N/A", "url": "N/A"},
        "Zepto": {"status": "Not Selected", "title": "N/A", "price": "N/A", "url": "N/A"},
        "Swiggy Instamart": {"status": "Not Selected", "title": "N/A", "price": "N/A", "url": "N/A"},
        "Blinkit": {"status": "Not Selected", "title": "N/A", "price": "N/A", "url": "N/A"}
    }
    user_query_main = ""
    try:
        api_key, default_pincode = load_environment_variables()
        user_query_main = get_user_product_query()
        standardized_query = get_standardized_query(user_query_main, api_key)
        print("-" * 30)

        selected_platforms = get_platform_selection()
        print("-" * 30)

        if "Amazon.in" in selected_platforms:
            print(f"Attempting to scrape Amazon.in for '{standardized_query}' with pincode {default_pincode}...")
            platform_results["Amazon.in"] = scrape_amazon(standardized_query, default_pincode, api_key, user_query_main)
            print("-" * 30)

        if "Flipkart.com" in selected_platforms:
            print(f"Attempting to scrape Flipkart.com for '{standardized_query}' with pincode {default_pincode}...")
            platform_results["Flipkart.com"] = scrape_flipkart(standardized_query, default_pincode, api_key, user_query_main)
            print("-" * 30)

        if "Zepto" in selected_platforms: # Add Zepto call
            print(f"Attempting to scrape Zepto for '{standardized_query}' with pincode {default_pincode}...")
            platform_results["Zepto"] = scrape_zepto(standardized_query, default_pincode, api_key, user_query_main)
            print("-" * 30)

        if "Swiggy Instamart" in selected_platforms:
            print(f"Attempting to scrape Swiggy Instamart for '{standardized_query}' with pincode {default_pincode}...")
            platform_results["Swiggy Instamart"] = scrape_swiggy_instamart(standardized_query, default_pincode, api_key, user_query_main)
            print("-" * 30)

        if "Blinkit" in selected_platforms:
            print(f"Attempting to scrape Blinkit for '{standardized_query}' with pincode {default_pincode}...")
            platform_results["Blinkit"] = scrape_blinkit(standardized_query, default_pincode, api_key, user_query_main)
            print("-" * 30)

    except ValueError as e: print(f"Configuration Error: {e}")
    except Exception as e:
        import traceback
        print(f"An unexpected error occurred in the main execution block: {e}")
        print(traceback.format_exc())
    finally:
        display_results(user_query_main if user_query_main else "N/A", platform_results)

        print("\nFinalizing resources...")
        time.sleep(1)

        print("Exiting Optimizer.")
