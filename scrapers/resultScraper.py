# Import necessary libraries
import asyncio
from itertools import chain
import aiohttp
from bs4 import BeautifulSoup, Tag
from data.examCodes import load_exam_codes
from utils.logger import scraping_logger


# Define a class for scraping JNTUH results
class ResultScraper:
    def __init__(
        self,
        roll_number,
        omit_exam_codes,
        url="http://results.jntuh.ac.in/resultAction",
    ):
        # Initialize instance variables
        self.url = url
        self.roll_number = roll_number
        self.results = {"details": {}, "results": []}
        self.exam_code_results = []
        self.failed_exam_codes = []
        self.exam_codes = load_exam_codes()
        self.omit_exam_codes = omit_exam_codes
        self.grades_to_gpa = {
            "O": 10,
            "A+": 9,
            "A": 8,
            "B+": 7,
            "B": 6,
            "C": 5,
            "F": 0,
            "Ab": 0,
            "-": 0,
        }
        self.payloads = self._load_payloads()
        self.logger = scraping_logger
        # Exam codes for different regulations and semesters

    def _load_payloads(self):
        # Payloads for different types of result requests
        return {
            "btech": [
                "&degree=btech&etype=r17&result=null&grad=null&type=intgrade&htno=",
                "&degree=btech&etype=r17&result=gradercrv&grad=null&type=rcrvintgrade&htno=",
            ],
            "bpharmacy": [
                "&degree=bpharmacy&etype=r17&grad=null&result=null&type=intgrade&htno=",
                "&degree=bpharmacy&etype=r17&grad=null&result=gradercrv&type=rcrvintgrade&htno=",
            ],
            "mba": [
                "&degree=mba&grad=pg&etype=null&result=grade17&type=intgrade&htno=",
                "&degree=mba&grad=pg&etype=r16&result=gradercrv&type=rcrvintgrade&htno=",
            ],
            "mpharmacy": [
                "&degree=mpharmacy&etype=r17&grad=pg&result=null&type=intgrade&htno=",
                "&degree=mpharmacy&etype=r17&grad=pg&result=gradercrv&type=rcrvintgrade&htno=",
            ],
            "mtech": [
                "&degree=mtech&grad=pg&etype=null&result=grade17&type=intgrade&htno=",
                "&degree=mtech&grad=pg&etype=r16&result=gradercrv&type=rcrvintgrade&htno=",
            ],
        }

    async def fetch_result(self, session, exam_code, payload):
        payloaddata = "?&examCode=" + exam_code + payload + self.roll_number
        headers = {
            "Upgrade-Insecure-Requests": "1",
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.9",
        }
        async with session.get(
            self.url + payloaddata, ssl=False, headers=headers, timeout=5
        ) as response:
            return await response.text()

    def scrape_results(self, semester_code, response):
        try:
            soup = BeautifulSoup(response, "lxml")
            table = soup.find_all("table")
            details_table, results_table = table[:2]

            if not isinstance(details_table, Tag) or not isinstance(results_table, Tag):
                return
            details = details_table.find_all("tr")
            htnoAndName = details[0]
            fatherNameAndCollegeCode = details[1]
            if not isinstance(fatherNameAndCollegeCode, Tag) or not isinstance(
                htnoAndName, Tag
            ):
                return
            htno = htnoAndName.find_all("td")[1].get_text()
            name = htnoAndName.find_all("td")[3].get_text()

            fatherName = fatherNameAndCollegeCode.find_all("td")[1].get_text()
            collegeCode = fatherNameAndCollegeCode.find_all("td")[3].get_text()

            self.results["details"] = {
                "name": name,
                "rollNo": htno,
                "collegeCode": collegeCode,
                "fatherName": fatherName,
            }

            results = results_table.find_all("tr")
            if not results:
                return
            column_results = results[0]
            if not isinstance(column_results, Tag):
                return
            columns = [content.text for content in column_results.find_all("b")]
            grade_index = columns.index("GRADE")
            subject_name_index = columns.index("SUBJECT NAME")
            subject_code_index = columns.index("SUBJECT CODE")
            subject_credits_index = columns.index("CREDITS(C)")
            subject_internal_marks_index = -1
            subject_external_marks_index = -1
            subject_total_marks_index = -1

            try:
                subject_internal_marks_index = columns.index("INTERNAL")
                subject_external_marks_index = columns.index("EXTERNAL")
                subject_total_marks_index = columns.index("TOTAL")
            except ValueError:
                pass

            subjects = []
            rcrv = False
            for row in results[1:]:
                if not isinstance(row, Tag):
                    return
                if "Change in Grade" in row.find_all("td")[-1].get_text():
                    rcrv = True
                subject_code = row.find_all("td")[subject_code_index].get_text()

                result = {
                    "subjectCode": subject_code,
                    "subjectName": row.find_all("td")[subject_name_index].get_text(),
                    "subjectGrade": row.find_all("td")[grade_index].get_text(),
                    "subjectCredits": row.find_all("td")[
                        subject_credits_index
                    ].get_text(),
                }
                result["subjectCode"] = subject_code

                try:
                    result["subjectInternal"] = row.find_all("td")[
                        subject_internal_marks_index
                    ].get_text()
                    result["subjectExternal"] = row.find_all("td")[
                        subject_external_marks_index
                    ].get_text()
                    result["subjectTotal"] = row.find_all("td")[
                        subject_total_marks_index
                    ].get_text()

                except Exception as e:
                    self.logger.error(
                        f"Error extracting results for {self.roll_number}: {e}"
                    )
                subjects.append(result)
            self.exam_code_results.append(
                {"examCode": semester_code, "subjects": subjects, "rcrv": rcrv}
            )

        except Exception:
            self.failed_exam_codes.append(semester_code)
            # self.logger.error(f"Error processing results for {self.roll_number}: {e}")

    def _determine_degree(self):
        degree_map = {
            "A": "btech",
            "R": "bpharmacy",
            "E": "mba",
            "D": "mtech",
            "S": "mpharmacy",
        }
        return degree_map.get(self.roll_number[5])

    def _determine_regulation(self):
        grad_year = int(self.roll_number[:2])
        if grad_year >= 23 or (grad_year == 22 and self.roll_number[4] != "5"):
            return "R22"

        regulation_map = {"A": "R18", "R": "R17"}
        return regulation_map.get(self.roll_number[5], "R19")

    async def scrape_all_results(self, failed_exam_codes=[]):
        tasks = {}
        degree = self._determine_degree()

        if degree is None:
            return

        exam_codes = self.exam_codes[degree][self._determine_regulation()]

        if self.roll_number[4] == "5":
            exam_codes.pop("1-1", None)
            exam_codes.pop("1-2", None)

        flattened_list = list(chain(*exam_codes.values()))
        codes_to_fetch = failed_exam_codes if failed_exam_codes else flattened_list
        payloads = self.payloads[degree]
        try:
            async with aiohttp.ClientSession() as session:
                for code in codes_to_fetch:
                    tasks[code] = []
                    if code not in self.omit_exam_codes:
                        try:
                            task = asyncio.create_task(
                                self.fetch_result(session, code, payloads[0])
                            )
                            tasks[code].append(task)
                        except Exception as e:
                            self.logger.error(
                                f"Error calling the api for {self.roll_number}:{e}"
                            )
                    try:
                        task = asyncio.create_task(
                            self.fetch_result(session, code, payloads[1])
                        )
                        tasks[code].append(task)
                    except Exception as e:
                        self.logger.error(
                            f"Error calling the api for {self.roll_number}:{e}"
                        )

                for exam_code, exam_tasks in tasks.items():
                    try:
                        responses = await asyncio.gather(*exam_tasks)
                        for response in responses:
                            if (
                                "Enter HallTicket Number" not in response
                                and "SUBJECT CODE" in response
                                # and "Internal Server Error" not in response
                            ):
                                self.scrape_results(exam_code, response)
                    except Exception as e:
                        self.logger.error(
                            f"Error fetching resultgs for {exam_code}: {e}"
                        )
                        self.failed_exam_codes.append(exam_code)
                for exam_result in self.exam_code_results:
                    exam_code = exam_result["examCode"]
                    for semester, codes in exam_codes.items():
                        if exam_code in codes:
                            exam_result["semesterCode"] = semester

            self.results["results"] = self.exam_code_results
        except Exception as e:
            scraping_logger.warning(
                f"Something unexpecting has happend while scraping results: {e}"
            )

    async def run(self):
        try:
            await self.scrape_all_results()
            retries = 0
            while self.failed_exam_codes and retries < 15:
                retries += 1
                failed_codes = list(set(self.failed_exam_codes))
                self.failed_exam_codes = []
                scraping_logger.info(
                    f"The roll_number {self.roll_number} has failed to get the exam codes of len {len(self.failed_exam_codes)} retrying again in {retries}"
                )
                await self.scrape_all_results(failed_codes)
            if self.failed_exam_codes:
                scraping_logger.info(
                    f"The roll_number {self.roll_number} has failed to get the exam codes of len {len(self.failed_exam_codes)}"
                )
                return None
            if retries:
                scraping_logger.info(
                    f"Successfully extracted results fo {self.roll_number} in {retries+1} attempts"
                )

            if bool(self.results["details"]):
                return self.results

            return None
        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            return None
