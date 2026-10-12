/**
 * @file scripts/generate-dict-types.ts
 * @description dictionaries/ko/*.json -> 컴포넌트 내 TypeScript 타입 자동완성 기능
 */
import * as path from "node:path";
import * as fs from "node:fs";

/** 경로 설정 */
const KO_DIR = path.resolve("i18n/dictionaries/ko");
/** 자동 생성 파일 위치 */
const OUT_FILE = path.resolve("i18n/dict.generate.d.ts");

/** ANSI 색상 코드 */
const c = {
  reset: "\x1b[0m",      // 모든 스타일 초기화
  bold: "\x1b[1m",       // 굵게
  dim: "\x1b[2m",        // 흐릿하게

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
/** 구분선 출력 */
function divider() {
  console.log(`${c.gray}================================================================${c.reset}`);
}

/** 헤더 박스 출력 (start 시) */
function header(title) {
  divider();
  console.log(`${c.bold}${c.cyan} ${title}${c.reset}`);
  divider();
}

/** 정보 출력 (cyan 라벨+ 값) */
function info(label, value) {
  const paddedLabel = label.padEnd(12, " ");
  console.log(`${c.cyan}${paddedLabel}${c.reset} ${value}`);
}

/** 성공 메시지 출력 */
function success(message) {
  console.log("");
  console.log(`${c.bgGreen}${c.bold} ✔ SUCCESS ${c.reset} ${c.green}${message}${c.reset}`);
}

/** 경고 메시지 출력 (start 시) */
function warn(message) {
  console.log(`${c.yellow}${c.bold}⚠ ${message}${c.reset}`);
}

/** 에러 메시지 출력 (start 시) */
function error(message) {
  console.error("");
  console.error(`${c.bgRed}${c.bold}✖ ERROR ${c.reset}${c.red}${message}${c.reset}`);
}

//===================
// 헬퍼함수
//===================
function toNamespace(name) {
  return name
    .split(/[-_]/)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join("");
}

/** JSDoc escape */
function escapeForJSDoc(value) {
  return value.replace(/\*\//g, "*\\/").replace(/\n/g, " ");
}

//===================
// 메인 실행 함수
//===================
function generate() {
  console.log("");
  header("dict 사전 type 자동 생성");

  if (!fs.existsSync(KO_DIR)) {
    error(`ko 다국어 폴더가 없습니다/: ${KO_DIR}`);
    process.exit(1);
  }

  const files = fs.readdirSync(KO_DIR).filter((f) => f.endsWith(".json"));
  if (files.length === 0) {
    error("ko/*.json 파일이 없습니다.");
    process.exit(1);
  }

  /** 출력 헤더 생성 */
  info("입력 폴더", `${c.dim}${KO_DIR}${c.reset}`);
  info("출력 파일", `${c.dim}${OUT_FILE}${c.reset}`);
  info("처리 파일", `${c.yellow}${files.length}개${c.reset}`);
  console.log("");

  let output = "";
  output += "// 자동 생성된 파일입니다. 직접 수정하지 마세요.\n";
  output += "// 생성: scripts/generate-message-type.ts\n";
  output += `// 생성 시각: ${new Date().toISOString()}\n`;
  output += "//\n";
  output += "// 사전 키 추가/수정은 dictionaries/ko/*.json 에서 하세요.\n";
  output += "// 이후 'npm run gen:dict' 또는 'npm run dev' 실행 시\n";
  output += "// 이 파일이 자동으로 갱신됩니다.\n\n";

  /** 각 도메인 JSON -> 인터페이스 변환 */
  const interfaceNames = [];
  const stats = [];

  for (const file of files) {
    const name = path.basename(file, ".json");
    const filePath = path.join(KO_DIR, file);

    let content;
    try {
      content = JSON.parse(fs.readFileSync(filePath, "utf-8"));
    } catch (err) {
      error(`JSON 파싱 실패: ${file}`);
      console.log(err);
      process.exit(1);
    }

    const iface = `${toNamespace(name)}Dict`;
    const keyCount = Object.keys(content).length;
    if (keyCount === 0) {
      warn(`${file}이 비어있습니다. (key 0개)`);
    }

    interfaceNames.push(iface);
    stats.push({ file, iface, keyCount });

    // 진행 상황 출력
    console.log(
      ` ${c.green}✔${c.reset} ${c.bold}${file.padEnd(20)}${c.reset} ` +
        `-> ${c.cyan}${iface}${c.reset} ` +
        `${c.gray}(${keyCount}개 키)${c.reset}`
    );

    output += `/** ${name}.json 사전 타입 */\n`;
    output += `export interface ${iface} {\n`;

    for (const [key, value] of Object.entries(content)) {
      output += `  /** ${escapeForJSDoc(value)} */\n`;
      output += `  ${key}: string;\n`;
    }

    output += `}\n\n`;
  }

  // - 통합 LangDict 타입 생성
  output += `/**\n`;
  output += ` * 모든 다국어 키를 합친 통합 타입.\n`;
  output += ` * dictionaries.ts의 LangDictType이 이 타입을 사용함.\n`;
  output += ` * 새 도메인 추가 시 자동으로 합쳐짐 (스크립트 재실행 필요).\n`;
  output += ` */\n`;
  output += `export type LangDict = ${interfaceNames.join(" & ")};\n`;

  fs.writeFileSync(OUT_FILE, output, "utf8");

  // 완료
  console.log("");
  divider();
  console.log(`${c.bold}${c.cyan}결과 요약:${c.reset}`);
  divider();

  const totalKeys = stats.reduce((sum, s) => sum + s.keyCount, 0);

  info("인터페이스", `${c.green}${interfaceNames.join(", ")}${c.reset}`);
  info("통합 타입", `${c.green}LangDict${c.reset}`);
  info("총 key 수", `${c.yellow}  ${totalKeys}개${c.reset}`);
  info("파일 크기", `${c.dim} ${formatBytes(output.length)}${c.reset}`);

  success("다국어 사전 type 생성 완료!!");
  console.log("");
}

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 * 1024).toFixed(1)} MB`;
}

//실행
generate();
