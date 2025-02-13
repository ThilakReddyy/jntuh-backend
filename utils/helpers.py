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
