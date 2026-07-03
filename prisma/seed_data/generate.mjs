/**
 * Extracts the static academic-calendar and syllabus data from the web frontend's
 * TypeScript constants and flattens them into JSON seed files for the backend DB.
 *
 * The TS constants are plain object literals (string keys/values, arrays of
 * {title, link}) with trailing commas and `//` comments — all valid JS — so we
 * slice out the object literal and eval it.
 *
 * Usage: node generate.mjs   (run from prisma/seed_data)
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const FRONTEND = path.resolve(__dirname, "../../../JNTUHRESULTS-WEB/constants");

/** Read a TS constant file and eval the first `= { ... };` object literal. */
function loadObject(file) {
  const text = fs.readFileSync(file, "utf8");
  // Grab from the first `= {` (the const assignment) to the final `};`.
  const eq = text.indexOf("= {");
  if (eq === -1) throw new Error(`No object literal in ${file}`);
  const end = text.lastIndexOf("};");
  const literal = text.slice(eq + 2, end + 1); // include closing }
  // eslint-disable-next-line no-eval
  return eval("(" + literal + ")");
}

// ---- Academic calendars: year -> degree -> studyYear -> { title: link } ----
function flattenCalendars(obj) {
  const rows = [];
  for (const academicYear of Object.keys(obj)) {
    const byDegree = obj[academicYear];
    for (const degree of Object.keys(byDegree)) {
      const byStudyYear = byDegree[degree];
      for (const studyYear of Object.keys(byStudyYear)) {
        const titles = byStudyYear[studyYear];
        for (const title of Object.keys(titles)) {
          const link = titles[title];
          if (typeof link === "string" && link.trim()) {
            rows.push({ academicYear, degree, studyYear, title, link });
          }
        }
      }
    }
  }
  return rows;
}

// ---- Syllabus: recursive folder tree; leaves are PdfItem[] ----
function flattenSyllabus(node, trail, rows) {
  if (Array.isArray(node)) {
    const degree = trail[0] ?? "";
    const regulation = trail[1] ?? "";
    const category = trail.slice(2).join(" / ") || regulation || "General";
    for (const item of node) {
      if (item && item.title && item.link) {
        rows.push({ degree, regulation, category, title: item.title, link: item.link });
      }
    }
    return;
  }
  if (node && typeof node === "object") {
    for (const key of Object.keys(node)) {
      flattenSyllabus(node[key], [...trail, key], rows);
    }
  }
}

function dedupe(rows, keyFn) {
  const seen = new Set();
  const out = [];
  for (const r of rows) {
    const k = keyFn(r);
    if (!seen.has(k)) {
      seen.add(k);
      out.push(r);
    }
  }
  return out;
}

const calendarsObj = loadObject(path.join(FRONTEND, "academiccalendars.tsx"));
const syllabusObj = loadObject(path.join(FRONTEND, "syllabusdetails.tsx"));

let calendars = flattenCalendars(calendarsObj);
calendars = dedupe(calendars, (r) => `${r.academicYear}|${r.degree}|${r.studyYear}|${r.title}|${r.link}`);

const syllabus = [];
flattenSyllabus(syllabusObj, [], syllabus);
const syllabusDeduped = dedupe(syllabus, (r) => `${r.degree}|${r.regulation}|${r.category}|${r.title}|${r.link}`);

fs.writeFileSync(path.join(__dirname, "calendars.json"), JSON.stringify(calendars, null, 2));
fs.writeFileSync(path.join(__dirname, "syllabus.json"), JSON.stringify(syllabusDeduped, null, 2));

console.log(`calendars: ${calendars.length} rows`);
console.log(`syllabus:  ${syllabusDeduped.length} rows`);
