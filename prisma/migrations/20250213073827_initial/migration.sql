-- CreateTable
CREATE TABLE "student" (
    "id" TEXT NOT NULL,
    "name" TEXT NOT NULL,
    "rollNumber" TEXT NOT NULL,
    "collegeCode" TEXT NOT NULL,
    "fatherName" TEXT NOT NULL DEFAULT '',

    CONSTRAINT "student_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "subject" (
    "id" TEXT NOT NULL,
    "subjectCode" TEXT NOT NULL,
    "subjectName" TEXT NOT NULL,

    CONSTRAINT "subject_pkey" PRIMARY KEY ("id")
);

-- CreateTable
CREATE TABLE "mark" (
    "id" TEXT NOT NULL,
    "studentId" TEXT NOT NULL,
    "subjectId" TEXT NOT NULL,
    "semesterCode" TEXT NOT NULL,
    "examCode" TEXT NOT NULL,
    "internalMarks" TEXT NOT NULL,
    "externalMarks" TEXT NOT NULL,
    "totalMarks" TEXT NOT NULL,
    "grades" TEXT,
    "credits" DOUBLE PRECISION,
    "rcrv" BOOLEAN NOT NULL,

    CONSTRAINT "mark_pkey" PRIMARY KEY ("id")
);

-- CreateIndex
CREATE UNIQUE INDEX "student_rollNumber_key" ON "student"("rollNumber");

-- CreateIndex
CREATE UNIQUE INDEX "subject_subjectCode_key" ON "subject"("subjectCode");

-- CreateIndex
CREATE UNIQUE INDEX "mark_studentId_semesterCode_examCode_subjectId_rcrv_key" ON "mark"("studentId", "semesterCode", "examCode", "subjectId", "rcrv");

-- AddForeignKey
ALTER TABLE "mark" ADD CONSTRAINT "mark_studentId_fkey" FOREIGN KEY ("studentId") REFERENCES "student"("id") ON DELETE RESTRICT ON UPDATE CASCADE;

-- AddForeignKey
ALTER TABLE "mark" ADD CONSTRAINT "mark_subjectId_fkey" FOREIGN KEY ("subjectId") REFERENCES "subject"("id") ON DELETE RESTRICT ON UPDATE CASCADE;
