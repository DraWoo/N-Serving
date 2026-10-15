/**
 * @file scripts/add-dict-key.ts
 * @description 키 하나를 ko/en JSON에 동시에 추가하고, 타입(미리보기)까지 재생성한다.
 *
 * 사용법
 *  npm run dict:add -- common.Status "상태" "Status"
 *  npm run dict:add -- model-detail.Title "모델 상세" "Model Detail"  (파일이 없으면 ko/en 모두 새로 만든다)
 *  npm run dict:add -- common.Status "상태값" "Status" --force        (이미 있는 키 덮어쓰기)
 *  npm run dict:add -- common.Status "상태"                          (영어 생략 가능 -> ko만 저장, gen:dict 가 번역 누락으로 알려줌)
 */
import * as path from "node:path";
import { BASE_LOCALE, DICT_DIR, DictError, LOCALES, hasKey, isBlank, readDictFile, runGenDict, setEntry, validateEntry, writeDictFile } from "./dict-shared";

/** 사용법 안내 후 종료 - 잘못 입력했을 때 무엇을 고쳐야 할지 바로 보여준다. */
function exitWithUsage(message: string): never {
  console.error(`✖ ${message}`);
  console.error('  사용법: npm run dict:add -- <파일>.<Key> "한국어" "English" [--force]');
  process.exit(1);
}

/** 입력 파싱 - CLI 인자는 모두 문자열이므로 여기서 한 번에 검증해 아래 로직을 단순하게 유지한다. */
function parseArgs(argv: string[]) {
  const force = argv.includes("--force"); // 덮어쓰기는 실수 위험이 있으므로 명시했을 때만 허용한다.
  const [target, ko, en] = argv.filter((arg) => arg !== "--force"); // 언어별 문구는 순서대로 받는다: 한국어, 영어

  if (target === undefined) exitWithUsage("파일.키 는 필수입니다.");

  const [file, key, ...rest] = target.split(".");
  if (key === undefined || rest.length > 0) exitWithUsage(`"${target}" 는 <파일>.<Key> 형태여야 합니다.`);

  const texts: Partial<Record<string, string>> = { [BASE_LOCALE]: ko, en }; // 영어를 키 이름 등으로 대신 채우지 않는다. 가짜 번역이 들어가면 누락 검사에 안 걸린다.
  const errors = validateEntry(file, key, texts); // CSV import와 같은 검증 함수를 써야 입력 방법에 따라 정책이 달라지지 않는다.
  if (errors.length > 0) exitWithUsage(errors.join("\n  "));

  return { file, key, force, texts };
}

/** 저장 계획 - 모든 언어를 먼저 읽고 검사한다. ko만 써지고 en에서 실패하면 언어 간 키가 어긋나기 때문이다. */
function planWrites({ file, key, force, texts }: ReturnType<typeof parseArgs>) {
  const targets = LOCALES.filter((locale) => !isBlank(texts[locale])); // 문구를 준 언어만 저장한다. (영어 생략 시 en 파일은 건드리지 않음)
  return targets.map((locale) => {
    const text = texts[locale] ?? ""; // 위 filter로 빈 값은 걸렀으므로 실제로 ""가 될 일은 없다. 타입상 기본값만 둔다.
    const filePath = path.join(DICT_DIR, locale, `${file}.json`);
    const dict = readDictFile(filePath); // 문법 오류/빈 파일/문자열 아닌 값은 여기서 에러가 나서 저장 전에 멈춘다.
    if (dict !== null && hasKey(dict, key) && !force) {
      throw new DictError(`${locale}/${file}.json 에 "${key}" 가 이미 있습니다. (덮어쓰려면 --force)`);
    }
    return { locale, text, filePath, dict: dict ?? {}, isNewFile: dict === null };
  });
}

//===================
// 실행
//===================
const args = parseArgs(process.argv.slice(2));

let plans: ReturnType<typeof planWrites>;
try {
  plans = planWrites(args);
} catch (err) {
  if (!(err instanceof DictError)) throw err; // 예상 못 한 버그는 숨기지 않는다.
  exitWithUsage(err.message);
}

// 검사를 모두 통과했을 때만 한꺼번에 저장한다.
for (const { locale, text, filePath, dict, isNewFile } of plans) {
  setEntry(dict, args.key, text); // __proto__ 같은 특수 키도 실제 속성으로 저장되게 공통 함수를 쓴다. (기존 키는 순서 유지, 새 키는 맨 뒤)
  writeDictFile(filePath, dict);
  console.log(`✔ ${locale}/${args.file}.json ${isNewFile ? "(새 파일) " : ""}+ ${args.key}: "${text}"`);
}

if (plans.length < LOCALES.length) console.log("⚠ 일부 언어 문구를 생략했습니다. 아래 gen:dict 에서 번역 누락으로 표시됩니다.");
process.exitCode = runGenDict(); // 같은 생성 로직을 재사용해야 "추가"와 "생성" 결과가 항상 일치한다. 번역 누락이면 종료 코드 1을 그대로 전달한다.
