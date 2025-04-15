import undetected_chromedriver as uc
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import time
import logging
import pickle

# Setup logging for detailed output
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Credentials and default settings
GOOGLE_EMAIL = "copysignel@gmail.com"
GOOGLE_PASSWORD = "Sayemroot2001"
ACCOUNT_ID = "110284373"  # Change this variable as needed

def initialize_driver():
    options = uc.ChromeOptions()
    options.add_argument("--start-maximized")
    driver = uc.Chrome(options=options)
    logging.info("Initialized Chrome driver.")
    return driver

def click_when_clickable(driver, by_locator, description, timeout=30):
    wait = WebDriverWait(driver, timeout)
    element = wait.until(EC.element_to_be_clickable(by_locator))
    element.click()
    logging.info("Clicked %s.", description)
    return element

def send_keys_when_visible(driver, by_locator, text, description, timeout=30):
    wait = WebDriverWait(driver, timeout)
    element = wait.until(EC.visibility_of_element_located(by_locator))
    element.send_keys(text)
    logging.info("Entered text into %s.", description)
    return element

def login_with_google(driver):
    wait = WebDriverWait(driver, 30)
    driver.get("https://my.exness.com/accounts/sign-in?lng=en")
    logging.info("Opened Exness login page.")
    
    click_when_clickable(driver, (By.XPATH, "//button[contains(., 'Google')]"), "Google login button")
    
    # Switch to the new window if it opens
    main_window = driver.current_window_handle
    time.sleep(2)
    all_windows = driver.window_handles
    new_window = next((w for w in all_windows if w != main_window), None)
    if new_window:
        driver.switch_to.window(new_window)
        logging.info("Switched to the new Google login window.")
    else:
        logging.warning("No new window detected, continuing on the current window.")
    
    # Login steps for Google SSO
    send_keys_when_visible(driver, (By.XPATH, "//input[@type='email']"), GOOGLE_EMAIL, "Google email field")
    click_when_clickable(driver, (By.XPATH, "//div[@id='identifierNext']//button | //span[text()='Next']"), "'Next' after email")
    time.sleep(2)
    
    send_keys_when_visible(driver, (By.XPATH, "//input[@type='password']"), GOOGLE_PASSWORD, "Google password field")
    click_when_clickable(driver, (By.XPATH, "//div[@id='passwordNext']//button | //span[text()='Next']"), "'Next' after password")
    
    logging.info("Waiting for manual intervention (2FA/CAPTCHA), if necessary...")
    time.sleep(5)
    
    try:
        continue_button = WebDriverWait(driver, 30).until(
            EC.element_to_be_clickable((By.XPATH, "//*[contains(text(), 'Continue')]"))
        )
        continue_button.click()
        logging.info("Clicked 'Continue' to complete Google SSO.")
    except Exception as e:
        logging.warning("Could not find or click 'Continue' button: %s", e)
    
    # Switch back and wait until fully logged in
    driver.switch_to.window(main_window)
    wait.until(EC.url_contains("exness"))
    logging.info("Logged in successfully!")
    time.sleep(20)
    return driver

def navigate_and_click_orders(driver, account_id=ACCOUNT_ID):
    strategy_url = f"https://my.exness.com/mfp/st/strategy?account={account_id}&from_fav=true"
    driver.get(strategy_url)
    logging.info("Navigated to strategy URL: %s", strategy_url)

    wait = WebDriverWait(driver, 30)
    orders_xpath = "//button[@data-auto='ORDERS']"

    try:
        orders_tab = wait.until(EC.presence_of_element_located((By.XPATH, orders_xpath)))
        driver.execute_script("arguments[0].scrollIntoView({behavior: 'smooth', block: 'center'});", orders_tab)
        time.sleep(1)
        wait.until(EC.element_to_be_clickable((By.XPATH, orders_xpath))).click()
        logging.info("Clicked Orders tab normally.")
        wait.until(EC.presence_of_element_located((By.XPATH, f"{orders_xpath}[@aria-selected='true']")))
        logging.info("Orders tab is now selected.")
    except Exception as e:
        logging.warning("Standard click failed, trying JavaScript click: %s", e)
        try:
            driver.execute_script("document.querySelector('button[data-auto=\"ORDERS\"]').click();")
            wait.until(EC.presence_of_element_located((By.XPATH, f"{orders_xpath}[@aria-selected='true']")))
            logging.info("JavaScript click succeeded. Orders tab is now selected.")
        except Exception as js_e:
            logging.error("Both normal and JS clicks failed: %s", js_e)
            raise

def extract_cookies_for_playwright(driver):
    try:
        cookies = driver.execute_cdp_cmd("Network.getAllCookies", {})["cookies"]
    except Exception as e:
        logging.error("Failed to extract cookies with CDP: %s", e)
        cookies = driver.get_cookies()  # fallback

    playwright_cookies = []
    for cookie in cookies:
        p_cookie = {
            "name": cookie["name"],
            "value": cookie["value"],
            "domain": cookie["domain"],
            "path": cookie["path"],
            "secure": cookie.get("secure", False),
            "httpOnly": cookie.get("httpOnly", False),
        }
        if "expires" in cookie:
            p_cookie["expires"] = cookie["expires"]
        playwright_cookies.append(p_cookie)

    return playwright_cookies

def main_selenium():
    driver = initialize_driver()
    try:
        login_with_google(driver)
        navigate_and_click_orders(driver)
        time.sleep(5)  # Ensure the page fully loads
        cookies = extract_cookies_for_playwright(driver)
        with open("cookies.pkl", "wb") as f:
            pickle.dump(cookies, f)
        logging.info("Cookies saved to cookies.pkl.")
    except Exception as e:
        logging.error("An error occurred during Selenium steps: %s", e)
        cookies = None
    finally:
        logging.info("Closing Selenium driver in 5 seconds...")
        time.sleep(5)
        driver.quit()
    return cookies

if __name__ == '__main__':
    main_selenium()
