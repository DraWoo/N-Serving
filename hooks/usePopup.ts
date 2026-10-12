/**
 * @file hooks/usePopup.ts
 * @description CommonPopup 상태 관리 훅
 * 
 * 사용 예시:
 *   const { popupProps, openPopup, closePopup } = usePopup();
 * 
 *   const handleDelete = () => {
 *     openPopup({
 *       type: "danger",
 *       title: "정말 삭제하시겠습니까?",
 *       message: "이 작업은 되돌릴 수 없습니다.",
 *       confirmText: "삭제",
 *       onConfirm: async () => {
 *         await deleteItem();
 *         closePopup();
 *       },
 *     });
 *   };
 *   return <CommonPopup {...popupProps} />;
 */
"use client";

import { CommonPopupProps, PopupType } from "@/components/common/CommonPopup";
import { useCallback, useState } from "react";

/** [openPopup에 전달하는 설정 (open, onClose는 훅이 자동관리)] */
type PopupConfig = {
  title: string;
  message?: string;
  type?: PopupType;
  confirmText?: string;
  cancelText?: string;
  showCancel?: boolean;
  onConfirm?: () => void | Promise<void>;
  onCancel?: () => void;
  width?: number;
  loading?: boolean;
  closeOnBackdrop?: boolean;
  closeOnEsc?: boolean;
  showCloseButton?: boolean;
};

type UsePopupReturn = {
  /** [CommonPopup에 spread할 props] */
  popupProps: CommonPopupProps;
  /** [팝업 열기] */
  openPopup: (config: PopupConfig) => void;
  /** [팝업 닫기] */
  closePopup: () => void;
  /** [팝업 열림 여부] */
  isOpen: boolean;
  /** [로딩 상태 변경 (API 호출 중 스피너 표시)] */
  setLoading: (loading: boolean) => void;
  /** config 없이 팝업 열림 상태 */
  open: () => void;
  /** config 없이 팝업 열림 상태 */
  close: () => void;
};

const usePopup = (): UsePopupReturn => {
  const [config, setConfig] = useState<PopupConfig | null>(null);
  const [loading, setLoading] = useState(false);
  // config 없이 열때
  const [simpleOpen, setSimpleOpen] = useState(false);

  const closePopup = useCallback(() => {
    setConfig(null);
    setLoading(false);
    setSimpleOpen(false);
  }, []);

  const openPopup = useCallback(
    (newConfig: PopupConfig) => {
      setConfig(newConfig);
      setLoading(false);
      setSimpleOpen(false);
    },
    []
  );

  /** config 없이 열기/닫기 */
  const open = useCallback(() => {
    setConfig(null);
    setSimpleOpen(true);
    setLoading(false);
  }, []);

  /** 현재 팝업 열림 상태 여부 */
  const isOpen = config !== null || simpleOpen;

  // CommonPopup에 spread할 props 생성
  const popupProps: CommonPopupProps = {
    open: config !== null,
    onCloseAction: closePopup,
    title: config?.title ?? "",
    message: config?.message,
    type: config?.type ?? "info",
    confirmText: config?.confirmText ?? "확인",
    cancelText: config?.cancelText ?? "취소",
    showCancel: config?.showCancel ?? true,
    onConfirm: config?.onConfirm,
    onCancel: config?.onCancel,
    width: config?.width ?? 400,
    loading: config?.loading ?? loading,
    closeOnBackdrop: config?.closeOnBackdrop ?? true,
    closeOnEsc: config?.closeOnEsc ?? true,
    showCloseButton: config?.showCloseButton ?? true,
  };

  return { popupProps, openPopup, closePopup, isOpen, setLoading, open, close: closePopup };
};

export default usePopup;
