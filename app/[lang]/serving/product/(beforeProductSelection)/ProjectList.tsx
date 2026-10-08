/**
 * @file ProductList.tsx
 * @description 상품목록
 * 
 * [20260331] - 컬럼 정렬 시 컬럼 너비 흔들림 수정
 */
"use client";

import { ProductInfoType } from "@/types/serving/product";
import { LangDictType } from "@/i18n/dictionaries";
import { useRouter } from "next/navigation";
import { useMemo, useState } from "react";
import Link from "next/link";
import { useCacheFetch } from "@/hooks/useCacheFetch";
import { formatDate } from "@/lib/utils/formatDate";
import Pagination from "@/components/common/Pagination";
import SvgIcon from "@/components/icons/SvgIcon";
import { BTN_ACTIVE } from "@/lib/constants";
import { PAGE_SIZE } from "@/lib/constants";

/** 컬럼 정의 */
interface Column {
  field: string;
  caption: string;
  width: string;
  align?: "left" | "center" | "right";
  isLink?: boolean;
  format?: (value: unknown) => string;
}

interface ProductListProps {
  productGridData: ProductInfoType[];
  dict: LangDictType;
  baseUrl: string;
}

export default function ProductList({
  productGridData,
  dict,
  baseUrl,
}: ProductListProps): Element {
  const router = useRouter();
  const [page, setPage] = useState(0);
  const [sortField, setSortField] = useState<string | null>(null);
  const [sortAsc, setSortAsc] = useState(true);

  // [Zustand] 캐시
  const { data } = useCacheFetch<ProductInfoType[]>({
    endpoint: "serving/product-list",
    ttl: 5 * 60_000,
    initialData: productGridData,
  });

  const displayData: ProductInfoType[] = useMemo(
    () => data ?? productGridData ?? [],
    [data, productGridData],
  );

  // [컬럼 정의]
  const columns: Column[] = [
    { field: "PRODUCT_NAME", caption: `${dict.Product} ${dict.Name}`, align: "left", isLink: true, width: "w-[16%]" },
    { field: "PRODUCT_SHORT_DESC", caption: `${dict.Product} ${dict.Description}`, align: "left", width: "w-[20%]" },
    { field: "SEGMENT_COUNT", caption: `${dict.Segment} ${dict.Count}`, align: "center", width: "w-[10%]" },
    { field: "OWNER_ID", caption: dict.Owner, align: "center", width: "w-[10%]" },
    { field: "ENROLLED_DATETIME", caption: dict.CreatedDt, align: "center", width: "w-[22%]", format: (v: unknown) => (v ? formatDate(String(v), "long") : "") },
    { field: "LAST_MODIFIED_DATETIME", caption: dict.LastModifiedDt, align: "center", width: "w-[22%]", format: (v: unknown) => (v ? formatDate(String(v), "long") : "") },
  ];

  // [sorting]
  const sorted: ProductInfoType[] = useMemo(() => {
    if (!sortField) return displayData;
    return [...displayData].sort((a: ProductInfoType, b: ProductInfoType) => {
      const aVal = a[sortField as keyof ProductInfoType];
      const bVal = b[sortField as keyof ProductInfoType];
      if (aVal == null) return 1;
      if (bVal == null) return 1;
      if (aVal < bVal) return sortAsc ? -1 : 1;
      if (aVal > bVal) return sortAsc ? 1 : -1;
      return 0;
    });
  }, [displayData, sortAsc, sortField]);

  // [paging]
  const paged: ProductInfoType[] = sorted.slice(page * PAGE_SIZE, (page + 1) * PAGE_SIZE);

  const handleSort = (field: string) => {
    if (sortField === field) {
      setSortAsc(!sortAsc);
    } else {
      setSortField(field);
      setSortAsc(true);
    }
    setPage(0);
  };

  // [텍스트 정렬 클래스]
  const alignClass = (align?: string) => {
    if (align === "right") return "text-right";
    if (align === "center") return "text-center";
    return "text-left";
  };

  return (
    <div>
      {/* 타이틀 + 버튼 */}
      <div className="flex items-center justify-between mb-3">
        <h3 className="text-[17px] font-bold text-[#191f28]">{dict.Product} {dict.List}</h3>
        <Link
          href={`${baseUrl}/new`}
          className={`flex items-center gap-1.5 px-4 py-2 rounded-[4px] border border-[#3182f6] text-[#3182f6] text-[14px] font-semibold bg-white hover:bg-[#f0f6ff] no-underline ${BTN_ACTIVE}`}
        >
          <SvgIcon name="plus" size={16} />
          {dict.CreateNewProduct}
        </Link>
      </div>

      {/* 테이블 + 페이징 */}
      <div className="bg-table rounded-[8px] border border-[#e5e8eb]">
        <table className="w-full table-fixed min-w-[900px]">
          {/* 헤더 */}
          <thead className="bg-[#f7f8fa]">
            <tr className="bg-[#f7f8fa] border-b border-[#e5e8eb]">
              {columns.map((col: Column) => (
                <th
                  key={col.field}
                  onClick={() => handleSort(col.field)}
                  className={`px-4 py-3 text-[12px] font-semibold text-[#4e5968] cursor-pointer select-none hover:bg-[#eef1f4] transition-colors ${alignClass(col.field)} ${col.width}`}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.caption}
                    {/* 정렬 아이콘: 해당 컬럼만 표시 */}
                    <span className="w-3 text-[10px] text-[#8b95a1]">
                      {sortField === col.field ? (sortAsc ? "▲" : "▼") : ""}
                    </span>
                  </span>
                </th>
              ))}
            </tr>
          </thead>
          {/* body 영역 */}
          <tbody>
            {paged.length === 0 && (
              <tr>
                <td
                  colSpan={columns.length}
                  className="py-12 text-center text-[13px] text-[#b0b8c1]"
                >
                  등록된 상품이 없습니다.
                </td>
              </tr>
            )}
            {paged.map((row: ProductInfoType) => (
              <tr
                key={row.PRODUCT_ID}
                onClick={() => router.push(`${baseUrl}/${row.PRODUCT_ID}`)}
                className="border-b border-[#f2f4f6] cursor-pointer hover:bg-[#f9fafb] transition-colors"
              >
                {columns.map((col: Column) => {
                  const rawValue = row[col.field as keyof ProductInfoType];
                  return (
                    <td
                      key={col.field}
                      className={`px-4 py-3 text-[13px] text-[#191f28] truncate ${alignClass(col.field)} ${col.width}`}
                    >
                      {col.isLink ? (
                        <Link
                          href={`${baseUrl}/${row.PRODUCT_ID}`}
                          onClick={(e: React.MouseEvent<HTMLAnchorElement>) => e.stopPropagation()}
                          className="text-[#3182f6] font-medium hover:underline underline-offset-2 no-underline"
                        >
                          {String(rawValue ?? "")}
                        </Link>
                      ) : col.format ? (
                        col.format(rawValue)
                      ) : (
                        String(rawValue ?? "")
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
        <div className="px-4 py-3 border-t border-[#f2f4f6] flex justify-end">
          <Pagination
            totalItems={sorted.length}
            pageSize={PAGE_SIZE}
            currentPage={page}
            onPageChangeAction={setPage}
          />
        </div>
      </div>
    </div>
  );
}
