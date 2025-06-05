import os
import google.generativeai as genai
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.service import Service as ChromeService
from webdriver_manager.chrome import ChromeDriverManager
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
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
        wait = WebDriverWait(driver, 10) # General wait timer

        # Navigate to Amazon.in
        driver.get("https://www.amazon.in")
        time.sleep(random.uniform(1,3)) # Allow page to load initially

        # --- Pincode Handling ---
        try:
            # Click the location popover link
            location_popover_link = wait.until(EC.element_to_be_clickable((By.ID, "nav-global-location-popover-link")))
            location_popover_link.click()
            time.sleep(random.uniform(1, 2))

            # Wait for the pincode input field and enter pincode
            pincode_input = wait.until(EC.visibility_of_element_located((By.ID, "GLUXZipUpdateInput")))
            pincode_input.send_keys(pincode)
            time.sleep(random.uniform(0.5, 1.5))

            # Click the apply button
            apply_button = wait.until(EC.element_to_be_clickable((By.XPATH, "//input[@aria-labelledby='GLUXZipUpdate-announce']")))
            apply_button.click()

            # Wait for pincode update to reflect, e.g., by checking if modal closes or a specific element updates.
            # This can be tricky. A simple delay or waiting for staleness of an element might work.
            # For now, a short delay, and we'll check if the location text updates.
            time.sleep(random.uniform(2, 4)) # Increased delay

            # Verify pincode (optional, but good for debugging)
            # delivery_location_text = driver.find_element(By.ID, "nav-global-location-data-modal-action").text
            # if pincode not in delivery_location_text:
            # print(f"Warning: Pincode {pincode} might not have been set correctly. Current location text: {delivery_location_text}")
            # else:
            # print(f"Pincode {pincode} successfully applied.")

        except Exception as e:
            print(f"Error setting pincode on Amazon: {e}. Proceeding without guaranteed pincode.")
            # driver.refresh() # Refresh to ensure we are in a known state if pincode fails
            # time.sleep(random.uniform(1,3))


        # --- Product Search ---
        search_bar = wait.until(EC.visibility_of_element_located((By.ID, "twotabsearchtextbox")))
        search_bar.clear()
        search_bar.send_keys(query)
        search_bar.send_keys(Keys.ENTER)
        time.sleep(random.uniform(2, 4)) # Wait for search results page

        # --- Data Extraction ---
        # Wait for the main search results container
        wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "div.s-main-slot")))
        soup = BeautifulSoup(driver.page_source, "html.parser")

        # Find all search result items (selector might need adjustment)
        results = soup.find_all("div", {"data-component-type": "s-search-result"})

        if not results:
            print("No search results found on Amazon page.")
            return {"title": "Not found", "price": "N/A", "url": "N/A", "status": "Not Found on Amazon"}

        # Iterate through the first few results
        for i, result in enumerate(results[:3]): # Check top 3 results
            title_element = result.select_one("h2 a.a-link-normal span.a-text-normal")
            price_element = result.select_one("span.a-price-whole")
            url_element = result.select_one("h2 a.a-link-normal")

            title = title_element.get_text(strip=True) if title_element else None
            price_str = price_element.get_text(strip=True).replace(",", "").replace(".", "") if price_element else None
            url = "https://www.amazon.in" + url_element["href"] if url_element and url_element.has_attr("href") else None

            # Basic validation: ensure title, price, and URL are found
            if title and price_str and url:
                try:
                    # Attempt to convert price to a numerical value for consistency, though returning string for now
                    # price = float(price_str) # Or int(price_str)
                    print(f"Amazon Result {i+1}: Title='{title}', Price='{price_str}', URL='{url}'")
                    return {"title": title, "price": price_str, "url": url, "status": "Available on Amazon"}
                except ValueError:
                    print(f"Warning: Could not parse price '{price_str}' for item '{title}' on Amazon. Skipping.")
                    continue # Skip if price is not a valid number

        print("Could not extract required information (title, price, URL) from the top Amazon results.")
        return {"title": "Not found", "price": "N/A", "url": "N/A", "status": "Data not extractable on Amazon"}

    except Exception as e:
        print(f"An unexpected error occurred during Amazon scraping: {e}")
        import traceback
        traceback.print_exc()
        return {"title": "Error", "price": "N/A", "url": "N/A", "status": f"Error during Amazon scraping: {str(e)}"}
    finally:
        if driver:
            driver.quit()
            print("Amazon WebDriver closed.")

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
    print(f"Starting Flipkart scrape for query: '{query}' with pincode: {pincode}")
    options = webdriver.ChromeOptions()
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
        driver = webdriver.Chrome(service=ChromeService(ChromeDriverManager().install()), options=options)
        wait = WebDriverWait(driver, 10)
        short_wait = WebDriverWait(driver, 5) # For elements that might appear briefly

        # Navigate to Flipkart
        driver.get("https://www.flipkart.com")
        time.sleep(random.uniform(1, 2))

        # Handle Login Pop-up
        try:
            # Common selectors for Flipkart's login popup close button
            login_popup_close_button = short_wait.until(EC.element_to_be_clickable(
                (By.XPATH, "//button[contains(text(),'✕')] | //button[contains(@class,'_2KpZ6l') and contains(@class,'_2doB4z')]")
            ))
            login_popup_close_button.click()
            print("Closed Flipkart login popup.")
            time.sleep(random.uniform(0.5, 1))
        except Exception:
            print("Flipkart login popup not found or could not be closed. Proceeding...")

        # Product Search
        # Search bar selectors: input[name='q'] or input[title='Search for Products, Brands and More']
        search_bar = wait.until(EC.visibility_of_element_located(
            (By.CSS_SELECTOR, "input[name='q'], input[title^='Search for product']")
        ))
        search_bar.clear()
        search_bar.send_keys(query)
        search_bar.send_keys(Keys.ENTER)
        time.sleep(random.uniform(2, 4)) # Wait for search results

        # Data Extraction from Search Results Page
        wait.until(EC.presence_of_element_located(
            # Common container selectors: div._1YokD2._3Mn1Gg (main results area), div._1AtVbE (individual item cards)
            (By.CSS_SELECTOR, "div._1YokD2, div._1AtVbE, div[data-id]")
        ))
        soup_search_page = BeautifulSoup(driver.page_source, "html.parser")

        # Product item selectors: div._1AtVbE, div._4ddWXP, div._2kHMtA, a._1fQZEK (links wrapping items)
        # For titles: div._4rR01T, a.s1Q9rs, .IRpwTa
        # For prices: div._30jeq3._1_WHN1, div._30jeq3
        # For URLs: direct href from 'a' tag

        # Try a few common structures for product listings
        # Prioritize more specific links if possible (e.g., those with product-like titles)
        results = soup_search_page.select("a._1fQZEK, a.s1Q9rs, div._1xHGtK div._4ddWXP") # More general for links, then specific for divs

        if not results:
             # Fallback if primary selectors fail
            results = soup_search_page.find_all("div", class_=lambda x: x and ("_1AtVbE" in x or "_4ddWXP" in x or "_2kHMtA" in x))


        print(f"Found {len(results)} potential items on Flipkart search results page.")
        if not results:
            return {"title": "Not found", "price": "N/A", "url": "N/A", "status": "Not Found on Flipkart (no results)"}

        extracted_product_url = None
        initial_title = None
        initial_price = None

        for i, item_soup in enumerate(results[:3]): # Check top 3 results
            # Try to get title from common title classes
            title_el = item_soup.select_one("div._4rR01T, a.s1Q9rs, .IRpwTa, ._2WkVRV")
            initial_title = title_el.get_text(strip=True) if title_el else "Title Not Found"

            # Try to get price from common price classes
            price_el = item_soup.select_one("div._30jeq3._1_WHN1, div._30jeq3")
            initial_price = price_el.get_text(strip=True).replace("₹", "").replace(",", "") if price_el else "Price Not Found"

            # Try to get URL
            url_el = None
            if item_soup.name == 'a' and item_soup.has_attr('href'): # If item_soup is <a> tag itself
                url_el = item_soup
            else: # Search within the item_soup for an <a> tag
                url_el = item_soup.select_one("a[href]")

            if url_el and url_el.has_attr('href'):
                product_link = url_el['href']
                if not product_link.startswith("https://www.flipkart.com"):
                    extracted_product_url = "https://www.flipkart.com" + product_link
                else:
                    extracted_product_url = product_link

                print(f"Flipkart Search Result {i+1}: Title='{initial_title}', Price='{initial_price}', URL='{extracted_product_url}'")
                if initial_title != "Title Not Found" and initial_price != "Price Not Found":
                    break # Found a promising item, proceed to its page for pincode check
            extracted_product_url = None # Reset if this item didn't have a good URL/title/price

        if not extracted_product_url:
            print("Could not find a suitable product link on Flipkart search page.")
            return {"title": "Not found", "price": "N/A", "url": "N/A", "status": "Data not extractable on Flipkart"}

        # Navigate to Product Page for Pincode Check
        print(f"Navigating to Flipkart product page: {extracted_product_url}")
        driver.get(extracted_product_url)
        time.sleep(random.uniform(2, 4)) # Allow product page to load

        # On product page, try to update pincode and get final price
        final_price = initial_price # Default to initial price if pincode check fails
        try:
            # Common pincode input field IDs/selectors on product pages
            pincode_input_field = wait.until(EC.visibility_of_element_located(
                (By.CSS_SELECTOR, "input#pincodeInputId, input[placeholder='Enter Delivery Pincode'], input[class*='pincode-input']")
            ))
            # Clear existing pincode first (important!)
            # Need to send CTRL+A then DELETE because .clear() sometimes fails
            pincode_input_field.send_keys(Keys.CONTROL + "a")
            pincode_input_field.send_keys(Keys.DELETE)
            time.sleep(random.uniform(0.2, 0.5))
            pincode_input_field.send_keys(pincode)
            time.sleep(random.uniform(0.5, 1))

            # Find and click the "Check" or "Submit" button for pincode
            # This selector needs to be robust, might be text-based or class-based
            check_button = driver.find_element(By.XPATH, "//span[contains(text(),'Check')] | //button[contains(text(),'Check')] | //div[contains(@class, '_2P_LDn')]") # _2P_LDn is a common class for the check button text
            check_button.click()
            print(f"Entered pincode {pincode} on Flipkart product page and clicked check.")
            time.sleep(random.uniform(2, 4)) # Wait for price/availability to update

            # Re-extract price after pincode update
            # Product page price selector: div._30jeq3._16Jk6d (often the main price)
            soup_product_page = BeautifulSoup(driver.page_source, "html.parser")
            price_after_pincode_el = soup_product_page.select_one("div._30jeq3._16Jk6d, div._30jeq3") # Re-check price
            if price_after_pincode_el:
                final_price = price_after_pincode_el.get_text(strip=True).replace("₹", "").replace(",", "")
                print(f"Price after pincode {pincode} check on Flipkart: {final_price}")
            else:
                print("Could not re-extract price after pincode check on Flipkart. Using initial price.")

        except Exception as e:
            print(f"Error during pincode setting/price re-extraction on Flipkart product page: {e}. Using initial price.")
            # It's possible the page structure doesn't have pincode input or it changed
            # In this case, we proceed with the price found on the search results page.

        # Re-extract title from product page to ensure it's the most accurate one
        soup_product_page_final = BeautifulSoup(driver.page_source, "html.parser")
        final_title_el = soup_product_page_final.select_one("span.B_NuCI") # Common for product titles on page
        if final_title_el:
            initial_title = final_title_el.get_text(strip=True)

        return {"title": initial_title, "price": final_price, "url": extracted_product_url, "status": "Available on Flipkart"}

    except Exception as e:
        print(f"An unexpected error occurred during Flipkart scraping: {e}")
        import traceback
        traceback.print_exc()
        return {"title": "Error", "price": "N/A", "url": "N/A", "status": f"Error during Flipkart scraping: {str(e)}"}
    finally:
        if driver:
            driver.quit()
            print("Flipkart WebDriver closed.")

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

    # Recommendation Logic
    recommendation = "Could not determine a recommendation."

    amazon_price_str = amazon_data.get("price", "N/A")
    flipkart_price_str = flipkart_data.get("price", "N/A")

    amazon_price_float = parse_price(amazon_price_str)
    flipkart_price_float = parse_price(flipkart_price_str)

    amazon_status = amazon_data.get("status", "Error")
    flipkart_status = flipkart_data.get("status", "Error")

    if amazon_price_float is not None and flipkart_price_float is not None:
        if amazon_price_float < flipkart_price_float:
            recommendation = f"Amazon.in is cheaper (₹{amazon_price_float:.2f} vs ₹{flipkart_price_float:.2f})."
        elif flipkart_price_float < amazon_price_float:
            recommendation = f"Flipkart.com is cheaper (₹{flipkart_price_float:.2f} vs ₹{amazon_price_float:.2f})."
        else:
            recommendation = f"Prices are similar on Amazon.in (₹{amazon_price_float:.2f}) and Flipkart.com (₹{flipkart_price_float:.2f})."
    elif amazon_price_float is not None:
        recommendation = f"Amazon.in has a price (₹{amazon_price_float:.2f}), Flipkart.com does not (Status: {flipkart_status})."
    elif flipkart_price_float is not None:
        recommendation = f"Flipkart.com has a price (₹{flipkart_price_float:.2f}), Amazon.in does not (Status: {amazon_status})."
    else: # Neither has a valid price
        if "Not Found" in amazon_status and "Not Found" in flipkart_status:
            recommendation = "Product not found on both platforms."
        elif "Error" in amazon_status or "Error" in flipkart_status:
            recommendation = "Could not compare prices due to errors or missing data from one or both platforms."
        else: # Both might be "N/A" for price but status isn't "Not Found" or "Error"
             recommendation = "Price information unavailable on both platforms."


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
