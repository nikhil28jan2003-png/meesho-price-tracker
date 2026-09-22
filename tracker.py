import os
import re
import json
import time
import requests
import gspread

from datetime import datetime
from google.oauth2.service_account import Credentials


# ==============================
# GOOGLE SHEET SETTINGS
# ==============================

SHEET_ID = "1mzG6jq3sQslNmWvKS1GjcXNb-VPq55x9zJVyrZFrbT8"

PRODUCT_SHEET = "Products"
HISTORY_SHEET = "PriceHistory"


# ==============================
# GOOGLE SHEETS LOGIN
# ==============================

def connect_google_sheet():

    credentials_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")

    if not credentials_json:
        raise Exception(
            "GOOGLE_SERVICE_ACCOUNT_JSON secret is missing."
        )

    credentials_info = json.loads(credentials_json)

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ]

    credentials = Credentials.from_service_account_info(
        credentials_info,
        scopes=scopes
    )

    client = gspread.authorize(credentials)

    spreadsheet = client.open_by_key(SHEET_ID)

    return spreadsheet


# ==============================
# EXTRACT MEESHO PRODUCT ID
# ==============================

def extract_product_id(url):

    match = re.search(r"/p/([A-Za-z0-9]+)", url)

    if match:
        return match.group(1)

    return ""


# ==============================
# GET MEESHO PAGE
# ==============================

def get_meesho_page(url):

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/140.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "en-IN,en;q=0.9",
        "Accept": "text/html,application/xhtml+xml"
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30
    )

    return response


# ==============================
# EXTRACT PRICE
# ==============================

def extract_price(html):

    # --------------------------------
    # Method 1: JSON-LD
    # --------------------------------

    json_ld_blocks = re.findall(
        r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>'
        r'(.*?)'
        r'</script>',
        html,
        re.I | re.S
    )

    for block in json_ld_blocks:

        try:

            data = json.loads(block.strip())

            objects = data if isinstance(data, list) else [data]

            for item in objects:

                if not isinstance(item, dict):
                    continue

                offers = item.get("offers")

                if isinstance(offers, dict):

                    price = offers.get("price")

                    if price:
                        value = float(
                            str(price)
                            .replace(",", "")
                            .strip()
                        )

                        if 1 <= value <= 1000000:
                            return value

                if isinstance(offers, list):

                    for offer in offers:

                        if not isinstance(offer, dict):
                            continue

                        price = offer.get("price")

                        if price:

                            value = float(
                                str(price)
                                .replace(",", "")
                                .strip()
                            )

                            if 1 <= value <= 1000000:
                                return value

        except Exception:
            pass


    # --------------------------------
    # Method 2: Search price patterns
    # --------------------------------

    patterns = [

        r'"price"\s*:\s*"?(?:₹|Rs\.?|INR)?\s*([0-9]+(?:\.[0-9]+)?)',

        r'"price"\s*:\s*([0-9]+(?:\.[0-9]+)?)',

        r'₹\s*([0-9]{1,6}(?:,[0-9]{3})*)',

        r'Rs\.?\s*([0-9]{1,6}(?:,[0-9]{3})*)',

        r'INR\s*([0-9]{1,6}(?:,[0-9]{3})*)'
    ]


    possible_prices = []

    for pattern in patterns:

        matches = re.findall(
            pattern,
            html,
            re.I
        )

        for match in matches:

            try:

                value = float(
                    str(match)
                    .replace(",", "")
                    .strip()
                )

                if 1 <= value <= 1000000:

                    possible_prices.append(value)

            except Exception:
                pass


    if possible_prices:

        return possible_prices[0]


    return None


# ==============================
# CHECK ONE PRODUCT
# ==============================

def check_product(product_name, url):

    print("--------------------------------")
    print("Checking:", product_name)
    print("URL:", url)

    try:

        response = get_meesho_page(url)

        print("HTTP:", response.status_code)

        if response.status_code != 200:

            return None, "HTTP_" + str(response.status_code)

        price = extract_price(response.text)

        if price is None:

            return None, "PRICE_NOT_FOUND"

        print("Price:", price)

        return price, "OK"

    except Exception as error:

        print("Error:", error)

        return None, "ERROR"


# ==============================
# UPDATE PRODUCT SHEET
# ==============================

def update_products_sheet(spreadsheet):

    sheet = spreadsheet.worksheet(PRODUCT_SHEET)

    history = spreadsheet.worksheet(HISTORY_SHEET)

    rows = sheet.get_all_values()

    if len(rows) <= 1:

        print("No products found.")

        return


    now = datetime.now().strftime(
        "%d/%m/%Y %H:%M:%S"
    )


    for row_number in range(2, len(rows) + 1):

        row = rows[row_number - 1]

        product_name = row[0].strip() if len(row) > 0 else ""

        url = row[1].strip() if len(row) > 1 else ""

        if not url:
            continue


        print("")
        print("PRODUCT:", product_name)


        # --------------------------------
        # Product ID
        # --------------------------------

        product_id = extract_product_id(url)


        # --------------------------------
        # Current price
        # --------------------------------

        price, status = check_product(
            product_name,
            url
        )


        # --------------------------------
        # Existing values
        # --------------------------------

        old_current = ""

        previous_price = ""

        lowest_price = ""

        highest_price = ""

        if len(row) > 3:
            old_current = row[3]

        if len(row) > 4:
            previous_price = row[4]

        if len(row) > 5:
            lowest_price = row[5]

        if len(row) > 6:
            highest_price = row[6]


        # --------------------------------
        # If price found
        # --------------------------------

        if price is not None:

            try:
                old_number = float(
                    str(old_current)
                    .replace(",", "")
                )
            except Exception:
                old_number = None


            # Previous price

            if old_number is not None:

                previous_price = old_number

            else:

                previous_price = ""


            # Lowest price

            try:

                old_lowest = float(
                    str(lowest_price)
                    .replace(",", "")
                )

            except Exception:

                old_lowest = None


            if old_lowest is None:

                lowest_price = price

            else:

                lowest_price = min(
                    old_lowest,
                    price
                )


            # Highest price

            try:

                old_highest = float(
                    str(highest_price)
                    .replace(",", "")
                )

            except Exception:

                old_highest = None


            if old_highest is None:

                highest_price = price

            else:

                highest_price = max(
                    old_highest,
                    price
                )


            # Change

            if old_number is None:

                change = "NEW"

            elif price > old_number:

                change = "↑ " + str(
                    round(price - old_number, 2)
                )

            elif price < old_number:

                change = "↓ " + str(
                    round(old_number - price, 2)
                )

            else:

                change = "NO CHANGE"


            current_price = price


            # --------------------------------
            # Save history
            # --------------------------------

            history.append_row(
                [
                    now,
                    product_name,
                    product_id,
                    price,
                    url
                ],
                value_input_option="USER_ENTERED"
            )


        else:

            current_price = old_current

            change = ""


        # --------------------------------
        # Update Products row
        # --------------------------------

        values = [
            product_name,
            url,
            product_id,
            current_price,
            previous_price,
            lowest_price,
            highest_price,
            now,
            change,
            status
        ]


        sheet.update(
            "A" + str(row_number) + ":J" + str(row_number),
            [values]
        )


        print(
            "Saved:",
            product_name,
            current_price,
            status
        )


        # Small delay
        time.sleep(2)


# ==============================
# MAIN
# ==============================

def main():

    print("")
    print("================================")
    print("MEESHO PRICE TRACKER STARTED")
    print("================================")
    print("")


    spreadsheet = connect_google_sheet()


    update_products_sheet(
        spreadsheet
    )


    print("")
    print("================================")
    print("TRACKING COMPLETED")
    print("================================")


if __name__ == "__main__":
    main()
