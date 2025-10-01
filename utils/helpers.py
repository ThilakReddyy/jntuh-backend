from datetime import datetime
from fastapi import HTTPException, Query, status

from config.settings import TELEGRAM_CHAT_ID, TELEGRAM_TOKEN
from utils.logger import telegram_logger


import requests


gradestogpa = {
    "O": 10,
    "A+": 9,
    "A": 8,
    "B+": 7,
    "B": 6,
    "C": 5,
    "D": 5,
    "F": 0,
    "Ab": 0,
    "-": 0,
    "P": 0,
}
gradestogpabppharamcyr22 = {
    "O": 10,
    "A": 9,
    "B": 8,
    "C": 7,
    "D": 6,
    "F": 0,
    "Ab": 0,
    "-": 0,
    "P": 0,
}


def format_date(date: datetime) -> str:
    return date.strftime("%Y-%m-%d")


def getGradeValue(grade, bpharmacyr22):
    if bpharmacyr22:
        return gradestogpabppharamcyr22.get(grade, 0)
    return gradestogpa.get(grade, 0)


def isbpharmacyr22(roll_number):
    grad_year = int(roll_number[:2])
    return roll_number[5] == "R" and (
        grad_year >= 23 or (grad_year == 22 and roll_number[4] != "5")
    )


def isGreat(previousGrade, grade):
    previousGradeValue = gradestogpa.get(previousGrade, 0)  # Default to 1 if not found
    gradeValue = gradestogpa.get(grade, 0)  # Default to 1 if not found
    return previousGradeValue < gradeValue


def validateRollNo(rollNumber: str = Query(..., min_length=10, max_length=10)):
    """Custom validation function for rollNo"""
    if (
        not rollNumber.isalnum()
    ):  # Checks if rollNo contains only alphanumeric characters
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid roll number. It should contain only letters and numbers.",
        )
    return rollNumber.strip().upper()


def validateconstrastRollNos(
    rollNumber1: str = Query(..., min_length=10, max_length=10),
    rollNumber2: str = Query(..., min_length=10, max_length=10),
):
    """Custom validation function for rollNo"""
    if (
        not rollNumber1.isalnum() or not rollNumber2.isalnum()
    ):  # Checks if rollNo contains only alphanumeric characters
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid roll number. It should contain only letters and numbers.",
        )
    if (
        rollNumber1.strip().upper() == rollNumber2.strip().upper()
    ):  # Checks if rollNo contains only alphanumeric characters
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Both the roll Number are same. Kindly use two diff roll Numbers",
        )

    if (
        rollNumber1.strip().upper()[:2] != rollNumber2.strip().upper()[:2]
        and rollNumber1.strip().upper()[4:8] != rollNumber2.strip().upper()[4:8]
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The two roll numbers should be of same Regulation, year and Branch ",
        )

    return [rollNumber1.strip().upper(), rollNumber2.strip().upper()]


def get_credit_regulation_details(roll_number: str):
    credit_regulation_details = {
        "btech": {
            "R18": {
                "Regular": {
                    "1": {"Required": "18", "Total": "37"},
                    "2": {"Required": "47", "Total": "79"},
                    "3": {"Required": "73", "Total": "123"},
                    "4": {"Required": "160", "Total": "160"},
                },
                "Lateral": {
                    "2": {"Required": "25", "Total": "42"},
                    "3": {"Required": "51", "Total": "86"},
                    "4": {"Required": "123", "Total": "123"},
                },
            },
            "R22": {
                "Regular": {
                    "1": {"Required": "20", "Total": "40"},
                    "2": {"Required": "48", "Total": "80"},
                    "3": {"Required": "72", "Total": "120"},
                    "4": {"Required": "160", "Total": "160"},
                },
                "Lateral": {
                    "2": {"Required": "24", "Total": "40"},
                    "3": {"Required": "48", "Total": "80"},
                    "4": {"Required": "120", "Total": "120"},
                },
            },
        }
    }

    # Ensure roll number is at least 10 characters long
    if len(roll_number) < 10:
        return None

    # Extract regulation and entry type
    regulation_year = roll_number[:2]  # First two characters
    entry_type = "Regular" if roll_number[4] == "1" else "Lateral"

    # Ensure it belongs to the B.Tech regulation (R18 or R22)
    if roll_number[5] != "A":  # Checking for 'A' at the 6th position
        return None

    # Determine regulation key
    if (int(regulation_year) >= 18 and int(regulation_year) < 22) or (
        regulation_year == "22" and entry_type == "Lateral"
    ):
        regulation_key = "R18"
    elif int(regulation_year) >= 22:
        regulation_key = "R22"
    else:
        return None  # Unsupported regulation

    return credit_regulation_details["btech"][regulation_key][entry_type]


def send_telegram_notification(data):
    if len(data) != 0:
        for item in data:
            message = "<b>🚨 Results have been Released! 🚨</b>\n\n"

            second_link = "http://202.63.105.184/results/" + "/".join(
                item["link"].split("/")[3:]
            )

            message += f"<b>🎓 {item['title']}</b>\n\n"
            message += (
                f'<b>🔗 Result Link 1:</b> <a href="{item["link"]}">Click Here</a>\n'
            )
            message += (
                f'<b>🔗 Result Link 2:</b> <a href="{second_link}">Click Here</a>\n\n'
            )
            message += f"<b>📅 Released Date:</b> {item['releaseDate']}\n\n"

            message += (
                "💌 <b>Questions or concerns?</b> Reach out to me:\n"
                "- Telegram: @thilak_reddy \n"
                "- Instagram:<a href='https://www.instagram.com/__thilak_reddy__/'>@__thilak_reddy__</a>  \n"
                '- Email: <a href="mailto:thilakreddypothuganti@gmail.com">thilakreddypothuganti@gmail.com</a>\n\n'
                "🌐 <b>More info:</b> <a href='https://jntuhresults.vercel.app/notifications'>jntuhresults.vercel.app</a>"
            )
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": message,
                "parse_mode": "HTML",
            }

            headers = {"Content-Type": "application/json"}

            response = requests.post(url, json=payload, headers=headers)
            if response.status_code == 200:
                telegram_logger.info("Telegram Notification has been Sent")
            else:
                telegram_logger.error("Telegram Notification has been failed to send")
                print("Failed to sent")
