import json
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from config.redisConnection import redisConnection
from config.settings import (
    NOTIFICATIONS_EXPIRY_TIME,
    NOTIFICATIONS_REDIS_KEY,
)
from database.operations import save_exam_codes
from subscriptions.send_notification import broadcast_all
from utils.logger import logger


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


def categorize_degree(index):
    if index == 0:
        return "btech"
    elif index == 1:
        return "bpharmacy"
    elif index == 2:
        return "mtech"
    elif index == 3:
        return "mpharmacy"
    elif index == 4:
        return "mba"
    elif index == 5:
        return "mca"
    return ""


def categorize_semester_code(title):
    # Categorize the exam code based on the result text
    if " I Year I " in title or " I B.Tech Year I Semester" in title:
        return "1-1"
    elif " I Year II " in title or " I B.Tech Year II Semester" in title:
        return "1-2"
    elif " II Year I " in title or " II B.Tech Year I Semester" in title:
        return "2-1"
    elif " II Year II " in title or " II B.Tech Year II Semester" in title:
        return "2-2"
    elif " III Year I " in title or " III B.Tech Year I Semester" in title:
        return "3-1"
    elif " III Year II " in title or " III B.Tech Year II Semester" in title:
        return "3-2"
    elif " IV Year I " in title or " IV B.Tech Year I Semester" in title:
        return "4-1"
    elif " IV Year II " in title or " IV B.Tech Year II Semester" in title:
        return "4-2"
    else:
        return None


def categorize_masters_exam_code(title):
    # Categorize the masters exam code based on the result text
    if " I Semester" in title:
        return "1-1"
    elif " II Semester" in title:
        return "1-2"
    elif " III Semester" in title:
        return "2-1"
    elif " IV Semester" in title:
        return "2-2"
    else:
        return None


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
        logger.info(f"Error fetching results: {e}")
        return None


def parse_results(tables):
    """Extracts notifications from parsed HTML tables."""
    results = []

    i = 0
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
                        "title": result_title,
                        "link": f"http://results.jntuh.ac.in{result_link}",
                        "date": result_date,
                        "degree": categorize_degree(i),
                    }
                )

            except (AttributeError, IndexError, TypeError):
                continue  # Skip rows that don't have valid data
        i = i + 1

    return results


def extract_exam_code(url):
    # Extract the exam code from the result link
    try:
        params = url.split("?")[1].split("&")
        for param in params:
            if "examCode" in param:
                examCode = param.split("=")[1]
                return examCode
    except Exception as e:
        print(e, url)
        return ""


def format_dates(results):
    """Converts date strings into a formatted YYYY-MM-DD format."""
    formatted_results = []

    for result in results:
        try:
            if result["date"] == "21-AUGUST-2023":
                result["releaseDate"] = "2024-08-21"
            else:
                day, month_abbr, year = result["date"].split("-")
                month_abbr = month_abbr[:3].upper()  # Normalize month abbreviation
                month = MONTH_MAP.get(month_abbr, None)

                if month:
                    formatted_date = datetime(int(year), month, int(day)).strftime(
                        "%Y-%m-%d"
                    )
                    result["releaseDate"] = formatted_date
                    formatted_results.append(result)

        except ValueError as e:
            logger.error(f"Error parsing date {result['date']}: {e}")

    return sorted(formatted_results, key=lambda x: x["releaseDate"], reverse=True)


def isrcrv(title):
    return "RCRV" in title or "RC/RV" in title


def get_exam_codes(results):
    for result in results:
        result["regulation"] = None
        result["semesterCode"] = None
        result["examCode"] = None
        result["rcrv"] = False
        try:
            semester_code = categorize_semester_code(" " + result["title"].strip())

            if semester_code is None:
                semester_code = categorize_masters_exam_code(
                    " " + result["title"].strip()
                )

            regulation = result["title"].split("(")[1].split(")")[0]
            examCode = extract_exam_code(result["link"])

            result["regulation"] = regulation
            result["semesterCode"] = semester_code
            result["examCode"] = examCode
            result["rcrv"] = isrcrv(result["title"])
        except Exception:
            pass
    return results


async def refresh_notifications():
    """Fetches, parses, and caches JNTUH notifications."""
    try:
        tables = fetch_results()
        if not tables:
            return None  # Exit if fetching fails

        results = parse_results(tables)
        results = format_dates(results)

        if redisConnection.client:
            redisConnection.client.set(
                NOTIFICATIONS_REDIS_KEY,
                json.dumps(results),
                ex=NOTIFICATIONS_EXPIRY_TIME,
            )
        results = get_exam_codes(results)

        new_exams = await save_exam_codes(results)
        if new_exams:
            for new_exam in new_exams:
                await broadcast_all(new_exam["title"])
    except Exception as e:
        logger.info(f"Error while fetching notifications:{e}")
