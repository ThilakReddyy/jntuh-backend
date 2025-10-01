from datetime import datetime, timedelta
import json

from collections import defaultdict

from prisma.types import examcodesWhereInput
from config.connection import prismaConnection
from database.models import PushSub
from utils.helpers import format_date
from utils.logger import database_logger


async def save_details(details):
    try:
        await prismaConnection.prisma.student.upsert(
            where={"rollNumber": details["rollNo"]},
            data={
                "create": {
                    "rollNumber": details["rollNo"],
                    "name": details["name"],
                    "collegeCode": details["collegeCode"],
                    "fatherName": details["fatherName"],
                },
                "update": {
                    "lastUpdated": datetime.now(),
                },
            },
        )

    except Exception as e:
        database_logger.error(f"Database error while inserting student data: {e}")


async def save_subject_and_marks(rollNumber, result, graceMarks=False):
    try:
        student = await prismaConnection.prisma.student.find_unique(
            where={"rollNumber": rollNumber},
        )
        if not student:
            database_logger.error(
                f"Database error while inserting student data: {rollNumber}"
            )
            return

        student_id = student.id
        exam_code = result["examCode"]
        semester_code = result["semesterCode"]
        rcrv = result["rcrv"]
        subjects = result["subjects"]

        for subject in subjects:
            subject_record = await prismaConnection.prisma.subject.upsert(
                where={"subjectCode": subject["subjectCode"]},
                data={
                    "create": {
                        "subjectCode": subject["subjectCode"],
                        "subjectName": subject["subjectName"],
                    },
                    "update": {},
                },
            )
            subject_id = subject_record.id
            await prismaConnection.prisma.mark.upsert(
                where={
                    "studentId_semesterCode_examCode_subjectId_rcrv_graceMarks": {
                        "studentId": student_id,
                        "semesterCode": semester_code,
                        "examCode": exam_code,
                        "subjectId": subject_id,
                        "rcrv": rcrv,
                        "graceMarks": graceMarks,
                    }
                },
                data={
                    "create": {
                        "studentId": student_id,
                        "subjectId": subject_id,
                        "semesterCode": semester_code,
                        "examCode": exam_code,
                        "internalMarks": subject["subjectInternal"],
                        "externalMarks": subject["subjectExternal"],
                        "totalMarks": subject["subjectTotal"],
                        "grades": subject["subjectGrade"],
                        "credits": float(subject["subjectCredits"]),
                        "rcrv": rcrv,
                    },
                    "update": {},
                },
            )

    except Exception as e:
        database_logger.error(
            f"Database error while inserting student marks: {rollNumber}:{e}"
        )


async def save_exam_codes(results):
    try:
        exam_pairs = [
            (result["rcrv"], result["examCode"], result["date"]) for result in results
        ]
        existing_exams = await prismaConnection.prisma.examcodes.find_many(
            where={
                "OR": [
                    {"rcrv": pair[0], "examCode": pair[1], "date": pair[2]}
                    for pair in exam_pairs
                ]
            },
        )

        existing_pairs = {
            (exam.rcrv, exam.examCode, exam.date) for exam in existing_exams
        }

        new_exams = [
            exam
            for exam in results
            if (exam["rcrv"], exam["examCode"], exam["date"]) not in existing_pairs
        ]
        if new_exams:
            # Bulk insert only new records
            inserted_records = await prismaConnection.prisma.examcodes.create_many(
                data=new_exams
            )
            database_logger.info(f"Inserted {inserted_records} new records")
        else:
            database_logger.info("No new records to insert")
        return new_exams
    except Exception as e:
        database_logger.error(f"Database error while inserting exam_codes: {e}")


async def get_exam_codes_from_database(roll_number, rcrv=False):
    student = await prismaConnection.prisma.student.find_unique(
        where={"rollNumber": roll_number}
    )

    if not student:
        return set()

    # Fetch only the examCode field instead of all mark data
    marks = await prismaConnection.prisma.mark.find_many(
        where={"studentId": student.id, "rcrv": rcrv},
    )

    # Use a set comprehension for better performance
    return {mark.examCode for mark in marks}


async def save_to_database(results):
    details = results["details"]
    rollNo = details["rollNo"]
    results = results["results"]
    await save_details(details)
    for result in results:
        await save_subject_and_marks(rollNo, result)
    database_logger.info(f"Exam data and marks saved for student {rollNo}")


async def get_details(roll_number: str):
    student = await prismaConnection.prisma.student.find_unique(
        where={"rollNumber": roll_number}
    )
    if student:
        marks = await prismaConnection.prisma.mark.find_many(
            where={"studentId": student.id},
            include={"subject": True},
            order=[
                {"semesterCode": "asc"},
                {"examCode": "asc"},
                {"rcrv": "asc"},
                {"graceMarks": "asc"},
            ],
        )
        return [student, marks]
    return None


async def get_students_details(rollNumber: str, roll_number2: str):
    students = await prismaConnection.prisma.student.find_many(
        where={
            "OR": [
                {"rollNumber": {"startswith": rollNumber}},
                {"rollNumber": {"startswith": roll_number2}},
            ]
        },
        order=[{"rollNumber": "asc"}],
    )

    if not students:
        return None

    student_ids = [s.id for s in students]

    marks = await prismaConnection.prisma.mark.find_many(
        where={"studentId": {"in": student_ids}},
        order=[
            {"studentId": "asc"},
            {"semesterCode": "asc"},
            {"examCode": "asc"},
            {"rcrv": "asc"},
            {"graceMarks": "asc"},
        ],
        include={"subject": True},
    )

    marks_by_student = defaultdict(list)
    for mark in marks:
        marks_by_student[mark.studentId].append(mark)

    for student in students:
        student.marks = marks_by_student.get(student.id, [])

    return students


async def get_subscription_roll_number(roll_number: str):
    record = await prismaConnection.prisma.anonpushsubscription.find_first(
        where={"rollNumber": roll_number},
        order=[{"createdAt": "desc"}],
    )
    return record


async def get_all_subscriptions():
    record = await prismaConnection.prisma.anonpushsubscription.find_many()
    return record


async def get_notifications(
    page: int, regulation: str = "", degree: str = "", year: str = "", title: str = ""
):
    page_size = 10  # Adjust as needed
    skip = (page - 1) * page_size
    where_clause: examcodesWhereInput = {}
    if regulation:
        where_clause["regulation"] = regulation
    if degree:
        where_clause["degree"] = degree
    if year:
        where_clause["releaseDate"] = {
            "contains": str(year),  # Equivalent to SQL's LIKE '%year%'
            "mode": "insensitive",  # Optional: Makes it case-insensitive
        }
    if title:
        where_clause["title"] = {
            "contains": str(title),  # Equivalent to SQL's LIKE '%year%'
            "mode": "insensitive",  # Optional: Makes it case-insensitive
        }

    notifications = await prismaConnection.prisma.examcodes.find_many(
        where=where_clause,
        skip=skip,
        take=page_size,
        order={"releaseDate": "desc"},
    )
    results = []
    for notification in notifications:
        results.append(
            {
                "title": notification.title,
                "releaseDate": notification.releaseDate,
                "date": notification.date,
                "link": notification.link,
            }
        )
    return results


async def get_exam_codes(degree, regulation):
    examCodesFromDb = await prismaConnection.prisma.examcodes.find_many(
        where={"degree": degree, "regulation": regulation},
        order=[{"semesterCode": "asc"}, {"examCode": "asc"}],
    )
    examCodes = {}
    for examcode in examCodesFromDb:
        if examcode.semesterCode not in examCodes:
            examCodes[examcode.semesterCode] = set()
        examCodes[examcode.semesterCode].add(examcode.examCode)

    for examCode in examCodes:
        examCodes[examCode] = list(examCodes[examCode])
        examCodes[examCode].sort()

    return examCodes


async def check_4_2_semester(rollNumber: str):
    student = await prismaConnection.prisma.student.find_unique(
        where={"rollNumber": rollNumber},
    )
    if student:
        marks = await prismaConnection.prisma.mark.find_first(
            where={"studentId": student.id, "semesterCode": "4-2"},
            include={"subject": True},
        )

        return marks
    return None


async def get_subscription_by_anon_key(anon_key: str):
    existing = await prismaConnection.prisma.anonpushsubscription.find_unique(
        where={"anonId": anon_key}
    )
    return existing


async def save_subscription_details(data: PushSub):
    subscription_str = json.dumps(data.subscription)

    return await prismaConnection.prisma.anonpushsubscription.upsert(
        where={"anonId": data.anon_id},
        data={
            "update": {
                "rollNumber": data.roll_number,
                "subscription": subscription_str,
            },
            "create": {
                "anonId": data.anon_id,
                "rollNumber": data.roll_number,
                "subscription": subscription_str,
            },
        },
    )


async def get_latest_notifications():
    today = datetime.utcnow()
    two_weeks_ago = today - timedelta(days=14)

    exams = await prismaConnection.prisma.examcodes.find_many(
        where={
            "releaseDate": {
                "gte": format_date(two_weeks_ago),
                "lte": format_date(today),
            }
        },
        order={"releaseDate": "asc"},
    )
    results = []
    for notification in exams:
        results.append(
            {
                "title": notification.title,
                "releaseDate": notification.releaseDate,
                "date": notification.date,
                "link": notification.link,
            }
        )
    return results
