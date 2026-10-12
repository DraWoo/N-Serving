/**
 * @file i18n/dictionaries.ts
 * @description 다국어 사전 loader
 *
 */
import "server-only";
import { CommonDict, ServingDict } from "@/i18n/dict.generate";

// 지원 언어
export type LangType = "ko" | "en";

// dict 객체 타입
export interface LangDictType extends CommonDict, ServingDict {}

export const getDictionary = async (locale: LangType, page: string): Promise<LangDictType> => {
  const [common, pageDict] = await Promise.all([
    import(`./dictionaries/${locale}/common.json`),
    import(`./dictionaries/${locale}/${page}.json`).catch(() => ({ default: {} })),
  ]);

  return { ...common.default, ...pageDict.default } as LangDictType;
};
