/**
 * @file scripts/dict-csv.ts
 * @description 다국어 사전 <-> CSV(엑셀) 일괄 내보내기/가져오기
 *
 * 사용법
 *  npm run dict:export                              -> i18n/dict.csv 로 전체 사전 내보내기 (엑셀로 열어서 수정)
 *  npm run dict:import                              -> i18n/dict.csv 를 읽어 ko/en JSON에 일괄 반영
 *  npm run dict:import -- 경로/파일.csv --dry-run   -> 저장하지 않고 바뀔 파일/키/문구만 미리 보기
 *  npm run dict:import -- 경로/파일.csv --force     -> 이미 있는 키의 문구가 다르면 덮어쓰기
 *  npm run dict:import -- --prune --dry-run         -> CSV에서 지운 키를 JSON에서도 삭제 (반드시 dry-run으로 먼저 확인)
 *
 * CSV 형식 (첫 줄은 반드시 헤더, 순서 무관, 중복/추가 컬럼 불가)
 *  file,key,ko,en
 *  serving,DeployName,배포명,Deploy Name
 */
import { execSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";
import Papa from "papaparse";
import { BASE_LOCALE, DICT_DIR, type Dict, DictError, LOCALES, hasKey, readDictFile, setEntry, validateEntry, writeDictFile } from "./dict-shared";

/** 기본 CSV 경로 - 매번 경로를 입력하지 않도록 사전 폴더 옆에 둔다. */
const DEFAULT_CSV = path.resolve("i18n/dict.csv");
/** CSV 헤더 - 사람이 엑셀에서 읽기 쉬운 순서(파일 -> 키 -> 언어들)로 둔다. */
const HEADER = ["file", "key", ...LOCALES];
/** UTF-8 BOM - 이게 있어야 엑셀이 한글 CSV를 깨지지 않게 연다. */
const BOM = "﻿";

/** 검증을 통과한 CSV 한 줄 */
interface Row {
  line: number; // 에러/미리보기에 엑셀 행 번호를 보여주려고 보관한다.
  file: string;
  key: string;
  texts: Dict; // { ko: "...", en: "..." } - 문구는 사람이 쓴 그대로(공백 포함) 보관한다.
}

/** 변경 1건 - dry-run 출력과 실제 저장이 같은 목록을 쓰게 해서 "미리보기 = 실제 결과"를 보장한다. */
interface Change {
  id: string; // "ko/serving" (언어/파일)
  key: string;
  before: string | undefined; // undefined면 신규 추가
  after: string | undefined; // undefined면 삭제 (--prune)
}

//===================
// 내보내기 (JSON -> CSV)
//===================
/** 전체 사전을 CSV로 내보낸다 - 엑셀에서 수정 후 다시 import 하는 "왕복" 작업의 시작점이다. */
function exportCsv(csvPath: string) {
  const baseDir = path.join(DICT_DIR, BASE_LOCALE);
  const files = fs.readdirSync(baseDir).filter((f) => f.endsWith(".json")).sort(); // 정렬해야 export할 때마다 행 순서가 같다.
  const rows: string[][] = [];

  for (const file of files) {
    const name = path.basename(file, ".json");
    const dicts = LOCALES.map((locale) => readDictFile(path.join(DICT_DIR, locale, file)) ?? {}); // 번역 파일이 없으면 빈 칸으로 내보내서 엑셀에서 채우게 한다.
    for (const key of Object.keys(dicts[0])) {
      rows.push([name, key, ...dicts.map((dict) => (hasKey(dict, key) ? dict[key] : ""))]);
    }
  }

  fs.writeFileSync(csvPath, BOM + Papa.unparse({ fields: HEADER, data: rows }), "utf-8"); // 쉼표/따옴표/줄바꿈이 들어간 문구도 Papa가 안전하게 감싸준다.
  console.log(`✔ ${rows.length}개 키를 내보냈습니다 -> ${path.relative(process.cwd(), csvPath)}`);
}

//===================
// 가져오기 (CSV -> JSON)
//===================
/** CSV 읽기 - 엑셀 기본 저장(CP949)이면 한글이 깨지므로, 깨진 파일은 저장 전에 막는다. */
function readCsvText(csvPath: string) {
  if (!fs.existsSync(csvPath)) throw new DictError(`CSV 파일이 없습니다: ${csvPath}`);
  try {
    const text = new TextDecoder("utf-8", { fatal: true }).decode(fs.readFileSync(csvPath)); // fatal: UTF-8이 아니면 깨진 글자로 넘어가지 않고 에러를 낸다.
    const body = text.startsWith(BOM) ? text.slice(1) : text; // BOM이 헤더 이름에 붙으면 "file" 컬럼을 못 찾으므로 떼어낸다.
    return body.replace(/\r\n?/g, "\n"); // 줄바꿈을 \n 하나로 통일한다. 편집기에 따라 \r\n 과 \n 이 섞이면 마지막 값에 줄바꿈 문자가 붙어 다른 문구로 인식된다.
  } catch {
    throw new DictError("CSV가 UTF-8이 아닙니다. 엑셀에서 [다른 이름으로 저장 -> CSV UTF-8(쉼표로 분리)] 로 저장해주세요.");
  }
}

/**
 * 헤더 검사 - Papa의 header 모드는 중복 헤더를 "en_1"처럼 몰래 이름을 바꿔 통과시킨다.
 * 그래서 헤더 줄만 따로 원본 그대로 읽어서 누락/중복/예상 밖 컬럼을 직접 막는다.
 */
function checkHeader(text: string) {
  const first = Papa.parse<unknown[]>(text, { preview: 1 }).data[0] ?? []; // preview: 1 -> 첫 줄만 배열로 읽는다 (이름 변경 없음).
  const cols = first.map((col) => (typeof col === "string" ? col.trim() : ""));

  const dup = cols.filter((col, i) => cols.indexOf(col) !== i);
  const unknown = cols.filter((col) => !HEADER.includes(col));
  const lack = HEADER.filter((col) => !cols.includes(col));

  const errors: string[] = [];
  if (dup.length > 0) errors.push(`중복 컬럼: ${[...new Set(dup)].join(", ")}`);
  if (unknown.length > 0) errors.push(`알 수 없는 컬럼: ${unknown.map((c) => `"${c}"`).join(", ")}`); // 빈 컬럼명("")도 여기서 걸린다.
  if (lack.length > 0) errors.push(`누락 컬럼: ${lack.join(", ")}`);
  if (errors.length > 0) throw new DictError(`CSV 헤더 오류 (올바른 첫 줄: ${HEADER.join(",")})\n  ${errors.join("\n  ")}`);
}

/** CSV 파싱 + 행 단위 검증 - 오류를 한 번에 모아서 보여줘야 엑셀을 여러 번 오가지 않는다. */
function parseRows(text: string) {
  checkHeader(text);
  const result = Papa.parse<unknown>(text, { header: true, skipEmptyLines: "greedy" }); // greedy: 엑셀이 남기는 ",,,," 빈 줄도 건너뛴다.

  // 구문 오류(따옴표 안 닫힘, 열 개수 다름)가 하나라도 있으면 나머지 데이터도 밀렸을 수 있어 전부 중단한다.
  const errors = result.errors.map((e) => `${e.row === undefined ? "?" : e.row + 2}행: CSV 구문 오류 [${e.code}] ${e.message}`);
  if (errors.length > 0) throw new DictError(`CSV 구문 오류 (${errors.length}건) - 따옴표/쉼표 개수를 확인하세요\n  ${errors.join("\n  ")}`);

  const seen = new Map<string, number>(); // "파일.키" -> 행 번호. CSV 안에서 같은 키를 두 번 적은 실수를 잡는다.
  const rows: Row[] = [];

  result.data.forEach((raw, index) => {
    const line = index + 2; // 1행은 헤더라서 데이터는 2행부터 시작한다 (엑셀 행 번호와 맞춘다).
    if (typeof raw !== "object" || raw === null) return;

    const cell = (col: string) => {
      const value: unknown = Reflect.get(raw, col); // 파싱 결과는 모양을 모르므로 unknown으로 꺼내서 좁힌다.
      return typeof value === "string" ? value : "";
    };

    const file = cell("file").trim(); // 식별자(file, key)만 공백 제거: 엑셀에서 붙은 공백 때문에 다른 키로 인식되는 것을 막는다.
    const key = cell("key").trim();
    const texts: Dict = {};
    for (const locale of LOCALES) texts[locale] = cell(locale); // 문구는 trim 하지 않는다. 의도한 공백도 있을 수 있고, export->import 왕복 시 값이 달라지면 안 된다.

    errors.push(...validateEntry(file, key, texts).map((e) => `${line}행: ${e}`)); // dict:add와 같은 검증 정책을 쓴다.

    const id = `${file}.${key}`;
    const firstLine = seen.get(id);
    if (firstLine !== undefined) errors.push(`${line}행: ${id} 가 ${firstLine}행과 중복됩니다.`);
    seen.set(id, line);

    rows.push({ line, file, key, texts });
  });

  if (errors.length > 0) throw new DictError(`CSV 검증 실패 (${errors.length}건)\n  ${errors.join("\n  ")}`);
  if (rows.length === 0) throw new DictError("CSV에 데이터 행이 없습니다.");
  return rows;
}

/**
 * 반영 계획 세우기 - 모든 JSON을 먼저 읽고 비교만 한다 (저장은 아직 안 함).
 * 하나라도 충돌이 있으면 아무 파일도 쓰지 않아야 ko/en이 어긋나지 않는다.
 */
function planImport(rows: Row[], { force, prune }: { force: boolean; prune: boolean }) {
  const dicts = new Map<string, Dict>(); // "ko/serving" -> 사전. 같은 파일을 여러 번 읽지 않고 메모리에서 누적 수정한다.
  const changes: Change[] = [];
  const conflicts: string[] = [];
  let unchanged = 0;

  const load = (id: string) => {
    const cached = dicts.get(id);
    if (cached !== undefined) return cached;
    const dict = readDictFile(path.join(DICT_DIR, `${id}.json`)) ?? {}; // 없는 파일은 빈 사전으로 시작해서 새 페이지 사전을 만든다.
    dicts.set(id, dict);
    return dict;
  };

  for (const { line, file, key, texts } of rows) {
    const diffs = LOCALES.map((locale) => {
      const id = `${locale}/${file}`;
      const dict = load(id);
      return { id, dict, key, before: hasKey(dict, key) ? dict[key] : undefined, after: texts[locale] };
    }).filter((d) => d.before !== d.after); // 이미 같은 문구인 언어는 변경 목록에서 뺀다.

    if (diffs.length === 0) {
      unchanged++; // 같은 CSV를 여러 번 import 해도 안전하다.
      continue;
    }

    const overwrites = diffs.filter((d) => d.before !== undefined);
    if (overwrites.length > 0 && !force) {
      overwrites.forEach((d) => conflicts.push(`${line}행 ${d.id}.${key}: "${d.before}" -> "${d.after}"`));
      continue;
    }

    for (const d of diffs) {
      setEntry(d.dict, key, d.after); // __proto__ 같은 특수 키도 실제 속성으로 저장된다. (메모리에만 반영, 저장은 마지막에)
      changes.push({ id: d.id, key, before: d.before, after: d.after });
    }
  }

  if (conflicts.length > 0) {
    throw new DictError(`기존 문구와 다른 키가 ${conflicts.length}건 있습니다. 덮어쓰려면 --force\n  ${conflicts.join("\n  ")}`);
  }

  // --prune: CSV에서 지운 키를 JSON에서도 삭제한다. 실수로 지운 행이 번역을 날리지 않도록 옵션을 줬을 때만 동작한다.
  if (prune) {
    const csvKeys = new Set(rows.map((r) => `${r.file}.${r.key}`)); // CSV에 남아 있는 "파일.키" 목록
    const files = new Set(rows.map((r) => r.file)); // CSV에 나온 파일만 정리한다. CSV에 없는 파일은 통째로 지워지지 않게 건드리지 않는다.
    for (const file of files) {
      for (const locale of LOCALES) {
        const id = `${locale}/${file}`;
        const dict = load(id);
        for (const key of Object.keys(dict)) {
          if (csvKeys.has(`${file}.${key}`)) continue;
          changes.push({ id, key, before: dict[key], after: undefined });
          delete dict[key]; // 메모리에서만 지운다. 실제 저장은 마지막에 한꺼번에 한다. (en에만 남은 키도 같이 정리된다)
        }
      }
    }
  }
  return { dicts, changes, unchanged };
}

/** 변경 목록 출력 - dry-run이든 실제 실행이든 "무엇이 바뀌는지"를 같은 형식으로 보여준다. */
function printChanges(changes: Change[], unchanged: number) {
  for (const { id, key, before, after } of changes) {
    if (before === undefined) console.log(`  + ${id}.${key}: "${after}"`); // + 신규
    else if (after === undefined) console.log(`  - ${id}.${key}: "${before}"`); // - 삭제
    else console.log(`  ~ ${id}.${key}: "${before}" -> "${after}"`); // ~ 수정
  }
  const added = changes.filter((c) => c.before === undefined).length;
  const deleted = changes.filter((c) => c.after === undefined).length;
  console.log(`  추가 ${added}건 / 수정 ${changes.length - added - deleted}건 / 삭제 ${deleted}건 / 변경 없음 ${unchanged}행 (언어별 건수)`);
}

/** 가져오기 실행 */
function importCsv(csvPath: string, { force, dryRun, prune }: { force: boolean; dryRun: boolean; prune: boolean }) {
  const rows = parseRows(readCsvText(csvPath));
  const { dicts, changes, unchanged } = planImport(rows, { force, prune });
  printChanges(changes, unchanged);

  if (dryRun) {
    console.log("  (--dry-run: 파일은 저장하지 않았습니다)");
    return;
  }
  if (changes.length === 0) return; // 바뀐 게 없으면 파일도, 타입도 건드리지 않는다.

  const dirty = new Set(changes.map((c) => c.id)); // 실제로 바뀐 파일만 저장한다. 안 바뀐 파일을 다시 쓰면 git에 의미 없는 변경이 생길 수 있다.
  for (const id of dirty) {
    const dict = dicts.get(id);
    if (dict !== undefined) writeDictFile(path.join(DICT_DIR, `${id}.json`), dict); // 검사를 모두 통과했을 때만 한꺼번에 저장한다.
  }
  console.log(`  저장한 파일: ${[...dirty].map((id) => `${id}.json`).join(", ")}`);
  execSync("npm run gen:dict", { stdio: "inherit" }); // 생성 로직을 재사용해야 수동 추가/CSV 추가 결과가 항상 같다.
}

//===================
// 실행
//===================
const [mode, ...rest] = process.argv.slice(2);
const csvPath = path.resolve(rest.find((arg) => !arg.startsWith("--")) ?? DEFAULT_CSV);

try {
  if (mode === "export") exportCsv(csvPath);
  else if (mode === "import") importCsv(csvPath, { force: rest.includes("--force"), dryRun: rest.includes("--dry-run"), prune: rest.includes("--prune") });
  else throw new DictError("사용법: dict-csv.ts <export|import> [파일.csv] [--force] [--dry-run] [--prune]");
} catch (err) {
  if (!(err instanceof DictError)) throw err; // 예상 못 한 버그는 숨기지 않는다.
  console.error(`✖ ${err.message}`);
  process.exitCode = 1;
}
