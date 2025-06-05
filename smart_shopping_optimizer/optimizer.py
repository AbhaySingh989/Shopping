import os
import google.generativeai as genai
from dotenv import load_dotenv
from selenium import webdriver # Keep for options
# from selenium.webdriver.chrome.service import Service as ChromeService # No longer directly used
# from webdriver_manager.chrome import ChromeDriverManager # No longer directly used
import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
import time
import random
# import google.api_core.exceptions # Import for specific error handling if needed later

# Main script for the Smart Shopping Optimizer
# This script will orchestrate the web scraping, LLM interaction, and user interface.

def load_environment_variables() -> tuple[str, str]:
    """
    Loads environment variables from .env file and retrieves the Gemini API key and default pincode.

    Raises:
        ValueError: If GEMINI_API_KEY or DEFAULT_PINCODE is not found in the environment variables.

    Returns:
        tuple[str, str]: The Gemini API key and the default pincode.
    """
    load_dotenv()
    api_key = os.getenv("GEMINI_API_KEY")
    default_pincode = os.getenv("DEFAULT_PINCODE")

    if not api_key:
        raise ValueError("GEMINI_API_KEY not found in .env file. Please ensure it is set.")
    if not default_pincode:
        raise ValueError("DEFAULT_PINCODE not found in .env file. Please ensure it is set (e.g., DEFAULT_PINCODE=\"560020\").")

    return api_key, default_pincode

def scrape_amazon(query: str, pincode: str) -> dict:
    """
    Scrapes Amazon.in for a given product query and pincode.

    Args:
        query (str): The product search query.
        pincode (str): The delivery pincode.

    Returns:
        dict: A dictionary containing product title, price, URL, and status.
              Returns "Not found" or "Error" status if issues occur.
    """
    print(f"Starting Amazon scrape for query: '{query}' with pincode: {pincode}")
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])

    driver = None  # Initialize driver to None
    try:
        print("Amazon: Initializing undetected-chromedriver...")
        # version_main might need to be adjusted or removed if uc handles auto-detection well.
        driver = uc.Chrome(options=options, use_subprocess=True, version_main=120)
        wait = WebDriverWait(driver, 10)
        print("Amazon: WebDriver initialized.")

        driver.get("https://www.amazon.in")
        print("Amazon: Navigated to homepage.")
        time.sleep(random.uniform(1, 2)) # Allow initial page load

        # --- Pincode Handling ---
        pincode_status = "Pincode not attempted"
        try:
            print("Amazon: Attempting to set pincode...")
            # Click the location popover link
            location_popover_link = wait.until(EC.element_to_be_clickable((By.ID, "nav-global-location-popover-link")))
            location_popover_link.click()
            print("Amazon: Clicked location popover link.")
            time.sleep(random.uniform(1, 2)) # Wait for modal

            # Wait for the pincode input field and enter pincode
            pincode_input_field = wait.until(EC.visibility_of_element_located((By.ID, "GLUXZipUpdateInput")))
            print("Amazon: Pincode input field visible.")
            pincode_input_field.send_keys(pincode)
            print(f"Amazon: Entered pincode {pincode}.")
            time.sleep(random.uniform(0.5, 1.5))

            # Click the apply button
            try:
                apply_button = wait.until(EC.element_to_be_clickable((By.ID, "GLUXZipUpdate-announce")))
                apply_button.click()
                print("Amazon: Clicked apply button by ID GLUXZipUpdate-announce.")
            except:
                print("Amazon: Could not find apply button by ID GLUXZipUpdate-announce, trying CSS selector.")
                apply_button_css = wait.until(EC.element_to_be_clickable((By.CSS_SELECTOR, "input[aria-labelledby='GLUXZipUpdate-announce']")))
                apply_button_css.click()
                print("Amazon: Clicked apply button by CSS selector.")

            # Wait for pincode modal to disappear by checking for staleness of the input field
            wait.until(EC.staleness_of(pincode_input_field))
            print(f"Amazon: Pincode {pincode} successfully set and modal closed.")
            pincode_status = f"Pincode {pincode} set successfully."
            time.sleep(random.uniform(1, 2)) # Wait for page elements to update if needed

        except Exception as e:
            pincode_status = f"Error setting pincode: {e}"
            print(f"Amazon: {pincode_status}. Proceeding with search...")
            # driver.refresh() # Optional: refresh if pincode fails, to ensure a clean search state
            # time.sleep(random.uniform(1,3))

        # --- Product Search ---
        print(f"Amazon: Searching for product: '{query}'...")
        search_bar = wait.until(EC.visibility_of_element_located((By.ID, "twotabsearchtextbox")))
        search_bar.clear()
        search_bar.send_keys(query)
        search_bar.send_keys(Keys.ENTER)
        print("Amazon: Search submitted.")

        try:
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.s-main-slot")))
            print("Amazon: Search results page loaded (s-main-slot found).")
        except Exception as e:
            print(f"Amazon: Search results page did not load as expected or s-main-slot not found: {e}")
            return {"title": "Not found", "price": "N/A", "url": "N/A", "status": "Amazon search results page error"}

        soup = BeautifulSoup(driver.page_source, "html.parser")

        results = soup.find_all("div", {"data-component-type": "s-search-result"})
        print(f"Amazon: Found {len(results)} product cards in search results.")

        if not results:
            return {"title": "Not found", "price": "N/A", "url": "N/A", "status": "No product cards found on Amazon"}

        # --- Data Extraction from Search Results ---
        for i, item in enumerate(results[:5]): # Process up to 5 items
            title, price, url = "Not found", "N/A", "N/A"
            print(f"Amazon: Processing item {i+1}")

            # TITLE Extraction
            title_element = item.select_one('h2 a.a-link-normal span.a-text-normal')
            if not title_element:
                title_element = item.select_one('span.a-size-medium.a-color-base.a-text-normal')
            if not title_element:
                title_element = item.select_one('span.a-size-base-plus.a-color-base.a-text-normal')
            if title_element:
                title = title_element.get_text(strip=True)
            else:
                print(f"Amazon: Title not found for item {i+1}")

            # PRICE Extraction
            price_whole_element = item.select_one('span.a-price-whole')
            price_fraction_element = item.select_one('span.a-price-fraction')
            if price_whole_element:
                price = price_whole_element.get_text(strip=True).replace(",", "") # Remove comma for consistency
                if price_fraction_element:
                    price += "." + price_fraction_element.get_text(strip=True) # Add fraction as decimal part
            else:
                price_element = item.select_one('span.a-price span.a-offscreen')
                if price_element:
                    price = price_element.get_text(strip=True).replace('₹', '').replace(',', '')
            if price == "N/A":
                print(f"Amazon: Price not found for item {i+1}")

            # URL Extraction
            url_element = item.select_one('h2 a.a-link-normal')
            if url_element and url_element.has_attr('href'):
                raw_url = url_element['href']
                # Ensure URL is absolute and clean off query parameters if desired (though not strictly needed for MVP)
                if raw_url.startswith('/'):
                    url = "https://www.amazon.in" + raw_url.split('?')[0] # Basic cleaning
                else:
                    url = raw_url.split('?')[0] # Basic cleaning
            else:
                url_element = item.select_one('a.a-link-normal.s-no-outline')
                if url_element and url_element.has_attr('href'):
                    raw_url = url_element['href']
                    if raw_url.startswith('/'):
                        url = "https://www.amazon.in" + raw_url.split('?')[0]
                    else:
                        url = raw_url.split('?')[0]
            if url == "N/A":
                print(f"Amazon: URL not found for item {i+1}")

            print(f"Amazon: Item {i+1} Raw Extract - Title: '{title}', Price: '{price}', URL: '{url}'")

            if title != "Not found" and price != "N/A" and url != "N/A":
                query_keywords = query.lower().split()
                title_lower = title.lower()
                # Check if at least one of the first two keywords of the query is in the title
                if any(keyword in title_lower for keyword in query_keywords[:2]):
                    print(f"Amazon: Found relevant product: Title='{title}', Price='{price}', URL='{url}'")
                    return {"title": title, "price": price, "url": url, "status": "Available on Amazon"}
                else:
                    print(f"Amazon: Item {i+1} title '{title}' deemed not relevant enough for query '{query}'.")
            else:
                print(f"Amazon: Could not extract all required info for item {i+1}.")

        print("Amazon: Could not find a relevant product matching all criteria in top 5 results.")
        return {"title": "Not found", "price": "N/A", "url": "N/A", "status": "Relevant product not found in top results on Amazon"}

    except Exception as e:
        error_message = f"Error during Amazon scraping: {str(e)}"
        print(f"Amazon: {error_message}")
        import traceback
        traceback.print_exc()
        return {"title": "Error", "price": "N/A", "url": "N/A", "status": error_message}
    finally:
        if driver:
            driver.quit()
            print("Amazon: WebDriver closed.")

def scrape_flipkart(query: str, pincode: str) -> dict:
    """
    Scrapes Flipkart.com for a given product query and pincode.

    Args:
        query (str): The product search query.
        pincode (str): The delivery pincode.

    Returns:
        dict: A dictionary containing product title, price, URL, and status.
              Returns "Not found" or "Error" status if issues occur.
    """
    print(f"Flipkart: Starting scrape for query: '{query}' with pincode: {pincode}") # Added platform prefix
    options = webdriver.ChromeOptions()
    # It's generally good to keep headless, window-size, and user-agent consistent.
    # uc.Chrome might manage some of these aspects differently, but providing them is usually fine.
    options.add_argument("--headless")
    options.add_argument("--window-size=1920,1080")
    options.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    options.add_argument("--disable-gpu")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--log-level=3")
    options.add_experimental_option('excludeSwitches', ['enable-logging'])

    driver = None
    try:
        print("Flipkart: Initializing undetected-chromedriver...")
        driver = uc.Chrome(options=options, use_subprocess=True, version_main=120)
        wait = WebDriverWait(driver, 10)
        # short_wait = WebDriverWait(driver, 5) # Already defined, but ensure it's used appropriately
        print("Flipkart: WebDriver initialized.")

        driver.get("https://www.flipkart.com")
        print("Flipkart: Navigated to homepage.")
        time.sleep(random.uniform(1, 2)) # Initial load pause

        # Handle Login Pop-up
        try:
            print("Flipkart: Checking for login popup...")
            # More specific XPATH, looking for a button, possibly with specific text or class
            login_popup_close_button = WebDriverWait(driver, 7).until( # Reduced wait time for popup
                EC.element_to_be_clickable((By.XPATH, "//button[contains(text(), '✕')] | //button[contains(@class, '_2KpZ6l') and contains(@class, '_2doB4z')] | //span[contains(@class, '_30XB9F') and text()='✕']"))
            ) # Added one more common selector for close button (span type)
            login_popup_close_button.click()
            print("Flipkart: Login popup closed.")
            time.sleep(random.uniform(0.5, 1))
        except Exception as e:
            print(f"Flipkart: Login popup not found or could not be closed (this is often OK): {e}")

        # Product Search
        print(f"Flipkart: Searching for product: '{query}'...")
        # Using a more encompassing selector for search bar, then filtering for visibility
        search_bar_selectors = "input[name='q'], input[title='Search for Products, Brands and More'], input[title='Search for products, brands and more']"
        search_bar = wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, search_bar_selectors)))

        # Ensure the located search bar is visible and interactable
        if not search_bar.is_displayed():
            # If the first found isn't visible, try to find another one that is (less common)
            search_bars = driver.find_elements(By.CSS_SELECTOR, search_bar_selectors)
            search_bar = next((bar for bar in search_bars if bar.is_displayed()), None)
            if not search_bar:
                raise Exception("Flipkart search bar found but not visible/interactable.")

        search_bar.clear()
        search_bar.send_keys(query)
        search_bar.send_keys(Keys.ENTER)
        print(f"Flipkart: Search submitted for '{query}'.")

        # Wait for Search Results Page
        try:
            # Wait for at least one product card indicator to be present
            results_page_indicator_selector = "div._1AtVbE, div._13oc-S, div[data-id^='MOB']" # Added data-id starting with MOB for mobiles often
            WebDriverWait(driver, 20).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, results_page_indicator_selector))
            )
            print("Flipkart: Search results page loaded (at least one potential item indicator found).")
        except Exception as e:
            print(f"Flipkart: Search results page did not load as expected: {e}")
            # Try to capture a screenshot here if debugging indicates it's useful
            # driver.save_screenshot("flipkart_search_fail.png")
            return {"title": "Not found", "price": "N/A", "url": "N/A", "status": "Flipkart search results page error"}

        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Product Cards selectors
        # Common structures: div._1AtVbE (list view), div._4ddWXP (often wraps items), div._1xHGtK._373qXS (another common card), a._1fQZEK (direct link to product in some views)
        # div[data-id] is a general attribute for product entities.
        results = soup.select("div[data-id], div._1AtVbE, div._4ddWXP, div._1xHGtK._373qXS, a._1fQZEK")
        print(f"Flipkart: Found {len(results)} potential product cards/links.")

        if not results:
            return {"title": "Not found", "price": "N/A", "url": "N/A", "status": "No product cards found on Flipkart"}

        # --- Data Extraction from Search Results ---
        for i, item in enumerate(results[:5]): # Process up to 5 items
            title, price, url = "Not found", "N/A", "N/A"
            print(f"Flipkart: Processing item {i+1}")

            # TITLE Extraction
            # Prioritize specific title classes, then more general ones, then image alt text
            title_element = item.select_one('div._4rR01T, a.s1Q9rs, a.IRpwTa, ._2WkVRV, .css-1xOzF6') # Added .css-1xOzF6 as a generic class seen
            if title_element:
                title = title_element.get_text(strip=True)
            else:
                img_alt_title = item.select_one('img._396cs4, img.CXW8mj') # Common image classes
                if img_alt_title and img_alt_title.has_attr('alt'):
                    title = img_alt_title['alt'].strip()
            if title == "Not found":
                print(f"Flipkart: Title not found for item {i+1}")

            # PRICE Extraction
            price_element = item.select_one('div._30jeq3._1_WHN1, div._30jeq3, .css-1xOzF6 .css-1qs7bhd') # Added another specific price pattern
            if price_element:
                price = price_element.get_text(strip=True).replace('₹', '').replace(',', '')
            if price == "N/A":
                print(f"Flipkart: Price not found for item {i+1}")

            # URL Extraction
            # Prefer links that wrap titles or are specifically marked as product links
            url_element = item.select_one('a._1fQZEK, a.s1Q9rs, a.IRpwTa, a._2UzuFa, a._2rpwqI') # Added a._2rpwqI
            if not url_element and item.name == 'a' and item.has_attr('href'): # If item itself is <a> tag
                url_element = item

            if url_element and url_element.has_attr('href'):
                raw_url = url_element['href']
                if raw_url.startswith('/'):
                    url = "https://www.flipkart.com" + raw_url.split('?')[0] # Basic cleaning
                else: # Should ideally not happen if it's a Flipkart link from Flipkart site
                    url = raw_url.split('?')[0]
            if url == "N/A":
                print(f"Flipkart: URL not found for item {i+1}")

            print(f"Flipkart: Item {i+1} Raw Extract - Title: '{title}', Price: '{price}', URL: '{url}'")

            if title != "Not found" and price != "N/A" and url != "N/A" and not title.lower().startswith("ad"): # Basic ad filter
                query_keywords = query.lower().split()
                title_lower = title.lower()
                if any(keyword in title_lower for keyword in query_keywords[:2]): # Relevance check
                    print(f"Flipkart: Found relevant product candidate: Title='{title}', Price='{price}', URL='{url}'")
                    search_page_price = price # Store for fallback

                    try:
                        print(f"Flipkart: Navigating to product page: {url}")
                        driver.get(url)
                        # Wait for pincode input field on product page
                        pincode_input_on_page = WebDriverWait(driver, 15).until(
                            EC.visibility_of_element_located((By.CSS_SELECTOR, "input#pincodeInputId, input._36yFo0, input[placeholder='Enter Delivery Pincode']"))
                        ) # Added _36yFo0 class
                        print("Flipkart: Pincode input field visible on product page.")

                        pincode_input_on_page.send_keys(Keys.CONTROL + "a") # Clear existing
                        pincode_input_on_page.send_keys(Keys.DELETE)
                        time.sleep(random.uniform(0.3, 0.7))
                        pincode_input_on_page.send_keys(pincode)
                        print(f"Flipkart: Entered pincode {pincode} on product page.")

                        # Attempt to click a "Check" or "Apply" button if it exists and is distinct
                        # Flipkart often auto-applies, so this might not always be necessary or present
                        try:
                            check_button = WebDriverWait(driver, 3).until( # Short wait for optional check button
                                EC.element_to_be_clickable((By.XPATH, "//span[contains(text(),'Check')] | //span[contains(text(),'Apply')] | //div[contains(@class, '_2P_LDn')] | //span[contains(@class, 'i40dM4')]"))
                            ) # Added another class for check button text
                            check_button.click()
                            print("Flipkart: Clicked pincode 'Check/Apply' button on product page.")
                            time.sleep(random.uniform(1.5, 2.5)) # Longer wait if button clicked
                        except:
                            print("Flipkart: Pincode 'Check/Apply' button not found or not clicked (might be auto-applied).")
                            time.sleep(random.uniform(1, 2)) # Standard wait for auto-apply

                        # Re-extract price from product page
                        new_soup_product_page = BeautifulSoup(driver.page_source, "html.parser")
                        # More specific price selectors for product page
                        price_on_product_page_el = new_soup_product_page.select_one('div._30jeq3._16Jk6d, div.CEmiEU div._30jeq3')
                        if price_on_product_page_el:
                            price = price_on_product_page_el.get_text(strip=True).replace('₹', '').replace(',', '')
                            print(f"Flipkart: Price after pincode {pincode} on product page: {price}")
                        else:
                            price = search_page_price # Fallback to search page price
                            print(f"Flipkart: Could not re-verify price on product page for pincode {pincode}. Using search page price: {price}")

                        # Re-extract title from product page for accuracy
                        final_title_el = new_soup_product_page.select_one("span.B_NuCI, h1 span._35KyD6") # Common title spans on product page
                        if final_title_el:
                            title = final_title_el.get_text(strip=True)

                        return {"title": title, "price": price, "url": url, "status": "Available on Flipkart"}

                    except Exception as e_pd_page:
                        print(f"Flipkart: Error during product page interaction or pincode check for {url}: {e_pd_page}")
                        return {"title": title, "price": search_page_price, "url": url, "status": "Available on Flipkart (pincode check failed/price not re-verified)"}
                else:
                    print(f"Flipkart: Item {i+1} title '{title}' (Ad: {title.lower().startswith('ad')}) not relevant enough for query '{query}'.")
            else:
                print(f"Flipkart: Could not extract all required info for item {i+1}.")

        print("Flipkart: Could not find a relevant product matching all criteria in top results.")
        return {"title": "Not found", "price": "N/A", "url": "N/A", "status": "Relevant product not found in top results on Flipkart"}

    except Exception as e:
        error_message = f"Error during Flipkart scraping: {str(e)}"
        print(f"Flipkart: {error_message}")
        import traceback
        traceback.print_exc()
        return {"title": "Error", "price": "N/A", "url": "N/A", "status": error_message}
    finally:
        if driver:
            driver.quit()
            print("Flipkart: WebDriver closed.")

# --- Helper function to parse price strings ---
def parse_price(price_str: str) -> float | None:
    """
    Parses a price string (e.g., "₹1,234.56", "1234") into a float.

    Args:
        price_str (str): The price string to parse.

    Returns:
        float | None: The parsed price as a float, or None if parsing fails or input is invalid.
    """
    if not price_str or price_str.lower() == "n/a":
        return None

    # Remove currency symbols (₹, $, etc.) and commas
    cleaned_price = price_str.replace("₹", "").replace("$", "").replace(",", "").strip()

    try:
        return float(cleaned_price)
    except ValueError:
        print(f"Warning: Could not parse price string: '{price_str}'")
        return None

# --- Function to display results ---
def display_results(user_query: str, amazon_data: dict, flipkart_data: dict):
    """
    Displays the scraped product information from Amazon and Flipkart,
    and provides a recommendation based on price.

    Args:
        user_query (str): The original user query.
        amazon_data (dict): Data dictionary from scrape_amazon.
        flipkart_data (dict): Data dictionary from scrape_flipkart.
    """
    print("\n---")
    print(f"Searching for: {user_query}")
    print("---\n")

    # Amazon Results
    print("Amazon.in:")
    print(f"  Product: {amazon_data.get('title', 'N/A')}")
    print(f"  Price: {amazon_data.get('price', 'N/A')}")
    print(f"  Link: {amazon_data.get('url', 'N/A')}")
    print(f"  Status: {amazon_data.get('status', 'N/A')}")
    print("\n---\n") # Separator

    # Flipkart Results
    print("Flipkart.com:")
    print(f"  Product: {flipkart_data.get('title', 'N/A')}")
    print(f"  Price: {flipkart_data.get('price', 'N/A')}")
    print(f"  Link: {flipkart_data.get('url', 'N/A')}")
    print(f"  Status: {flipkart_data.get('status', 'N/A')}")
    print("\n---")

    # Recommendation Logic Update
    amazon_price_str = amazon_data.get("price", "N/A")
    flipkart_price_str = flipkart_data.get("price", "N/A")
    amazon_status = amazon_data.get("status", "Status N/A") # Default if status key is missing
    flipkart_status = flipkart_data.get("status", "Status N/A") # Default if status key is missing

    amazon_price_float = parse_price(amazon_price_str)
    flipkart_price_float = parse_price(flipkart_price_str)

    recommendation = "Could not determine a recommendation based on available data."

    # Check if status indicates availability (e.g., "Available on...", "Available on... (pincode check failed)")
    # and if a valid price float was parsed.
    amz_available_with_price = "available" in amazon_status.lower() and amazon_price_float is not None
    flp_available_with_price = "available" in flipkart_status.lower() and flipkart_price_float is not None

    if amz_available_with_price and flp_available_with_price:
        if amazon_price_float < flipkart_price_float:
            recommendation = f"Amazon.in is cheaper (Amazon: ₹{amazon_price_float:.2f}, Flipkart: ₹{flipkart_price_float:.2f})."
        elif flipkart_price_float < amazon_price_float:
            recommendation = f"Flipkart.com is cheaper (Flipkart: ₹{flipkart_price_float:.2f}, Amazon: ₹{amazon_price_float:.2f})."
        else:
            recommendation = f"Prices are similar (Amazon: ₹{amazon_price_float:.2f}, Flipkart: ₹{flipkart_price_float:.2f})."
    elif amz_available_with_price:
        recommendation = f"Product available on Amazon.in (₹{amazon_price_float:.2f}). Status on Flipkart.com: {flipkart_status} (Price: {flipkart_price_str})."
    elif flp_available_with_price:
        recommendation = f"Product available on Flipkart.com (₹{flipkart_price_float:.2f}). Status on Amazon.in: {amazon_status} (Price: {amazon_price_str})."
    else:
        # Neither has a clearly available product with a valid parsed price.
        # Provide a summary of statuses.
        recommendation = (
            f"Price comparison not possible. "
            f"Amazon: {amazon_status} (Reported Price: {amazon_price_str}). "
            f"Flipkart: {flipkart_status} (Reported Price: {flipkart_price_str})."
        )

    print(f"Recommendation: {recommendation}")
    print("---")


def get_standardized_query(user_query: str, api_key: str) -> str:
    """
    Refines a raw user product query into a concise and effective search query
    using the Gemini API.

    Args:
        user_query (str): The raw product query from the user.
        api_key (str): The Gemini API key.

    Returns:
        str: The refined search query, or the original query if an error occurs.
    """
    try:
        genai.configure(api_key=api_key)
        model = genai.GenerativeModel('gemini-1.5-flash')

        prompt = (
            "Refine the following user product query into a concise and effective search query "
            "suitable for e-commerce platforms like Amazon and Flipkart. "
            "Focus on extracting key product identifiers, brand, model, quantity, and relevant keywords. "
            "For example, if the user query is 'samsung 23L microwave oven black', the refined query could be "
            "'Samsung 23L microwave oven black'. If the user query is 'Looking for a 500 gram pack of fresh red tomatoes', "
            "the refined query should be 'fresh red tomatoes 500g'. "
            "Your output should ONLY be the refined query string, with no extra conversational text or explanations.\n\n"
            f"User Query: \"{user_query}\"\n"
            "Refined Query:"
        )

        response = model.generate_content(prompt)

        # Basic check to see if response.text exists and is not empty
        if response.text and response.text.strip():
            return response.text.strip()
        else:
            print("Warning: Gemini API returned an empty response. Using original query.")
            return user_query

    except Exception as e: # Broad exception for now, can be refined
        # Check if the exception is from google.api_core.exceptions for more specific handling if needed
        # For example: if isinstance(e, google.api_core.exceptions.GoogleAPIError): # type: ignore
        print(f"Error during Gemini API call: {e}. Using original query as fallback.")
        return user_query

def get_user_product_query() -> str:
    """
    Prompts the user to enter a product name or description and validates the input.

    The function will continuously prompt the user until a non-empty string is provided.
    Whitespace is stripped from the input before validation.

    Returns:
        str: The validated, non-empty user query string.
    """
    while True:
        user_input = input("Please enter the product name or description: ").strip()
        if user_input:
            return user_input
        else:
            print("Input cannot be empty. Please try again.")

if __name__ == "__main__":
    try:
        api_key, default_pincode = load_environment_variables()

        user_query = get_user_product_query()
        print(f"Original query: {user_query}")

        standardized_query = get_standardized_query(user_query, api_key)
        # print(f"Standardized query: {standardized_query}") # Keep this for debugging if needed

        if standardized_query: # Proceed only if we have a query
            # Initialize results to ensure they are always defined
            amazon_results = {"title": "N/A", "price": "N/A", "url": "N/A", "status": "Not Scraped (Query Missing or Error)"}
            flipkart_results = {"title": "N/A", "price": "N/A", "url": "N/A", "status": "Not Scraped (Query Missing or Error)"}

            print(f"\nAttempting to scrape Amazon for '{standardized_query}' with pincode {default_pincode}...")
            amazon_results = scrape_amazon(standardized_query, default_pincode)
            # print(f"Amazon Results: {amazon_results}") # Raw results, display_results will format

            print(f"\nAttempting to scrape Flipkart for '{standardized_query}' with pincode {default_pincode}...")
            flipkart_results = scrape_flipkart(standardized_query, default_pincode)
            # print(f"Flipkart Results: {flipkart_results}") # Raw results, display_results will format

            display_results(user_query, amazon_results, flipkart_results)
        else:
            print("Could not proceed with scraping as the standardized query was empty.")

    except ValueError as e:
        print(f"Configuration Error: {e}")
    except Exception as e: # Catch any other unexpected errors
        print(f"An unexpected error occurred in the main script: {e}")
        import traceback
        traceback.print_exc()
