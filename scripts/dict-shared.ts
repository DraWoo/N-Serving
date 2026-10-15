/**
 * @file scripts/dict-shared.ts
 * @description 다국어 스크립트 공통 규칙 (generate-dict-types.ts, add-dict-key.ts 가 함께 사용)
 *
 * 두 스크립트가 같은 규칙을 각자 들고 있으면 한쪽만 고쳐져서 결과가 어긋난다.
 * 그래서 경로, 이름 규칙, JSON 읽기/검증을 이 파일 한 곳에서만 관리한다.
 */
import { spawnSync } from "node:child_process";
import * as fs from "node:fs";
import * as path from "node:path";

/** 사전 루트 폴더 - 언어 폴더(ko, en)의 상위 폴더를 기준으로 잡아야 모든 언어를 읽을 수 있다. */
export const DICT_DIR = path.resolve("i18n/dictionaries");
/** 기준 언어 - 키 목록의 "정답"은 하나여야 하므로 ko 하나만 기준으로 삼는다. */
export const BASE_LOCALE = "ko";
/** 비교 대상 언어 - 기준 언어의 키가 빠짐없이 있는지 검사할 언어들. */
export const OTHER_LOCALES = ["en"] as const;
/** 전체 언어 목록 - 입력 검증/저장처럼 "모든 언어에 똑같이" 해야 하는 작업에 쓴다. */
export const LOCALES = [BASE_LOCALE, ...OTHER_LOCALES];
/** 키 형식 - dict.Key 처럼 점(.)으로 접근하려면 JS 변수 이름 규칙을 지켜야 한다. */
export const KEY_PATTERN = /^[A-Za-z_$][\w$]*$/;
/** 파일명 형식(kebab-case) - 파일명이 그대로 타입 이름과 import 경로가 되므로 한 가지 규칙만 허용한다. */
export const FILE_PATTERN = /^[a-z][a-z0-9]*(-[a-z0-9]+)*$/;

/** 사전 규칙 위반 에러 - 예상된 실패만 골라서 깔끔하게 출력하려고 일반 Error와 구분한다. */
export class DictError extends Error {}

/** 사전 타입 - 모든 값이 문자열인 객체. */
export type Dict = Record<string, string>;

/** 타입 가드 - JSON.parse 결과는 unknown이므로, 캐스팅 대신 실제로 검사해서 Dict로 좁힌다. */
export function isDict(value: unknown): value is Dict {
  if (typeof value !== "object" || value === null || Array.isArray(value)) return false; // 배열/null도 typeof가 object라 따로 걸러야 한다.
  return Object.values(value).every((v) => typeof v === "string"); // 값이 문자열이어야 화면에 그대로 출력할 수 있다.
}

/** 키 존재 검사 - `in`은 constructor, toString 같은 상속 속성까지 true라서 실제 내 속성만 검사한다. */
export function hasKey(dict: Dict, key: string) {
  return Object.hasOwn(dict, key);
}

/**
 * 키 저장 - dict[key] = text 는 key가 "__proto__"일 때 값이 저장되지 않고 사라진다.
 * defineProperty는 "이 객체 자신의 속성"으로 명시해서 만들기 때문에 어떤 키든 안전하다.
 */
export function setEntry(dict: Dict, key: string, text: string) {
  Object.defineProperty(dict, key, { value: text, enumerable: true, writable: true, configurable: true }); // enumerable이어야 JSON.stringify/Object.keys에 포함된다.
}

/** 키 이름 검사 - 문제가 있으면 메시지, 없으면 null. generate/add/csv 세 곳이 같은 기준을 쓰도록 한 곳에 둔다. */
export function keyError(key: string) {
  if (!KEY_PATTERN.test(key)) return `키 "${key}" 는 영문으로 시작하고 영문/숫자/_ 만 사용할 수 있습니다.`;
  if (key === "__proto__") return `키 "__proto__" 는 JS 예약 속성이라 사용할 수 없습니다.`; // 저장은 되더라도 화면 코드에서 dict.__proto__ 는 혼란을 준다.
  return null;
}

/** 파일명 검사 - 파일명이 그대로 타입 이름이 되므로 같은 규칙을 강제한다. */
export function fileError(file: string) {
  return FILE_PATTERN.test(file) ? null : `파일명 "${file}" 은 소문자 kebab-case(예: model-detail)여야 합니다.`;
}

/** 빈 문구 판단 - 공백만 있는 문구도 화면에선 빈 칸이라 "없음"으로 본다. (저장할 때는 원문 그대로 저장한다) */
export function isBlank(text: string | undefined) {
  return text === undefined || text.trim() === "";
}

/**
 * 한 건 입력 검증 - dict:add 와 CSV import 가 똑같은 정책을 쓰도록 공통화했다.
 * 정책
 *  - 기준 언어(ko) 문구는 필수: 키는 ko에 있어야 존재하는 키다.
 *  - 다른 언어(en) 빈 값은 허용하되 "건드리지 않음"으로 처리한다.
 *    가짜 번역을 채우지 않으므로 gen:dict 의 번역 누락 검사에 그대로 걸려서 숨겨지지 않는다.
 */
export function validateEntry(file: string, key: string, texts: Partial<Record<string, string>>) {
  const errors = [fileError(file), keyError(key)].filter((e) => e !== null);
  if (isBlank(texts[BASE_LOCALE])) errors.push(`${BASE_LOCALE} 문구가 비어 있습니다. (${file}.${key})`);
  return errors;
}

/**
 * 타입 재생성 실행 - 번역 누락이 있으면 gen:dict 가 종료 코드 1로 끝난다.
 * execSync 는 그때 예외를 던져 긴 스택이 찍히므로, spawnSync 로 결과 코드만 받아서 그대로 전달한다.
 */
export function runGenDict() {
  const result = spawnSync("npm", ["run", "gen:dict"], { stdio: "inherit", shell: true }); // shell: 윈도우에서 npm(npm.cmd)을 찾으려면 필요하다.
  return result.status ?? 1; // 신호로 강제 종료되면 status가 null이라 실패(1)로 본다.
}

/** 파일명 -> 타입 이름 (model-detail -> ModelDetail) - 타입 이름은 PascalCase가 관례다. */
export function toPascalCase(name: string) {
  return name
    .split("-") // FILE_PATTERN이 하이픈만 허용하므로 하이픈 기준으로만 나눈다.
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1)) // 단어 첫 글자만 대문자로 바꾼다.
    .join("");
}

/** 사전 파일 저장 - 2칸 들여쓰기 + 마지막 줄바꿈은 Prettier 기본값과 같아서 불필요한 포맷 diff가 안 생긴다. */
export function writeDictFile(filePath: string, data: Dict) {
  fs.mkdirSync(path.dirname(filePath), { recursive: true }); // 언어 폴더가 없어도 실패하지 않게 만든다.
  fs.writeFileSync(filePath, `${JSON.stringify(data, null, 2)}\n`, "utf-8");
}

/**
 * 사전 파일 읽기
 * - 파일 없음  : null (누락 여부는 호출하는 쪽이 판단)
 * - 빈 파일    : 에러 (저장 중 끊긴 파일일 수 있어서, 조용히 {}로 보면 키가 전부 사라진다)
 * - 문법/형태 오류 : 에러
 */
export function readDictFile(filePath: string) {
  if (!fs.existsSync(filePath)) return null;

  const label = path.relative(DICT_DIR, filePath); // 에러 메시지에 "ko/common.json"처럼 짧게 보여주려고 쓴다.
  const raw = fs.readFileSync(filePath, "utf-8");
  if (raw.trim() === "") throw new DictError(`${label} 파일이 비어 있습니다. 키가 없으면 {} 를 넣어주세요.`);

  let parsed: unknown; // 어떤 모양인지 모르므로 unknown으로 받고 아래 isDict로 좁힌다.
  try {
    parsed = JSON.parse(raw);
  } catch (err) {
    const detail = err instanceof Error ? err.message : String(err); // 원래 메시지에 "position 23" 같은 위치 정보가 있어 오류 지점을 바로 찾을 수 있다.
    throw new DictError(`JSON 문법 오류: ${label}\n  ${detail}`);
  }

  if (!isDict(parsed)) throw new DictError(`${label} 은 { "Key": "문자열" } 형태여야 합니다.`);
  return parsed;
}
