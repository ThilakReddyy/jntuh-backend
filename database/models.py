from typing import List, TypedDict
from prisma.models import student, mark

from utils.helpers import getGradeValue, isGreat


def studentDetailsModel(details: student):
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


def calculateGPA(grades: float, credits: float) -> float:
    return round(grades / credits, 2) if credits > 0 else 0.0


def processResults(results: List[mark]):
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
            grade_value = getGradeValue(subject["grades"])
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

    return {
        "semesters": list(final_result.values()),
        "CGPA": calculateGPA(total_grades, total_credits),
        "backlogs": total_backlogs,
        "credits": total_credits,
        "grades": total_grades,
    }


def studentResultsModel(results: List[mark]):
    return processResults(results)


def studentBacklogs(results: List[mark]):
    processed_results = processResults(results)["semesters"]
    backlogs_data = []
    for sem in processed_results:
        if sem["backlogs"] > 1:
            backlogSubjects = []
            for subject in sem["subjects"]:
                grade_value = getGradeValue(subject["grades"])
                if grade_value == 0:
                    backlogSubjects.append(subject)
            sem["subjects"] = backlogSubjects
            backlogs_data.append(sem)

    total_backlogs = sum(sem["backlogs"] for sem in backlogs_data)

    return {
        "semesters": backlogs_data,
        "totalBacklogs": total_backlogs,
    }
