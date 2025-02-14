-- AlterTable
ALTER TABLE "student" ADD COLUMN     "lastUpdated" TIMESTAMP(3) NOT NULL DEFAULT CURRENT_TIMESTAMP;

-- CreateIndex
CREATE INDEX "student_rollNumber_idx" ON "student"("rollNumber");
