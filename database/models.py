from typing import Any, List, TypedDict
from prisma.models import student, mark
from pydantic import BaseModel

from config.settings import SEMESTERS
from utils.helpers import getGradeValue, isGreat


class StudentDetails(TypedDict):
    name: str
    rollNumber: str
    collegeCode: str
    fatherName: str


class PushSub(BaseModel):
    anon_id: str
    roll_number: str | None = None
    subscription: dict[str, Any]


def studentDetailsModel(details: student) -> StudentDetails:
    return {
        "name": details.name,
        "rollNumber": details.rollNumber,
        "collegeCode": details.collegeCode,
        "fatherName": details.fatherName,
    }


class StudentResult(TypedDict):
    subjectCode: str
    subjectName: str
    internalMarks: float
    externalMarks: float
    totalMarks: int
    grades: str
    credits: float


def studentResultModel(result: mark) -> StudentResult:
    return {
        "subjectCode": str(getattr(result.subject, "subjectCode", "") or ""),
        "subjectName": str(getattr(result.subject, "subjectName", "") or ""),
        "internalMarks": int(result.internalMarks)
        if str(result.internalMarks).isdigit()
        else 0,
        "externalMarks": int(result.externalMarks)
        if str(result.externalMarks).isdigit()
        else 0,
        "totalMarks": int(result.totalMarks) if str(result.totalMarks).isdigit() else 0,
        "grades": str(result.grades or ""),
        "credits": float(result.credits or 0),
    }


def studentAllResultsModel(
    results: List[mark],
):
    final_result = {}
    for result in results:
        semester_results = final_result.setdefault(
            result.semesterCode, {"semester": result.semesterCode, "exams": {}}
        )
        exam_code = f"{result.examCode}[RCRV]" if result.rcrv else result.examCode
        exam_data = semester_results["exams"].setdefault(
            exam_code,
            {
                "examCode": exam_code,
                "rcrv": result.rcrv,
                "subjects": [],
            },
        )
        exam_data["subjects"].append(studentResultModel(result))

    return [
        {"semester": sem, "exams": list(data["exams"].values())}
        for sem, data in final_result.items()
    ]


def calculateGPA(grades: float, credits: float) -> str:
    return f"{round(grades / credits, 2):.2f}" if credits > 0 else "0.00"


def processResults(results: List[mark], bpharmacyR22):
    final_result = {}
    total_grades, total_credits, total_backlogs = 0.0, 0.0, 0

    for result in results:
        semester_results = final_result.setdefault(result.semesterCode, {})
        subject_code = getattr(result.subject, "subjectCode", "")

        if subject_code not in semester_results or isGreat(
            semester_results[subject_code]["grades"], result.grades
        ):
            semester_results[subject_code] = studentResultModel(result)

    for semester, subjects in final_result.items():
        semester_credits = semester_grades = backlogs = 0.0
        subject_list = list(subjects.values())

        for subject in subject_list:
            grade_value = getGradeValue(subject["grades"], bpharmacyR22)
            subject_credits = subject["credits"]
            semester_grades += grade_value * subject_credits
            semester_credits += subject_credits
            backlogs += int(grade_value == 0)

        final_result[semester] = {
            "semester": semester,
            "subjects": subject_list,
            "semesterSGPA": calculateGPA(semester_grades, semester_credits),
            "semesterCredits": semester_credits,
            "semesterGrades": semester_grades,
            "backlogs": backlogs,
            "failed": backlogs > 0,
        }
        total_grades += semester_grades
        total_credits += semester_credits
        total_backlogs += backlogs

    final_result_keys = final_result.keys()
    semesters = {}
    for semester in SEMESTERS:
        if semester in final_result_keys:
            semesters[semester] = final_result[semester]

    return {
        "semesters": list(semesters.values()),
        "CGPA": calculateGPA(total_grades, total_credits),
        "backlogs": total_backlogs,
        "credits": total_credits,
        "grades": total_grades,
    }


def studentResultsModel(results: List[mark], bpharmacyR22=False):
    return processResults(results, bpharmacyR22)


def studentCredits(results: List[mark], credits, bpharmacyR22):
    processed_results = processResults(results, bpharmacyR22)
    semester_results = processed_results["semesters"]

    # Extract semester-wise obtained credits
    semester_credits = {
        sem["semester"]: sem["semesterCredits"] for sem in semester_results
    }
    total_obtained_credits = sum(semester_credits.values())

    # Split semester credits into chunks of 2
    chunk_size = 2
    semester_credits_chunked = [
        dict(list(semester_credits.items())[i : i + chunk_size])
        for i in range(0, len(semester_credits), chunk_size)
    ]

    ret = {
        "academicYears": [],
        "totalCredits": 0.0,
        "totalObtainedCredits": total_obtained_credits,
        "totalRequiredCredits": 0.0,
    }

    previous_credits = {}
    for i, (year, year_data) in enumerate(credits.items()):
        if len(semester_credits_chunked) - 1 >= i:
            ret["academicYears"].append(
                {
                    "semesterWiseCredits": semester_credits_chunked[i]
                    if i < len(semester_credits_chunked)
                    else {},
                    "creditsObtained": sum(semester_credits_chunked[i].values())
                    if i < len(semester_credits_chunked)
                    else 0.0,
                    "totalCredits": float(year_data["Total"])
                    - float(previous_credits.get("Total", 0.0)),
                }
            )
            previous_credits = year_data

    ret["totalCredits"] = float(previous_credits.get("Total", 0.0))
    ret["totalRequiredCredits"] = float(previous_credits.get("Required", 0.0))

    return ret


def studentBacklogs(results: List[mark], bpharmacyR22):
    processed_results = processResults(results, bpharmacyR22)["semesters"]
    backlogs_data = []
    for sem in processed_results:
        if sem["backlogs"] >= 1.0:
            backlogSubjects = []
            for subject in sem["subjects"]:
                grade_value = getGradeValue(subject["grades"], bpharmacyR22)
                if grade_value == 0:
                    backlogSubjects.append(subject)
            sem["subjects"] = backlogSubjects
            backlogs_data.append(sem)

    total_backlogs = sum(sem["backlogs"] for sem in backlogs_data)

    return {
        "semesters": backlogs_data,
        "totalBacklogs": total_backlogs,
    }


def studentResultContrast(result1, result2):
    # Extract basic details for both students
    student1_profile = {
        "name": result1["details"]["name"],
        "rollNumber": result1["details"]["rollNumber"],
        "collegeCode": result1["details"]["collegeCode"],
        "fatherName": result1["details"]["fatherName"],
        "CGPA": result1["results"]["CGPA"],
        "backlogs": result1["results"]["backlogs"],
        "credits": result1["results"]["credits"],
    }

    student2_profile = {
        "name": result2["details"]["name"],
        "rollNumber": result2["details"]["rollNumber"],
        "collegeCode": result2["details"]["collegeCode"],
        "fatherName": result2["details"]["fatherName"],
        "CGPA": result2["results"]["CGPA"],
        "backlogs": result2["results"]["backlogs"],
        "credits": result2["results"]["credits"],
    }

    # Initialize a dictionary to store semester-wise comparison
    semester_comparison = {}

    # Process semester data for the first student
    for semester in result1["results"]["semesters"]:
        semester_key = semester["semester"]
        semester_comparison[semester_key] = [
            {
                "semester": semester_key,
                "semesterSGPA": semester["semesterSGPA"],
                "semesterCredits": semester["semesterCredits"],
                "semesterGrades": semester["semesterGrades"],
                "backlogs": semester["backlogs"],
                "failed": semester["failed"],
            },
            {
                "semester": semester_key,
                "semesterSGPA": "-",
                "semesterCredits": "-",
                "semesterGrades": "-",
                "backlogs": "-",
                "failed": False,
            },
        ]

    # Process semester data for the second student
    for semester in result2["results"]["semesters"]:
        semester_key = semester["semester"]
        if semester_key in semester_comparison:
            semester_comparison[semester_key][1] = {
                "semester": semester_key,
                "semesterSGPA": semester["semesterSGPA"],
                "semesterCredits": semester["semesterCredits"],
                "semesterGrades": semester["semesterGrades"],
                "backlogs": semester["backlogs"],
                "failed": semester["failed"],
            }
        else:
            semester_comparison[semester_key] = [
                {
                    "semester": semester_key,
                    "semesterSGPA": "-",
                    "semesterCredits": "-",
                    "semesterGrades": "-",
                    "backlogs": "-",
                    "failed": False,
                },
                {
                    "semester": semester_key,
                    "semesterSGPA": semester["semesterSGPA"],
                    "semesterCredits": semester["semesterCredits"],
                    "semesterGrades": semester["semesterGrades"],
                    "backlogs": semester["backlogs"],
                    "failed": semester["failed"],
                },
            ]

    # Combine the results into a single dictionary
    result = {
        "studentProfiles": [student1_profile, student2_profile],
        "semesters": list(semester_comparison.values()),
    }

    return result
