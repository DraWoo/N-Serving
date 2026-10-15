/**
 * @file scripts/generate-dict-types.ts
 * @description dictionaries/{ko,en}/*.json -> i18n/dict.generate.d.ts 타입 자동 생성
 *
 * 사용법
 *  - 1회 생성 : npm run gen:dict             (번역 누락 시 종료 코드 1 -> 빌드 중단)
 *  - 감시 모드 : npm run gen:dict -- --watch  (JSON 저장할 때마다 재생성, 오류가 나도 계속 감시)
 */
import * as fs from "node:fs";
import * as path from "node:path";
import { BASE_LOCALE, DICT_DIR, DictError, OTHER_LOCALES, fileError, hasKey, keyError, readDictFile, toPascalCase } from "./dict-shared";

/** 자동 생성 파일 위치 - 기존 경로를 유지해야 import 경로를 바꾸지 않아도 된다. */
const OUT_FILE = path.resolve("i18n/dict.generate.d.ts");

/** ANSI 색상 코드 - 터미널에서 성공/경고/에러를 눈으로 빠르게 구분하려고 쓴다. */
const c = {
  reset: "\x1b[0m", // 모든 스타일 초기화
  bold: "\x1b[1m", // 굵게
  dim: "\x1b[2m", // 흐릿하게

  // 텍스트 색상
  red: "\x1b[31m",
  green: "\x1b[32m",
  yellow: "\x1b[33m",
  blue: "\x1b[34m",
  magenta: "\x1b[35m",
  cyan: "\x1b[36m",
  gray: "\x1b[90m",

  // 배경 색상
  bgGreen: "\x1b[42m",
  bgRed: "\x1b[41m",
  bgYellow: "\x1b[43m",
};

//===================
// 출력 헬퍼
//===================
/** 구분선 - 실행 결과 묶음을 시각적으로 나누기 위해 쓴다. */
function divider() {
  console.log(`${c.gray}${"=".repeat(64)}${c.reset}`);
}

/** 헤더 박스 - 여러 스크립트 로그 사이에서 "다국어 생성 결과"가 어디서 시작하는지 바로 찾게 해준다. */
function header(title: string) {
  divider();
  console.log(`${c.bold}${c.cyan} ${title}${c.reset}`);
  divider();
}

/** 라벨 + 값 출력 - 라벨 폭을 맞춰야 요약이 표처럼 정렬된다. */
function info(label: string, value: string) {
  console.log(`${c.cyan}${label.padEnd(12, " ")}${c.reset} ${value}`);
}

/** 경고 라벨 - 빌드는 계속되지만 알아야 할 내용(키 중복 등)에 쓴다. */
/** 한글의 화면 너비를 반영해 모든 값이 같은 위치에서 시작하도록 출력합니다. */
function info(label: string, value: string) { // 기존 호출 방식을 유지해 출력부만 수정합니다.
  const koreanCount = Array.from(label).filter((char) => /[ㄱ-ㅎㅏ-ㅣ가-힣]/u.test(char)).length; // 한글은 문자열 길이보다 화면에서 한 칸씩 더 차지하므로 개수를 셉니다.
  const displayWidth = label.length + koreanCount; // 현재 라벨에 사용하는 한글·영문·공백의 화면 너비를 계산합니다.
  const padding = " ".repeat(Math.max(0, 14 - displayWidth)); // 라벨 영역을 14칸으로 맞춰 값의 시작 위치를 고정합니다.
  console.log(`${c.cyan}${label}${padding}${c.reset} : ${value}`); // 너비 계산 후 색상을 적용해 색상 코드가 정렬에 영향을 주지 않게 합니다.
} // 입력 정보와 결과 요약에 같은 정렬 기준을 적용합니다.

/** 에러 라벨 - 반드시 고쳐야 하는 내용에 쓴다. */
function error(message: string) {
  console.error(`${c.bgRed}${c.bold} ✖ ERROR ${c.reset} ${c.red}${message}${c.reset}`);
}

/** 성공 라벨 - 생성 완료를 한눈에 확인하려고 쓴다. */
function success(message: string) {
  console.log(`${c.bgGreen}${c.bold} ✔ SUCCESS ${c.reset} ${c.green}${message}${c.reset}`);
}

/** JSDoc 안전 처리 - 값에 '*\/'나 줄바꿈이 있으면 주석이 깨지므로 미리 치환한다. */
function escapeForJSDoc(value: string) {
  return value.replace(/\*\//g, "*\\/").replace(/\n/g, " ");
}

/** 바이트 표시 - 괄호가 없으면 /1024*1024 = 원래 값이 되므로 반드시 묶는다. */
function formatBytes(bytes: number) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

//===================
// 메인 로직
//===================
/**
 * 타입 파일 생성
 * - 구조 오류(JSON 문법, 키/파일명 규칙, 타입명 충돌) : 즉시 throw -> 파일 생성 안 함
 * - 번역 누락(en 파일/키 없음)                       : 모아서 반환 -> 파일은 생성(미리보기 유지), 실행은 실패 처리
 */
function generate() {
  const baseDir = path.join(DICT_DIR, BASE_LOCALE);
  if (!fs.existsSync(baseDir)) throw new DictError(`기준 언어 폴더가 없습니다: ${baseDir}`);

  const files = fs.readdirSync(baseDir).filter((f) => f.endsWith(".json")).sort(); // 정렬해야 출력 순서가 항상 같아 git diff가 깔끔하다.
  if (files.length === 0) throw new DictError(`${BASE_LOCALE}/*.json 파일이 없습니다.`);

  info("입력 폴더", `${c.dim}${baseDir}${c.reset}`); // 경로가 틀렸을 때(실행 위치 문제 등) 바로 알 수 있게 실제 경로를 보여준다.
  info("출력 파일", `${c.dim}${OUT_FILE}${c.reset}`);
  info("처리 파일", `${c.yellow}${files.length}개${c.reset}`);
  console.log("");

  const missing: string[] = []; // 번역 누락 목록. 한 번에 모아서 보여줘야 여러 번 실행하며 하나씩 고치지 않아도 된다.
  const ifaceOwner = new Map<string, string>(); // 타입 이름 -> 파일명. 서로 다른 파일이 같은 타입 이름이 되는 것을 막는다.
  const keyOwner = new Map<string, string>(); // 키 -> 파일명. 파일 간 같은 키가 덮어써지는 것을 알린다.
  const entries: { name: string; iface: string }[] = [];
  let body = "";
  let totalKeys = 0;

  for (const file of files) {
    const name = path.basename(file, ".json");
    const badFile = fileError(name);
    if (badFile !== null) throw new DictError(badFile);

    const iface = `${toPascalCase(name)}Dict`;
    const sameIface = ifaceOwner.get(iface);
    if (sameIface !== undefined) throw new DictError(`${sameIface}.json 과 ${file} 이 같은 타입 이름(${iface})으로 변환됩니다. 파일명을 바꿔주세요.`);
    ifaceOwner.set(iface, name);

    const baseDict = readDictFile(path.join(baseDir, file)) ?? {}; // 목록에서 읽은 파일이라 null일 일은 없지만 타입상 기본값을 둔다.
    if (Object.keys(baseDict).length === 0) warn(`${BASE_LOCALE}/${file} 에 키가 없습니다. (key 0개)`); // {}는 정상이지만 실수로 비운 건지 확인할 수 있게 알린다.
    const others = OTHER_LOCALES.map((locale) => ({ locale, dict: readDictFile(path.join(DICT_DIR, locale, file)) }));

    for (const { locale, dict } of others) {
      if (dict === null) {
        missing.push(`${locale}/${file} 파일 없음`);
        continue;
      }
      const lack = Object.keys(baseDict).filter((key) => !hasKey(dict, key)); // in 대신 hasKey: constructor 같은 상속 속성을 "있다"고 착각하지 않는다.
      if (lack.length > 0) missing.push(`${locale}/${file} 키 없음: ${lack.join(", ")}`);
    }

    body += `/** ${name}.json 사전 타입 */\n`;
    body += `export interface ${iface} {\n`;

    for (const [key, koText] of Object.entries(baseDict)) {
      const badKey = keyError(key);
      if (badKey !== null) throw new DictError(`${BASE_LOCALE}/${file}: ${badKey}`);

      const sameKey = keyOwner.get(key);
      if (sameKey !== undefined) warn(`키 중복 "${key}" (${sameKey}.json, ${file}) - 페이지 사전 값이 우선 적용됩니다.`);
      keyOwner.set(key, name);

      const previews = others.map(({ locale, dict }) => {
        const text = dict !== null && hasKey(dict, key) ? dict[key] : "⚠ 번역 없음"; // 실제 내 속성일 때만 값을 꺼내야 함수 같은 상속 값이 섞이지 않는다.
        return `${locale}: ${escapeForJSDoc(text)}`;
      });
      body += `  /** ${BASE_LOCALE}: ${escapeForJSDoc(koText)} | ${previews.join(" | ")} */\n`; // hover 시 모든 언어를 한 번에 보여준다.
      body += `  ${key}: string;\n`;
    }
    body += `}\n\n`;

    entries.push({ name, iface });
    totalKeys += Object.keys(baseDict).length;
    console.log(` ${c.green}✔${c.reset} ${c.bold}${file.padEnd(20)}${c.reset} -> ${c.cyan}${iface}${c.reset} ${c.gray}(${Object.keys(baseDict).length}개 키)${c.reset}`);
  }

  let output = "";
  output += "// 자동 생성된 파일입니다. 직접 수정하지 마세요.\n";
  output += "// 생성: scripts/generate-dict-types.ts\n";
  output += "//\n";
  output += "// 사전 키 추가/수정은 dictionaries/{ko,en}/*.json 에서 하세요.\n"; // 이 파일을 직접 고치려는 사람에게 올바른 위치를 알려준다.
  output += "// 키 추가: npm run dict:add -- <파일>.<Key> \"한국어\" \"English\"\n";
  output += "// 이후 'npm run gen:dict' 또는 'npm run dev' 실행 시 이 파일이 자동으로 갱신됩니다.\n\n"; // 생성 시각은 넣지 않는다. 매번 바뀌면 의미 없는 git 변경이 생긴다.
  output += body;
  output += `/** 사전 파일명 -> 타입 매핑. getDictionary가 파일명으로 정확한 타입을 찾을 때 쓴다. */\n`;
  output += `export interface DictMap {\n`;
  output += entries.map(({ name, iface }) => `  "${name}": ${iface};\n`).join("");
  output += `}\n\n`;
  output += `/** 사용 가능한 사전 이름. 오타를 내면 컴파일 에러가 난다. */\n`;
  output += `export type DictNamespace = keyof DictMap;\n\n`;
  output += `/** 모든 사전 키를 합친 통합 타입. 기존 코드 호환용으로 유지한다. (신규 코드는 LangDictType<"페이지명"> 권장) */\n`;
  output += `export type LangDict = ${entries.map((e) => e.iface).join(" & ")};\n`; // 이미 LangDict를 import하는 파일이 있어도 깨지지 않게 남겨둔다.

  const prev = fs.existsSync(OUT_FILE) ? fs.readFileSync(OUT_FILE, "utf8") : "";
  if (prev !== output) fs.writeFileSync(OUT_FILE, output, "utf8"); // 내용이 같으면 쓰지 않아야 TS 서버/HMR이 불필요하게 다시 돌지 않는다.

  console.log("");
  header("결과 요약");
  info("인터페이스", `${c.green}${entries.map((e) => e.iface).join(", ")}${c.reset}`);
  info("통합 타입", `${c.green}DictMap, DictNamespace, LangDict${c.reset}`);
  info("총 key 수", `${c.yellow}${totalKeys}개${c.reset}`);
  info("파일 크기", `${c.dim}${formatBytes(Buffer.byteLength(output))}${c.reset}`);
  return { changed: prev !== output, missing };
}

/** 1회 실행 - 성공 여부를 반환해서 1회 모드는 종료 코드로, 감시 모드는 계속 실행으로 처리한다. */
function runOnce() {
  console.log("");
  header("dict 사전 type 자동 생성");
  try {
    const { changed, missing } = generate();
    if (missing.length > 0) {
      missing.forEach((m) => error(`번역 누락 - ${m}`)); // 누락 하나하나를 한 줄씩 보여줘야 바로 찾아가 고칠 수 있다.
      console.log(`${c.gray}  (미리보기 타입은 갱신됨, 번역을 채우기 전까지 빌드는 실패합니다)${c.reset}`);
      return false;
    }
    success(changed ? "타입 갱신 완료" : "변경 없음");
    return true;
  } catch (err) {
    if (!(err instanceof DictError)) throw err; // 예상 못 한 버그는 숨기지 않고 그대로 터뜨린다.
    error(err.message);
    return false;
  }
}

/** 감시 모드 - 개발 서버와 함께 켜두면 JSON 저장만으로 타입/미리보기가 갱신된다. */
function watch() {
  runOnce(); // 감시 시작 전에 바뀐 내용도 맞춰둔다.
  let timer: NodeJS.Timeout | undefined;

  fs.watch(DICT_DIR, { recursive: true }, (_event, filename) => {
    if (filename === null || !filename.endsWith(".json")) return; // 에디터 임시 파일 등은 무시한다.
    clearTimeout(timer);
    timer = setTimeout(runOnce, 150); // 에디터가 저장 이벤트를 여러 번 보내므로 잠깐 모았다가 한 번만 실행한다.
  });
  console.log(`${c.blue}👀 ${DICT_DIR} 감시 중...${c.reset}`);
}

// 실행 - 감시 모드는 실패해도 살아 있어야 하고, 1회 모드는 실패 시 종료 코드 1로 빌드/CI를 멈춘다.
if (process.argv.includes("--watch")) watch();
else if (!runOnce()) process.exitCode = 1;
