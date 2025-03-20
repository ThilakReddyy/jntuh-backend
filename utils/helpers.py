from fastapi import HTTPException, Query, status


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
}


def getGradeValue(grade):
    return gradestogpa.get(grade, 0)


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
    if (
        int(regulation_year) >= 18
        and int(regulation_year) < 22
        and entry_type == "Regular"
    ) or (regulation_year == "22" and entry_type == "Lateral"):
        regulation_key = "R18"
    elif int(regulation_year) >= 22:
        regulation_key = "R22"
    else:
        return None  # Unsupported regulation

    return credit_regulation_details["btech"][regulation_key][entry_type]
