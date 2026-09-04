import mysql.connector

MIN_PERCENT_DIFF = 1.0
mysql_password ="..."
db = mysql.connector.connect(
    host="localhost", user="root", password=mysql_password, database="a5it_datas"
)

cursor = db.cursor()

print("MySQL connection successful.")


cursor.execute("SELECT COUNT(*) FROM a5it_products")
a5it_count = cursor.fetchone()[0]

cursor.execute("SELECT COUNT(*) FROM ingram_products")
ingram_count = cursor.fetchone()[0]

print()
print(f"a5it_products table has {a5it_count} products.")
print(f"ingram_products table has {ingram_count} products.")
print()


cursor.execute("DROP TABLE IF EXISTS result_product")
db.commit()

create_table = """
CREATE TABLE result_product (
    id INT AUTO_INCREMENT PRIMARY KEY,
    name TEXT,
    vendor_name VARCHAR(255),
    mpn VARCHAR(255),
    a5it_price DECIMAL(15,2),
    ingram_price DECIMAL(15,2),
    best_price DECIMAL(15,2),
    best_vendor VARCHAR(50),
    a5it_url TEXT,
    a5it_image TEXT,
    ingram_image TEXT,
    price_difference DECIMAL(15,2),
    price_difference_percent DECIMAL(10,2),
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
)
"""

cursor.execute(create_table)
db.commit()

print("result_product table ready.")


query = """
SELECT
    a.name,
    a.mpn,
    a.vendor_name,
    a.price,
    a.slug,
    a.primary_image,

    i.dealer_price,
    i.image_url

FROM a5it_products a

INNER JOIN ingram_products i
    ON UPPER(TRIM(a.mpn)) = UPPER(TRIM(i.manufacture_part_number))

WHERE
    a.mpn IS NOT NULL AND TRIM(a.mpn) != ''
    AND i.manufacture_part_number IS NOT NULL
    AND TRIM(i.manufacture_part_number) != ''
    AND a.price IS NOT NULL AND a.price > 0
    AND i.dealer_price IS NOT NULL AND i.dealer_price > 0
"""

cursor.execute(query)
matches = cursor.fetchall()

print()
print(f"Total matched rows (by mpn): {len(matches)}")


best_by_mpn = {}

for row in matches:

    (
        name,
        mpn,
        vendor_name,
        a5it_price,
        a5it_slug,
        a5it_image,
        ingram_price,
        ingram_image,
    ) = row

    a5it_price = float(a5it_price)
    ingram_price = float(ingram_price)

    key = mpn.strip().upper()

    candidate_best_price = min(a5it_price, ingram_price)

    existing = best_by_mpn.get(key)

    if existing is None or candidate_best_price < existing["best_price"]:

        best_by_mpn[key] = {
            "name": name,
            "mpn": mpn,
            "vendor_name": vendor_name,
            "a5it_price": a5it_price,
            "a5it_slug": a5it_slug,
            "a5it_image": a5it_image,
            "ingram_price": ingram_price,
            "ingram_image": ingram_image,
            "best_price": candidate_best_price,
        }

print(f"Unique products after deduplication (mpn): {len(best_by_mpn)}")


insert_sql = """
INSERT INTO result_product (
    name,
    vendor_name,
    mpn,
    a5it_price,
    ingram_price,
    best_price,
    best_vendor,
    a5it_url,
    a5it_image,
    ingram_image,
    price_difference,
    price_difference_percent
)
VALUES (
    %s, %s, %s,
    %s, %s,
    %s, %s,
    %s, %s, %s,
    %s, %s
)
"""

result_values = []
skipped_low_diff = 0

for item in best_by_mpn.values():

    a5it_price = item["a5it_price"]
    ingram_price = item["ingram_price"]

    price_difference = abs(a5it_price - ingram_price)
    min_price = min(a5it_price, ingram_price)
    price_difference_percent = (
        (price_difference / min_price) * 100
        if min_price > 0
        else 0
    )

    if price_difference_percent < MIN_PERCENT_DIFF:
        skipped_low_diff += 1
        continue

    a5it_url = (
        f"https://a5it.com/product/{item['a5it_slug']}"
        if item["a5it_slug"]
        else None
    )

    if a5it_price < ingram_price:
        best_price = a5it_price
        best_vendor = "A5IT"
    else:
        best_price = ingram_price
        best_vendor = "Ingram"

    result_values.append((
        item["name"],
        item["vendor_name"],
        item["mpn"],
        a5it_price,
        ingram_price,
        best_price,
        best_vendor,
        a5it_url,
        item["a5it_image"],
        item["ingram_image"],
        price_difference,
        price_difference_percent,
    ))

if result_values:
    cursor.executemany(insert_sql, result_values)
    db.commit()

print()
print(
    f"Skipped due to price difference < {MIN_PERCENT_DIFF}%: "
    f"{skipped_low_diff}"
)
print(f"Written to result_product table: {len(result_values)}")

cursor.close()
db.close()

print("MySQL connection closed.")
