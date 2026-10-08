import { getDictionary, LangType } from "@/i18n/dictionaries";
import ProductCreator from "./ProductCreator";

export default async function Page({
  params,
}: {
  params: Promise<{ lang: LangType }>;
}): Promise<Element> {
  const { lang } = await params;
  const dict :LangDictType = await getDictionary(lang, "serving");

  return (
    <div className="subpage-container productCreator-page" style={{ padding: "0px" }}>
      <ProductCreator
        dict={dict}
        baseUrl={`/serving/product`}
        lang={lang} //[20250825] - ProductCreator로 lang 전달 추가
      />
    </div>
  );
}
