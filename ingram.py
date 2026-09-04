import json
import os
import time
import random
import urllib.parse

import mysql.connector
from playwright.sync_api import sync_playwright


CATEGORIES = [
    "Accessories",
    "Audio/Video Devices",
    "Cables",
    "Communications",
    "Computer Systems",
    "Data Capture / Point of Sale",
    "Displays",
    "Education & Training",
    "Imaging Devices",
    "Input & Output Devices",
    "Network Devices",
    "Physical Security",
    "Power & Rack Equipment",
    "Presentation Devices",
    "Printers & Office Equipment",
    "Professional Sound",
    "Services and Warranties",
    "Software",
    "Storage Devices",
    "System Components",
]

PAGES_PER_CATEGORY = 10

PROGRESS_FILE = "ingram_progress.json"

COOLDOWN_AFTER_FAILURES = 3
COOLDOWN_SECONDS = (90, 150)

ABORT_AFTER_FAILURES = 6

CATEGORY_SKIP_THRESHOLD = 4


def load_progress():

    if not os.path.exists(PROGRESS_FILE):
        return {}

    try:
        with open(PROGRESS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    except Exception:
        return {}


def save_progress(progress):

    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def bootstrap_progress_from_db():

    progress = {}

    cursor.execute(
        "SELECT source_category, COUNT(*) "
        "FROM ingram_products "
        "WHERE source_category IS NOT NULL "
        "GROUP BY source_category"
    )

    for category, count in cursor.fetchall():

        pages_done = count // 24

        if pages_done > 0:
            progress[category] = pages_done

    return progress

mysql_password ="..."
db = mysql.connector.connect(
    host="localhost",
    user="root",
    password=mysql_password,
    database="a5it_datas"
)

cursor = db.cursor()

print("MySQL connection successful.")


create_table = """
CREATE TABLE IF NOT EXISTS ingram_products (

    id INT AUTO_INCREMENT PRIMARY KEY,

    part_number VARCHAR(100),
    manufacture_part_number VARCHAR(255),
    global_part_number VARCHAR(255),
    upcean VARCHAR(100),

    vendor_name VARCHAR(255),
    subvendor_name VARCHAR(255),

    description TEXT,
    long_description TEXT,

    category VARCHAR(255),
    subcategory VARCHAR(255),
    product_type VARCHAR(255),

    currency VARCHAR(10),

    dealer_price DECIMAL(15,2),
    customer_price DECIMAL(15,2),
    msrp_price DECIMAL(15,2),

    image_url TEXT,
    gallery_image_url TEXT,

    stock_status VARCHAR(100),
    stock_quantity INT,

    is_authorized_to_buy BOOLEAN,
    is_web_visible BOOLEAN,
    is_discontinued BOOLEAN,
    is_backorder_allowed BOOLEAN,

    product_id VARCHAR(255),
    offering_id VARCHAR(255),

    source_category VARCHAR(255),

    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

cursor.execute(create_table)
db.commit()

print("ingram_products table ready.")


def build_url(category, page):

    category_hierarchy = json.dumps(
        [{"categories": [category]}],
        separators=(",", ":")
    )

    params = {
        "DisableSuggestionSearch": "false",
        "EnablePNA": "false",
        "displaytitle": "",
        "keyword": "",
        "page": str(page),
        "rowsPerPage": "24",
        "sortBy": "relevance",
        "title": category,
        "categoryHierarchy": category_hierarchy,
    }

    query = urllib.parse.urlencode(
        params,
        quote_via=urllib.parse.quote
    )

    return (
        "https://usa.ingrammicro.com/cep/app/product/"
        f"productsearch?{query}"
    )


def save_products(items, category_name):

    if not items:
        return 0

    sql = """

    INSERT INTO ingram_products (

        part_number,
        manufacture_part_number,
        global_part_number,
        upcean,

        vendor_name,
        subvendor_name,

        description,
        long_description,

        category,
        subcategory,
        product_type,

        currency,

        dealer_price,
        customer_price,
        msrp_price,

        image_url,
        gallery_image_url,

        stock_status,
        stock_quantity,

        is_authorized_to_buy,
        is_web_visible,
        is_discontinued,
        is_backorder_allowed,

        product_id,
        offering_id,

        source_category

    )

    VALUES (

        %s, %s, %s, %s,

        %s, %s,

        %s, %s,

        %s, %s, %s,

        %s,

        %s, %s, %s,

        %s, %s,

        %s, %s,

        %s, %s, %s, %s,

        %s, %s,

        %s

    )

    """

    values = []

    for item in items:

        pricing = item.get("pricingInformation") or {}

        dealer_price = pricing.get("dealerPrice")
        customer_price = pricing.get("customerPrice")
        msrp_price = pricing.get("msrpPrice")

        inventory = item.get("inventoryInformation") or {}

        stock_status = (
            item.get("elasticStockStatus")
            or inventory.get("stockStatus")
        )

        stock_quantity = item.get(
            "elasticTotalAvailableQuantity"
        )

        if stock_quantity is None:
            stock_quantity = inventory.get(
                "totalAvailableQuantity"
            )

        values.append((

            item.get("partNumber"),
            item.get("manufacturePartNumber"),
            item.get("globalpartnumber"),
            item.get("upcean"),

            item.get("vendorname"),
            item.get("subvendorname"),

            item.get("shortdescription"),
            item.get("eproductdescription"),

            item.get("category"),
            item.get("subcategory"),
            item.get("producttype"),

            item.get("currencyCode"),

            dealer_price,
            customer_price,
            msrp_price,

            item.get("imageUrl"),
            item.get("galleryImageUrlHigh"),

            stock_status,
            stock_quantity,

            item.get("isAuthorizedToBuy"),
            item.get("isWebVisible"),
            item.get("isdiscontinued"),
            item.get("isBackOrderAllowed"),

            item.get("productid"),
            item.get("offeringid"),

            category_name,

        ))

    cursor.executemany(sql, values)
    db.commit()

    return len(values)


def main():

    total_saved = 0

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False,
            channel="chrome",
            args=[
                "--disable-blink-features=AutomationControlled",
            ],
        )

        context = browser.new_context(
            locale="en-US",
        )

        context.add_init_script(
            "Object.defineProperty(navigator, 'webdriver', "
            "{get: () => undefined});"
        )

        page_obj = context.new_page()

        print("Visiting home page (warming up session)...")

        page_obj.goto(
            "https://usa.ingrammicro.com/",
            wait_until="networkidle"
        )

        time.sleep(random.uniform(2, 4))

        file_progress = load_progress()
        db_progress = bootstrap_progress_from_db()

        progress = {}

        for category in CATEGORIES:

            file_value = file_progress.get(category)

            if file_value == "SKIPPED_CHECK":

                progress[category] = "SKIPPED_CHECK"
                continue

            db_pages = db_progress.get(category, 0)

            if db_pages == 0:

                continue

            if file_value == "DONE":

                progress[category] = "DONE"

            else:

                progress[category] = db_pages

        if progress:

            print(
                "Progress reconciled with current DB data:"
            )

            for cat, val in progress.items():
                print(f"  {cat}: {val}")

        save_progress(progress)

        consecutive_failures = 0
        aborted = False

        for category in CATEGORIES:

            if progress.get(category) in ("DONE", "SKIPPED_CHECK"):

                reason = (
                    "completed"
                    if progress.get(category) == "DONE"
                    else "likely invalid category name, "
                         "awaiting check"
                )

                print()
                print(
                    f"CATEGORY: {category} -> already "
                    f"{reason}, skipping."
                )

                continue

            start_page = progress.get(category, 0) + 1

            category_ever_succeeded = start_page > 1
            category_failures = 0

            print()
            print("=" * 60)

            if start_page > 1:
                print(
                    f"CATEGORY: {category} "
                    f"(resuming from page {start_page})"
                )
            else:
                print(f"CATEGORY: {category}")

            print("=" * 60)

            category_skipped = False

            for page_num in range(start_page, PAGES_PER_CATEGORY + 1):

                url = build_url(category, page_num)

                captured = {}

                def handle_response(response, captured=captured):

                    if (
                        "/api/product/v1/products" in response.url
                        and response.request.method == "POST"
                    ):

                        try:
                            captured["data"] = response.json()

                        except Exception:
                            pass

                page_obj.on("response", handle_response)

                navigation_ok = False

                for nav_attempt in range(1, 3):

                    try:
                        page_obj.goto(
                            url,
                            wait_until="networkidle",
                            timeout=30000
                        )

                        navigation_ok = True
                        break

                    except Exception as e:

                        print(
                            f"Page failed to load (attempt "
                            f"{nav_attempt}/2) | {category} "
                            f"page {page_num} | {e}"
                        )

                        time.sleep(random.uniform(5, 9))

                if not navigation_ok:

                    page_obj.remove_listener(
                        "response",
                        handle_response
                    )

                    consecutive_failures += 1

                else:

                    time.sleep(1)

                    page_obj.remove_listener(
                        "response",
                        handle_response
                    )

                    data = captured.get("data")

                    if not data:

                        print(
                            f"{category} page {page_num}: "
                            "API response not captured."
                        )

                        consecutive_failures += 1
                        category_failures += 1

                    else:

                        products = data.get("products", {})
                        items = products.get("items", [])

                        print(
                            f"{category} page {page_num}: "
                            f"{len(items)} products"
                        )

                        if items:

                            saved = save_products(
                                items,
                                category
                            )

                            total_saved += saved
                            consecutive_failures = 0
                            category_failures = 0
                            category_ever_succeeded = True

                            print(
                                f"  -> Saved to SQL: {saved}"
                            )

                            progress[category] = page_num
                            save_progress(progress)

                            if len(items) < 24:

                                print(
                                    "  -> Page returned fewer "
                                    "than 24 products, this "
                                    "is the last page of the "
                                    "category. Moving to "
                                    "next category."
                                )

                                progress[category] = "DONE"
                                save_progress(progress)

                                break

                        else:

                            print(
                                "  -> No products on this "
                                "page for this category, "
                                "moving to next category."
                            )

                            progress[category] = "DONE"
                            save_progress(progress)

                            break

                if (
                    not category_ever_succeeded
                    and category_failures >= CATEGORY_SKIP_THRESHOLD
                ):

                    print()
                    print(
                        f"  -> '{category}' category never "
                        "returned a successful result, the "
                        "category name is likely wrong. "
                        "Skipping this category, not "
                        "stopping the script — check the "
                        "real categoryHierarchy value for "
                        "this category in the browser's "
                        "Network tab, like you did for "
                        "'Cables'."
                    )

                    progress[category] = "SKIPPED_CHECK"
                    save_progress(progress)

                    category_skipped = True
                    break

                if consecutive_failures >= ABORT_AFTER_FAILURES:

                    print()
                    print("!" * 60)
                    print(
                        "Too many consecutive failures "
                        "(likely IP blocked). Stopping the "
                        "script safely."
                    )
                    print(
                        "Progress saved — wait a few hours "
                        "and rerun the script, it will "
                        "resume from where it left off."
                    )
                    print("!" * 60)

                    aborted = True
                    break

                elif (
                    consecutive_failures > 0
                    and consecutive_failures % COOLDOWN_AFTER_FAILURES == 0
                ):

                    cooldown = random.uniform(*COOLDOWN_SECONDS)

                    print(
                        f"  -> {consecutive_failures} "
                        f"consecutive failures, taking a "
                        f"{cooldown:.0f} second cooldown "
                        "break..."
                    )

                    time.sleep(cooldown)

                else:

                    time.sleep(random.uniform(4, 8))

            if aborted:
                break

            if (
                not category_skipped
                and progress.get(category) != "DONE"
                and progress.get(category, 0) >= PAGES_PER_CATEGORY
            ):
                progress[category] = "DONE"
                save_progress(progress)

    print()
    print("=" * 60)
    print("TOTAL SAVED (this run):", total_saved)
    print("=" * 60)


if __name__ == "__main__":

    try:
        main()

    finally:
        cursor.close()
        db.close()
        print("MySQL connection closed.")
