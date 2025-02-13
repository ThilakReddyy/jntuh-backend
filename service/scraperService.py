# Import necessary libraries
import asyncio
import aiohttp
from bs4 import BeautifulSoup, Tag
import logging


# Define a class for scraping JNTUH results
class ResultScraper:
    def __init__(self, roll_number, url="http://results.jntuh.ac.in/resultAction"):
        # Initialize instance variables
        self.url = url
        self.roll_number = roll_number
        self.results = {"details": {}, "results": []}
        self.exam_code_results = []
        self.failed_exam_codes = []
        self.exam_codes = self._load_exam_codes()
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
        self.logger = logging.getLogger(__name__)
        logging.basicConfig(level=logging.INFO)
        # Exam codes for different regulations and semesters

    def _load_exam_codes(self):
        return {
            "btech": {
                "R18": {
                    "1-1": [
                        "1323",
                        "1358",
                        "1404",
                        "1430",
                        "1467",
                        "1504",
                        "1572",
                        "1615",
                        "1658",
                        "1700",
                        "1732",
                        "1764",
                        "1804",
                    ],
                    "1-2": [
                        "1356",
                        "1363",
                        "1381",
                        "1435",
                        "1448",
                        "1481",
                        "1503",
                        "1570",
                        "1620",
                        "1622",
                        "1656",
                        "1705",
                        "1730",
                        "1769",
                        "1801",
                    ],
                    "2-1": [
                        "1391",
                        "1425",
                        "1449",
                        "1496",
                        "1560",
                        "1610",
                        "1628",
                        "1667",
                        "1671",
                        "1707",
                        "1728",
                        "1772",
                        "1819",
                    ],
                    "2-2": [
                        "1437",
                        "1447",
                        "1476",
                        "1501",
                        "1565",
                        "1605",
                        "1627",
                        "1663",
                        "1711",
                        "1715",
                        "1725",
                        "1776",
                        "1814",
                    ],
                    "3-1": [
                        "1454",
                        "1491",
                        "1550",
                        "1590",
                        "1626",
                        "1639",
                        "1645",
                        "1655",
                        "1686",
                        "1697",
                        "1722",
                        "1784",
                        "1789",
                        "1828",
                        "1832",
                    ],
                    "3-2": [
                        "1502",
                        "1555",
                        "1595",
                        "1625",
                        "1638",
                        "1649",
                        "1654",
                        "1682",
                        "1690",
                        "1696",
                        "1719",
                        "1780",
                        "1788",
                        "1823",
                        "1827",
                    ],
                    "4-1": [
                        "1545",
                        "1585",
                        "1624",
                        "1640",
                        "1644",
                        "1653",
                        "1678",
                        "1695",
                        "1717",
                        "1758",
                        "1762",
                        "1795",
                    ],
                    "4-2": [
                        "1580",
                        "1600",
                        "1623",
                        "1672",
                        "1673",
                        "1677",
                        "1691",
                        "1698",
                        "1716",
                        "1790",
                        "1794",
                        "1808",
                        "1812",
                    ],
                },
                "R22": {
                    "1-1": ["1662", "1699", "1763", "1803"],
                    "1-2": ["1704", "1768", "1800"],
                    "2-1": ["1771", "1818"],
                    "2-2": ["1813"],
                },
            },
            "bpharmacy": {
                "R17": {
                    "1-1": [
                        "519",
                        "537",
                        "577",
                        "616",
                        "643",
                        "683",
                        "722",
                        "781",
                        "824",
                        "832",
                        "855",
                        "893",
                        "936",
                        "973",
                    ],
                    "1-2": [
                        "517",
                        "549",
                        "575",
                        "591",
                        "648",
                        "662",
                        "698",
                        "727",
                        "779",
                        "829",
                        "831",
                        "853",
                        "890",
                        "933",
                        "970",
                    ],
                    "2-1": [
                        "532",
                        "570",
                        "638",
                        "673",
                        "717",
                        "769",
                        "819",
                        "849",
                        "860",
                        "886",
                        "945",
                        "983",
                    ],
                    "2-2": [
                        "558",
                        "611",
                        "650",
                        "661",
                        "693",
                        "711",
                        "774",
                        "814",
                        "845",
                        "882",
                        "897",
                        "940",
                        "978",
                    ],
                    "3-1": [
                        "597",
                        "633",
                        "668",
                        "712",
                        "759",
                        "799",
                        "837",
                        "873",
                        "928",
                        "965",
                    ],
                    "3-2": [
                        "655",
                        "660",
                        "688",
                        "710",
                        "764",
                        "804",
                        "841",
                        "869",
                        "877",
                        "924",
                        "961",
                    ],
                    "4-1": [
                        "663",
                        "705",
                        "754",
                        "794",
                        "832",
                        "836",
                        "865",
                        "920",
                        "953",
                    ],
                    "4-2": ["678", "700", "789", "809", "861", "878", "949", "957"],
                },
                "R22": {
                    "1-1": ["859", "892", "935", "972"],
                    "1-2": ["898", "932", "969"],
                    "2-1": ["944", "982"],
                    "2-2": ["977"],
                },
            },
            "mtech": {
                "R19": {
                    "1-1": [
                        "319",
                        "332",
                        "347",
                        "356",
                        "371",
                        "382",
                        "388",
                        "395",
                        "414",
                        "422",
                    ],
                    "1-2": [
                        "328",
                        "336",
                        "344",
                        "353",
                        "368",
                        "379",
                        "387",
                        "393",
                        "412",
                        "420",
                    ],
                    "2-1": ["337", "350", "365", "376", "386", "391", "410", "418"],
                    "2-2": ["340", "374", "385", "390", "416"],
                },
                "R22": {
                    "1-1": ["389", "394", "413", "421"],
                    "1-2": ["392", "411", "419"],
                    "2-1": ["409", "417"],
                    "2-2": ["415"],
                },
            },
            "mpharmacy": {
                "R19": {
                    "1-1": [
                        "161",
                        "177",
                        "185",
                        "198",
                        "209",
                        "215",
                        "222",
                        "240",
                        "248",
                    ],
                    "1-2": [
                        "157",
                        "165",
                        "174",
                        "182",
                        "195",
                        "206",
                        "214",
                        "220",
                        "238",
                        "246",
                    ],
                    "2-1": ["166", "180", "194", "204", "213", "218", "236", "244"],
                    "2-2": ["169", "203", "212", "217", "242"],
                },
                "R22": {
                    "1-1": ["216", "221", "239", "247"],
                    "1-2": ["219", "237", "245"],
                    "2-1": ["235", "243"],
                    "2-2": ["241"],
                },
            },
            "mba": {
                "R19": {
                    "1-1": [
                        "297",
                        "316",
                        "323",
                        "350",
                        "362",
                        "368",
                        "374",
                        "405",
                        "413",
                    ],
                    "1-2": [
                        "122",
                        "293",
                        "302",
                        "313",
                        "320",
                        "347",
                        "359",
                        "367",
                        "372",
                        "403",
                        "411",
                    ],
                    "2-1": ["303", "310", "344", "356", "366", "376", "401", "409"],
                    "2-2": ["120", "307", "341", "353", "365", "375", "399", "407"],
                },
                "R22": {
                    "1-1": ["369", "373", "404", "412"],
                    "1-2": ["371", "402", "410"],
                    "2-1": ["400", "408"],
                    "2-2": ["406"],
                },
            },
        }
        # GPA conversion table

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
            self.url + payloaddata, ssl=False, headers=headers
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

        except Exception as e:
            self.failed_exam_codes.append(semester_code)
            self.logger.error(f"Error processing results for {self.roll_number}: {e}")

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

        codes_to_fetch = failed_exam_codes if failed_exam_codes else exam_codes
        payloads = self.payloads[degree]

        async with aiohttp.ClientSession() as session:
            for exam_code in codes_to_fetch:  # Use codes_to_fetch instead of exam_codes
                for code in codes_to_fetch[exam_code]:
                    tasks[code] = []
                    for payload in payloads:
                        try:
                            task = asyncio.create_task(
                                self.fetch_result(session, code, payload)
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
                            and "Internal Server Error" not in response
                        ):
                            self.scrape_results(exam_code, response)
                except Exception as e:
                    self.logger.error(f"Error fetching resultgs for {exam_code}: {e}")
            for exam_result in self.exam_code_results:
                exam_code = exam_result["examCode"]
                for semester, codes in exam_codes.items():
                    if exam_code in codes:
                        exam_result["semesterCode"] = semester

        self.results["results"] = self.exam_code_results

    async def run(self):
        try:
            await self.scrape_all_results()
            retries = 0
            while self.failed_exam_codes and retries < 6:
                retries += 1
                failed_codes = list(set(self.failed_exam_codes))
                self.failed_exam_codes = []
                await self.scrape_all_results(failed_codes)

            if bool(self.results["details"]):
                return self.results
            return None
        except Exception as e:
            self.logger.error(f"Fatal error: {e}")
            return None
