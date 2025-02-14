import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from config.redisConnection import redisConnection
from config.settings import NOTIFICATIONS_REDIS_KEY


# Month mapping dictionary
MONTH_MAP = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


def fetch_results():
    """Fetch and parse JNTUH results page."""
    url = "http://results.jntuh.ac.in/jsp/home.jsp"

    try:
        with requests.Session() as session:
            response = session.get(url, timeout=10)
            response.raise_for_status()
            soup = BeautifulSoup(response.content, "html.parser")

        return soup.find_all("table")[:8]  # Get only the first 8 tables

    except requests.RequestException as e:
        print(f"Error fetching results: {e}")
        return None


def parse_results(tables):
    """Extracts notifications from parsed HTML tables."""
    results = []

    for table in tables:
        for row in table.find_all("tr"):
            try:
                result_link = row.find("a")["href"]
                result_text = row.get_text().strip().replace(">", "")
                result_text_index = result_text.find("Results") + 7

                result_title = result_text[:result_text_index].strip()
                result_date = (
                    result_text[result_text_index:]
                    .replace("Results", "")
                    .split(")")[-1]
                    .strip()
                )

                results.append(
                    {
                        "Result_title": result_title,
                        "Link": f"http://results.jntuh.ac.in{result_link}",
                        "Date": result_date,
                    }
                )

            except (AttributeError, IndexError, TypeError):
                continue  # Skip rows that don't have valid data

    return results


def format_dates(results):
    """Converts date strings into a formatted YYYY-MM-DD format."""
    formatted_results = []

    for result in results:
        try:
            if result["Date"] == "21-AUGUST-2023":
                result["formatted_date"] = "2024-08-21"
            else:
                day, month_abbr, year = result["Date"].split("-")
                month_abbr = month_abbr[:3].upper()  # Normalize month abbreviation
                month = MONTH_MAP.get(month_abbr, None)

                if month:
                    formatted_date = datetime(int(year), month, int(day)).strftime(
                        "%Y-%m-%d"
                    )
                    result["formatted_date"] = formatted_date
                    formatted_results.append(result)

        except ValueError as e:
            print(f"Error parsing date {result['Date']}: {e}")

    return sorted(formatted_results, key=lambda x: x["formatted_date"], reverse=True)


def get_notifications():
    """Fetches, parses, and caches JNTUH notifications."""
    tables = fetch_results()
    if not tables:
        return None  # Exit if fetching fails

    results = parse_results(tables)
    results = format_dates(results)

    if redisConnection.client:
        redisConnection.client.set(
            NOTIFICATIONS_REDIS_KEY,
            json.dumps(results),
        )
