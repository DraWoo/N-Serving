/**
 * @file useBreadcrumb.ts
 * @description 페이지 진입 시 Breadcrumb 갱신 로직 사용
 * - Product > [메뉴명] 패턴
 * 
 * [사용법]
 * useBreadcrumb({
 *   menuId: "menu_feature",
 *   menuText: "Feature",
 *   menuPath: "/feature",
 * });
 */
import { useBreadcrumb, type NavItem } from "@/components/navigation/BreadcrumbContext";
import { useEffect } from "react";

type UseBreadcrumbSyncParams = {
  menuId: string;    // 메뉴 ID
  menuText: string;  // 렌더링 텍스트
  menuPath: string;  // 경로 suffix
};

/**
 * Breadcrumb[Product, 메뉴명] 형태로 동기화
 * 
 * 동작:
 * - 진입 시 현재 navItemList 점검
 * - 형태가 다르면 [Product, 메뉴명]으로 갱신
 * - 이미 올바른 상태면 갱신 생략
 */
export function useBreadcrumbSync({
  menuId,
  menuText,
  menuPath,
}: UseBreadcrumbSyncParams): void {
  const { navItemList, changeBreadcrumb } = useBreadcrumb();

  useEffect(() => {
    // 초기화 전이면 종료
    if (navItemList.length === 0) return;

    /**
     * 업데이트 필요 조건:
     * - 단계 3개 이상 (이전 페이지 전체)
     * - 두 번째 단계가 menuId 아님 (다른 메뉴에서 진입)
     * - 단계 1개 (Product만 있음)
     */
    const needUpdate =
      navItemList.length > 2 ||
      (navItemList.length === 2 && navItemList[1].id !== menuId) ||
      navItemList.length === 1;

    if (!needUpdate) return;

    const nextNavList: NavItem[] = [
      navItemList[0],
      {
        id: menuId,
        text: menuText,
        link: navItemList[0].link + menuPath,
      },
    ];

    changeBreadcrumb(nextNavList);
  }, [changeBreadcrumb, menuId, menuPath, menuText, navItemList]);
}
