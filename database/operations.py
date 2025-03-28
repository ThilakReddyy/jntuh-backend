from datetime import datetime
from config.connection import prismaConnection
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


async def save_subject_and_marks(rollNumber, result):
    try:
        student = await prismaConnection.prisma.student.find_unique(
            where={"rollNumber": rollNumber}
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
                    "studentId_semesterCode_examCode_subjectId_rcrv": {
                        "studentId": student_id,
                        "semesterCode": semester_code,
                        "examCode": exam_code,
                        "subjectId": subject_id,
                        "rcrv": rcrv,
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
    except Exception as e:
        database_logger.error(f"Database error while inserting exam_codes: {e}")


async def get_exam_codes_from_database(roll_number):
    student = await prismaConnection.prisma.student.find_unique(
        where={"rollNumber": roll_number}
    )

    if not student:
        return set()

    # Fetch only the examCode field instead of all mark data
    marks = await prismaConnection.prisma.mark.find_many(
        where={"studentId": student.id},
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
            order=[{"semesterCode": "asc"}, {"examCode": "asc"}],
        )
        return [student, marks]
    return None
