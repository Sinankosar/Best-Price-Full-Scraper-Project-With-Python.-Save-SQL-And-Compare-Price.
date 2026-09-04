import json
import time
import mysql.connector
import requests
import random

API_URL = "https://typesense-production-3f77.up.railway.app/multi_search"
API_KEY = "..."

params = {"use_cache": "true", "x-typesense-api-key": API_KEY}
headers = {"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
mysql_password = "..."
db = mysql.connector.connect(
    host="localhost", user="root", password=mysql_password , database="a5it_datas"
)

cursor = db.cursor()
print("MySQL connection successful.")

create_table_sql = """
CREATE TABLE IF NOT EXISTS a5it_products (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    product_id VARCHAR(100),
    name TEXT,
    mpn VARCHAR(255),
    vendor_name VARCHAR(255),
    category VARCHAR(255),
    sub_category VARCHAR(255),
    category_path TEXT,
    price DECIMAL(12,2),
    retail_price DECIMAL(12,2),
    total_stock INT,
    in_stock BOOLEAN,
    quality_score DECIMAL(10,4),
    primary_image TEXT,
    slug TEXT,
    seo_title TEXT,
    key_features JSON,
    shipping_tier VARCHAR(100),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_mpn (mpn),
    INDEX idx_product_id (product_id)
)
"""

cursor.execute(create_table_sql)
db.commit()
print("a5it_products table ready.")


def create_payload(page):
    return {
        "searches": [
            {
                "facet_sample_percent": 10,
                "facet_sample_threshold": 10000,
                "query_by": (
                    "name,mpn,vendor_name,category,"
                    "sub_category,search_keywords"
                ),
                "query_by_weights": "6,8,4,12,12,4",
                "text_match_type": "max_weight",
                "num_typos": "2,2,2,0,0,0",
                "prefix": "true,true,true,false,false,false",
                "sort_by": (
                    "_text_match:desc,"
                    "_eval([ "
                    "(is_service:false && is_accessory:false):3, "
                    "(is_service:false):2, "
                    "(is_accessory:false):1 "
                    "]):desc,"
                    "quality_score:desc"
                ),
                "include_fields": (
                    "id,name,slug,mpn,vendor_name,vendor_slug,"
                    "vendor_logo_url,category,sub_category,category_path,"
                    "primary_image,display_price,retail_price,total_stock,"
                    "in_stock,quality_score,has_images,seo_title,"
                    "key_features,shipping_tier"
                ),
                "highlight_full_fields": "name,mpn,vendor_name",
                "typo_tokens_threshold": 3,
                "filter_by": (
                    "vendor_name:!=[`AMT`,`Blancco`,"
                    "`CONCENTRIX / SYNNEX`,`D&H Services`,`Datalogic`,"
                    "`Distinow`,`GLOBAL KNOWLEDGE TRAINING`,"
                    "`HOUSHTEC, LLC DBA DISTINOW (ESD)`,"
                    "`INGRAM MICRO`,`INTEGRATION SERVICES`,"
                    "`Ingram Sourcing`,`IronLink`,"
                    "`MSFT SURFACE RECERTIFIED`,`Mitel`,"
                    "`OEM SOURCING`,`PC WHOLESALE EXCLUSIVE`,"
                    "`SERVICESOLV ITAD SOLUTIONS`,`SNX Refurbished`,"
                    "`STRATEGIC SOURCING`,`STRATEGIC SOURCING-TOPAZ`,"
                    "`SYNNEX`,`Star Micronics`,"
                    "`TD SYNNEX CISCO PARTNER SERVICES`,"
                    "`TD SYNNEX- CYBER RANGE`,"
                    "`TDSYNNEX PUBLIC SECTOR (TDSPS)`,"
                    "`TRAINING PALO ALTO`,`Unknown`] "
                    "&& distributor_count:>0"
                ),
                "collection": "products",
                "q": "*",
                "facet_by": (
                    "category_l1,category_l2,category_slugs,"
                    "has_images,in_stock,sell_price,spec_managed_type,"
                    "spec_os,spec_poe_standard,spec_ports,spec_processor,"
                    "spec_processor_brand,spec_ram,spec_resolution,"
                    "spec_screen_size,spec_storage_size,spec_storage_type,"
                    "spec_touchscreen,vendor_name"
                ),
                "max_facet_values": 50,
                "page": page,
                "per_page": 24,
            }
        ]
    }


def get_products(page):
    time.sleep(random.uniform(3.0, 7.0))
    payload = create_payload(page)
    response = requests.post(
        API_URL, params=params, headers=headers, json=payload, timeout=60
    )
    response.raise_for_status()

    data = response.json()
    result = data["results"][0]
    hits = result.get("hits", [])
    products = []

    for hit in hits:
        product = hit.get("document", {})
        products.append({
            "id": product.get("id"),
            "name": product.get("name"),
            "mpn": product.get("mpn"),
            "vendor_name": product.get("vendor_name"),
            "category": product.get("category"),
            "sub_category": product.get("sub_category"),
            "category_path": product.get("category_path"),
            "price": product.get("display_price"),
            "retail_price": product.get("retail_price"),
            "total_stock": product.get("total_stock"),
            "in_stock": product.get("in_stock"),
            "quality_score": product.get("quality_score"),
            "primary_image": product.get("primary_image"),
            "slug": product.get("slug"),
            "seo_title": product.get("seo_title"),
            "key_features": product.get("key_features"),
            "shipping_tier": product.get("shipping_tier"),
        })

    total = result.get("found")
    return products, total


def clean_price(value):
    if value is None:
        return None

    if isinstance(value, str):
        value = value.replace("$", "").replace(",", "").strip()

    try:
        val = float(value)
        return val / 100.0
    except ValueError:
        return None


def save_product(product):
    sql = """
        INSERT INTO a5it_products (
            product_id,
            name,
            mpn,
            vendor_name,
            category,
            sub_category,
            category_path,
            price,
            retail_price,
            total_stock,
            in_stock,
            quality_score,
            primary_image,
            slug,
            seo_title,
            key_features,
            shipping_tier
        )
        VALUES (
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s
        )
    """

    key_features = product.get("key_features")
    if key_features is not None:
        key_features = json.dumps(key_features, ensure_ascii=False)

    values = (
        product.get("id"),
        product.get("name"),
        product.get("mpn"),
        product.get("vendor_name"),
        product.get("category"),
        product.get("sub_category"),
        product.get("category_path"),
        clean_price(product.get("price")),
        clean_price(product.get("retail_price")),
        product.get("total_stock"),
        product.get("in_stock"),
        product.get("quality_score"),
        product.get("primary_image"),
        product.get("slug"),
        product.get("seo_title"),
        key_features,
        product.get("shipping_tier"),
    )

    cursor.execute(sql, values)


def main():
    total_saved = 0

    for page in range(1, 28475):
        print(f"\nPage: {page}")

        try:
            products, total = get_products(page)
            print(f"Products found: {len(products)}")
            print(f"Total count: {total}")

            page_saved = 0
            for product in products:
                try:
                    save_product(product)
                    page_saved += 1
                except Exception as product_error:
                    print(
                        f"PRODUCT ERROR | "
                        f"MPN: {product.get('mpn')} | "
                        f"Error: {product_error}"
                    )

            db.commit()
            total_saved += page_saved
            print(f"Saved to MySQL: {page_saved}")

            time.sleep(random.uniform(1.3, 3.6))

        except Exception as e:
            print(f"ERROR | Page {page} | {e}")
            db.rollback()

    print(f"\nTOTAL SAVED: {total_saved}")


if __name__ == "__main__":
    try:
        main()
    finally:
        cursor.close()
        db.close()
        print("\nMySQL connection closed.")