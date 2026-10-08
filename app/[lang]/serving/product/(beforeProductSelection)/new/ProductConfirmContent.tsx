import { LangDictType } from "@/i18n/dictionaries";
import { ProductObj } from "@/types/serving/product";
import { SegmentObj } from "@/types/serving/segment";

/**
 * @file app/{lang}/serving/product/(beforeProductSelection)/new/ProductConfirmContent.tsx
 * @description 상품 등록 확인 모달의 본문 콘텐츠
 * 
 * 상태:
 * - newProductId > 0: 등록 완료 화면 (체크 아이콘 + 상세 페이지 링크)
 * - newProductId === 0: 등록 정보 요약 (상품 + 세그먼트 목록)
 */
type ProductConfirmContentProps = {
  newProductId: number;
  newProduct: ProductObj;
  newSegments: SegmentObj[];
  dict: LangDictType;
};

const ProductConfirmContent = ({
  newProductId,
  newProduct,
  newSegments,
  dict,
}: ProductConfirmContentProps) => {
  // = 등록 완료 화면 =
  if (newProductId > 0) {
    return (
      <div className="flex flex-col items-center justify-center py-4 gap-3">
        <p className="text-[15px] font-semibold text-[#191f28] text-center">
          {dict.CompleteAddProduct}
        </p>
        <p className="text-[13px] text-[#8b95a1] text-center">
          {dict.ProductInfoMove}
        </p>
      </div>
    );
  }

  // = 등록 정보 요약 화면 =
  return (
    <>
      {/* 상품 정보 요약 */}
      <div className="space-y-2 mb-5">
        {[
          [`${dict.Product} ${dict.Name}`, newProduct.ProductName],
          [dict.SegmentationColumn, newProduct.SegmentColumn],
          [dict.ExclusionColumn, newProduct.ExclusionColumn],
          [dict.Segment, `${Array.isArray(newSegments) ? newSegments.length : 0}개`],
        ].map(([label, val], i) => (
          <div key={i} className="flex text-sm">
            <span className="w-[120px] font-semibold text-[#4e5968] shrink-0">{label}</span>
            <span className="text-[#191f28]">{val}</span>
          </div>
        ))}
      </div>

      {/* 세그먼트별 요약 */}
      {Array.isArray(newSegments) && newSegments.map((seg) => (
        <div key={seg.Id} className="bg-[#f9fafb] border border-[#e5e8eb] rounded-xl p-4 mb-2.5">
          <div className="w-[120px] font-semibold text-[#191f28] mb-2">{seg.SegmentName}</div>
          <div className="space-y-1 text-[13px]">
            <div className="flex">
              <span className="w-[100px] text-[#8b95a1] shrink-0">{dict.SegmentationColumn}</span>
              <span className="text-[#4e5968]">{seg.SegmentValue}</span>
            </div>
            <div className="flex">
              <span className="w-[100px] text-[#8b95a1] shrink-0">{dict.ExclusionColumn}</span>
              <span className="text-[#4e5968]">{seg.ExclusionValue}</span>
            </div>
            <div className="flex">
              <span className="w-[100px] text-[#8b95a1] shrink-0">{dict.Model}</span>
              <span className="text-[#4e5968]">{seg.Models.length}개</span>
            </div>
            {seg.Models.map((m) => (
              <div key={m.ModelId} className="text-[12px] text-[#8b95a1] pl-[100px]">
                {m.ModelName ?? ""} [{m.ModelType ?? ""}] {m.ModelFile?.name ?? ""}
              </div>
            ))}
          </div>
        </div>
      ))}
    </>
  );
};

export default ProductConfirmContent;
