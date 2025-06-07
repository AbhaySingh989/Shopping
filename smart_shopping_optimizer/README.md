```markdown
# Smart Shopping List Optimizer (MVP)

Version: 0.1

## 1. Agent Capabilities

This AI-powered command-line agent helps you quickly compare product prices between Amazon.in and Flipkart.com.

**Core Features:**
*   **Natural Language Input:** Enter a product name or description in plain English (e.g., "iPhone 15 Pro Max 256GB," "Samsung washing machine 7kg," "LG smart TV 55 inch").
*   **AI-Powered Query Standardization:** Uses Google's Gemini 1.5 Flash model to refine your input into an effective search query for e-commerce sites.
*   **Dual Platform Scraping:** Automatically searches for the product on:
    *   Amazon India (amazon.in)
    *   Flipkart India (flipkart.com)
*   **Targeted Location:** Searches are performed specifically for **Bangalore, Pincode 560020**.
*   **Data Extraction:** For each platform, the agent attempts to extract:
    *   Product Title
    *   Product Price
    *   Direct Product URL
*   **CLI Output:** Presents a clear, comparative list of the findings in your command line.
*   **Basic Recommendation:** Suggests which platform might be cheaper based on the extracted prices.
*   **Error Reporting:** Indicates if a product was not found or if an error occurred during scraping for a specific platform.

**MVP Limitations (Non-Goals):**
*   Only single product queries (no multi-item lists).
*   No cart functionality or purchasing.
*   No advanced optimizations (delivery times, minimum orders).
*   No historical price tracking.
*   No user preferences or purchase history integration.
*   Supports only India (specifically Bangalore, 560020) for searches.
*   No Graphical User Interface (GUI).
*   Basic CAPTCHA handling (may fail if heavy CAPTCHAs are encountered).
*   Basic anti-bot evasion (may be blocked by sophisticated measures).

## 2. Process Flow

The agent follows these steps to provide a price comparison:

1.  **User Input:** Prompts you to enter a product name/description via the command line. Validates that the input is not empty.
2.  **Environment Setup:** Loads necessary API keys (Gemini) and configurations (default Pincode) from a `.env` file.
3.  **Query Standardization (Gemini):**
    *   Sends your input to the Gemini 1.5 Flash model.
    *   Gemini refines the query into a standardized format suitable for e-commerce search engines.
4.  **Web Scraping (Sequential in current MVP code):**
    *   **Amazon.in (via Selenium & `undetected-chromedriver`):**
        *   Opens Amazon.in in a headless browser.
        *   Sets the delivery Pincode to 560020 on the main page.
        *   Performs a search using the standardized query.
        *   Extracts product title, price, and URL from the first few relevant search results using BeautifulSoup.
        *   **Relevance Check (Gemini):** For each potential product, its title is sent to Gemini to determine if it's a relevant match. Only relevant products are considered.
    *   **Flipkart.com (via Crawl4AI):**
        *   Constructs a search URL for Flipkart.
        *   Uses `Crawl4AI` to navigate to the search URL, configured with geolocation settings for Bangalore (Pincode 560020 equivalent).
        *   `Crawl4AI` fetches the page content and converts it into clean Markdown.
        *   Sends this Markdown output to Gemini, along with a prompt, to extract a list of potential products (titles, prices, URLs).
        *   For each product extracted by Gemini, a final relevance check is performed using another Gemini call (comparing the extracted title to the standardized user query).
        *   The first relevant product's details are taken.
5.  **Output Presentation:**
    *   Displays the extracted information (title, price, URL, status) for both Amazon.in and Flipkart.com in the command line.
    *   Provides a simple recommendation (e.g., "Amazon.in is cheaper," "Prices are similar," "Product not found").
6.  **Error Handling:** Throughout the process, the agent includes error handling for issues like:
    *   Missing API keys.
    *   Network problems during scraping.
    *   Product not found on a platform.
    *   Failure to extract specific data points.

## 3. Tools and Technologies Used

*   **Programming Language:** Python 3.x
*   **Large Language Model (LLM):** Google Gemini 1.5 Flash (via `google-generativeai` library) for:
        *   Standardizing the user's initial product query.
        *   Evaluating the relevance of scraped product titles (from both Amazon and Flipkart) against the user's query.
        *   Extracting structured product data (title, price, URL) from the Markdown content retrieved by `Crawl4AI` for Flipkart.
*   **Web Scraping & Automation:**
    *   **Amazon.in:**
        *   **Selenium (`selenium` library) with `undetected-chromedriver`:** For browser automation to scrape Amazon.in.
        *   **BeautifulSoup4 (`beautifulsoup4` library):** For parsing HTML content from Amazon.in.
    *   **Flipkart.com:**
        *   **Crawl4AI (`crawl4ai` library):** An LLM-friendly web crawler used to fetch and preprocess content from Flipkart.com. It uses Playwright for browser automation.
        *   **Geolocation via `Crawl4AI`:** Attempts to set location to Bangalore using latitude/longitude for more accurate Flipkart results.
    *   **Pydantic (`pydantic` library):** Used for data modeling, particularly for structuring data extracted by Gemini from `Crawl4AI`'s output.
*   **Environment Management:**
    *   **python-dotenv (`python-dotenv` library):** For managing API keys and other configurations securely in a `.env` file.
*   **Development Environment:** A standard Python environment with `pip` for package management.

## 4. Step-by-Step Guide to Execute the Agent

Follow these instructions to set up and run the Smart Shopping List Optimizer on your local machine.

**Prerequisites:**
*   Python 3.7 or higher installed. You can download it from [python.org](https://www.python.org/downloads/).
*   `pip` (Python package installer), which usually comes with Python.
*   Google Chrome browser installed (for Selenium-based Amazon scraper and if Playwright uses it).
*   A Gemini API Key from Google AI Studio.
    (Note: The agent uses the Gemini API for query standardization, relevance checking, and potentially for extracting data from Flipkart if `Crawl4AI` is used.)
*   **Playwright Browsers**: The `Crawl4AI` library uses Playwright for its browser automation (used for Flipkart). After installing requirements, you'll need to install browser binaries for Playwright by running:
    ```bash
    crawl4ai-setup
    ```
    Or, more specifically for Chromium (recommended if issues persist):
    ```bash
    python -m playwright install --with-deps chromium
    ```

**Setup Instructions:**

**Step 1: Clone the Repository (or Download Files)**
   If this project is in a Git repository, clone it:
   ```bash
   git clone <repository_url>
   cd smart_shopping_optimizer
   ```
   If you have the files directly, create a project folder (e.g., `smart_shopping_optimizer`) and place `optimizer.py`, `requirements.txt`, and `.env.example` into it.

**Step 2: Create and Activate a Virtual Environment**
   It's highly recommended to use a virtual environment to manage project dependencies.
   Open your terminal or command prompt in the project directory (`smart_shopping_optimizer`).

   *   **Create the virtual environment:**
      ```bash
      python -m venv venv
      ```
   *   **Activate the virtual environment:**
      *   On Windows:
         ```bash
         venv\Scripts\activate
         ```
      *   On macOS and Linux:
         ```bash
         source venv/bin/activate
         ```
      Your terminal prompt should now indicate that you are in the `(venv)` environment.

**Step 3: Install Required Libraries**
   With the virtual environment activated, install the necessary Python packages using the `requirements.txt` file:
   ```bash
   pip install -r requirements.txt
   ```
   This will install `google-generativeai`, `selenium`, `undetected-chromedriver`, `beautifulsoup4`, `python-dotenv`, `crawl4ai`, and `pydantic`.

**Step 4: Set Up Environment Variables (.env file)**
   The agent needs your Gemini API Key to function.
   *   In the project directory, find the file named `.env.example`.
   *   Make a copy of this file and rename the copy to `.env`.
      *   On Windows (Command Prompt): `copy .env.example .env`
      *   On macOS/Linux (Terminal): `cp .env.example .env`
   *   Open the `.env` file in a text editor.
   *   It will look like this:
      ```
      GEMINI_API_KEY="YOUR_GEMINI_API_KEY_HERE"
      DEFAULT_PINCODE="560020"
      ```
   *   Replace `"YOUR_GEMINI_API_KEY_HERE"` with your actual Gemini API key. Ensure the key is within the quotes.
   *   The `DEFAULT_PINCODE` is already set to "560020" as per requirements. You can leave it as is.
   *   **Important:** Save the `.env` file. This file is included in `.gitignore`, so your API key will not be accidentally committed if you are using Git.

**Step 5: Run the Agent**
   Once you have completed all the setup steps, you can run the agent from your terminal (ensure your virtual environment is still active):
   ```bash
   python optimizer.py
   ```

**Execution Flow:**
1.  The script will first attempt to load your environment variables. If the `GEMINI_API_KEY` is missing, it will show an error.
2.  You will be prompted: `Please enter the product name or description: `
3.  Type the product you want to search for (e.g., `Sony WH-1000XM5 headphones`) and press Enter.
4.  The agent will then:
    *   Show you the original and standardized query.
    *   Indicate that it's starting to scrape Amazon.in. You might see some browser activity if headless mode has issues, or it might run silently. This can take some seconds.
    *   Indicate that it's starting to scrape Flipkart.com. This also takes some seconds.
    *   Finally, it will display the results from both platforms, followed by a recommendation.

**Troubleshooting Common Issues:**
*   **`ValueError: GEMINI_API_KEY not found in .env file.`**: Ensure you've created the `.env` file correctly, copied the content from `.env.example`, and replaced the placeholder with your actual API key. Make sure the file is named exactly `.env` (not `.env.txt`).
*   **Selenium/WebDriver Errors (e.g., `WebDriverException`, `SessionNotCreatedException`)**:
    *   Ensure Google Chrome is installed and up to date.
    *   Make sure no antivirus or firewall is blocking WebDriver's operation.
    *   On some systems, especially Linux servers or Docker containers, you might need to install additional dependencies for headless Chrome (for the Amazon scraper).
*   **`undetected-chromedriver` specific issues (Amazon Scraper)**:
    *   **Chrome Version Mismatches**: `undetected-chromedriver` tries to download the correct driver for your installed Chrome version. If you update Chrome, `uc` might need to re-download a new driver on the next run. This is usually automatic.
    *   **Antivirus/Firewall**: Ensure your security software isn't blocking `undetected-chromedriver` or the Chrome instances it launches.
    *   **Profile Issues**: `uc` sometimes uses existing Chrome profiles or creates temporary ones. If you face persistent issues, try running after closing all other Chrome instances.
*   **`Crawl4AI` / Playwright Issues (Flipkart Scraper)**:
    *   **Browser Installation**: If you see errors related to Playwright browsers not being found, ensure you've run `crawl4ai-setup` or `python -m playwright install --with-deps chromium` after installing requirements.
    *   **`Crawl4AI` Failures**: If `Crawl4AI` fails to fetch content from Flipkart (e.g., status message "Crawl4AI failed to retrieve content"), it could be due to network issues, Flipkart blocking the request (even with `Crawl4AI`), or changes in Flipkart's site structure that `Crawl4AI` cannot process effectively. The console logs from the script might provide more details from `Crawl4AI`'s output.
    *   **Geolocation**: While `Crawl4AI` attempts to set geolocation for Flipkart, its effectiveness can vary and might not always reflect exact pincode-level pricing if Flipkart's site relies on other mechanisms.
*   **Scraping Failures (General - Product "Not Found" or "Error")**:
    *   The agent now has more detailed logging. Check the console output for messages from "Amazon:" and "Flipkart:" prefixes to understand at what stage (pincode, search, item processing, relevance check by Gemini, etc.) the issue occurred. This can help identify if it's a selector issue, network problem, or an anti-scraping measure.
    *   E-commerce websites change their layout frequently. The selectors used for scraping (especially for the Selenium-based Amazon scraper) might become outdated. This is a common challenge with web scraping.
    *   The product might genuinely not be available on one or both platforms.
    *   Your internet connection might be unstable, or the websites might be temporarily blocking automated requests.
    *   Heavy CAPTCHAs can block the scrapers.
*   **Gemini Data Extraction/Relevance Check Issues**:
    *   If product data from Flipkart is missing or inaccurate, it might be due to Gemini's interpretation of `Crawl4AI`'s Markdown output. The prompt for this extraction is in `extract_flipkart_data_gemini`.
    *   If relevance checking seems off for either platform, the prompts in `is_product_relevant_gemini` might need adjustment.
    *   Ensure your `GEMINI_API_KEY` is valid and has not exceeded quotas, as it's now used for query standardization, relevance checking, and Flipkart data extraction.
*   **Pincode Issues**: The agent tries to set the pincode to 560020. For Amazon, this is via Selenium UI interaction. For Flipkart (Crawl4AI), it's via geolocation and potentially in the search URL. If the websites change how pincodes are handled, this might fail, and prices might not be for the target location.

This README should provide a solid foundation for users to understand and run the agent.
```
