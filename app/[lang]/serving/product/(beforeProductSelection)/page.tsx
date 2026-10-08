import { getDictionary, LangType } from "@/i18n/dictionaries";
import AsyncBoundary from "@/components/skeletonUI/AsyncBoundary";
import { ProductInfoType } from "@/types/serving/product";
import ServerDataLoader from "@/components/skeletonUI/ServerDataLoder";
import ProductList from "./ProductList";

export default async function Page({
  params,
}: {
  params: Promise<{ lang: LangType }>;
}): Promise<Element> {

  const { lang } = await params;
  const dict :LangDictType = await getDictionary(lang, "serving");
  return (
    <div className="max-w-[1400px] mx-auto">
      <AsyncBoundary skeletonRows={16}>
        <ServerDataLoader<ProductInfoType[]>
          endpoint="serving/product-list"
          options={{
            cacheOpt:
              {
                revalidate: 600,
                tags: ["product-list"],
              }
          }}
          fallbackData={[]}
        >
          {(products) => (
            <ProductList
              productGridData={products}
              dict={dict}
              baseUrl={`/${lang}/serving/product`}
            />
          )}
        </ServerDataLoader>
      </AsyncBoundary>
    </div>
  );
}
