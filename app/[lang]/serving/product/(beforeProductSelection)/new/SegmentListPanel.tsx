/**
 * @file SegmentListPanel.tsx
 * @description 세그먼트 목록 패널
 * 
 * 기능:
 * - 세그먼트 추가/편집/삭제
 * - 이름 패턴(영문 대소문자+숫자+언더바) / 길이(2-20자) 검증
 * - 행 클릭 -> 부모해 선택 전달
 * ====================================================
 * 변경 내역:
 * - [20260508] - 타입/상수 => types/product.ts 이동
 *                한글 평문 텍스트 => 다국어 dict key로 변경
 * ====================================================
 */
"use client";

import ...

type EditInputProps = {
  value: string;
  field: keyof EditingRow;
  placeholder: string;
  error?: string;
  inputRef?: React.Ref<HTMLInputElement | null>;
  onChange: (field: keyof EditingRow, value: string) => void;
  onSave: () => void;
  onCancel: () => void;
};

// = 인라인 input 컴포넌트 =
const EditInput = ({
  value,
  field,
  placeholder,
  inputRef,
  error,
  onChange,
  onSave,
  onCancel,
}: EditInputProps) => {
  // IME 조합 중 여부 추적
  const composingRef = useRef(false);

  return (
    <div className="flex-1 min-w-0">
      <input
        ref={inputRef}
        type="text"
        value={value}
        onCompositionStart={() => {
          composingRef.current = true;
        }}
        onCompositionEnd={(e) => {
          composingRef.current = false;
          // 조합 완료 시 최종 값 반영
          onChange(field, (e.target as HTMLInputElement).value);
        }}
        onChange={(e) => {
          if (!composingRef.current) {
            onChange(field, e.target.value);
          }
        }}
        placeholder={placeholder}
        onKeyDown={(e) => {
          if (composingRef.current) return; // 조합 중 Enter/Esc 무시
          if (e.key === "Enter") onSave();
          if (e.key === "Escape") onCancel();
        }}
        className={[
          "w-full px-2.5 py-1.5 text-[13px] text-[#191f28] bg-white",
          "border rounded-md outline-none transition-all duration-150",
          error ? "border-[#f04452] bg-[#fff8f8]" : "border-[#e5e8eb]",
          "focus:border-[#3182f6] focus:ring-1 focus:ring-[#3182f6]/20",
          "placeholder:text-[#b0b8c1]",
        ].join(" ")}
      />
      {error && (
        <p className="text-[10px] text-[#f04452] mt-0.5 leading-tight">
          {error}
        </p>
      )}
    </div>
  );
};

//=============================
// Props
//=============================
type Props = {
  segments: SegmentObj[];
  selectedSegmentId: string | number | null;
  onAdd: (name: string, value: string, exclusion: string) => void;
  onUpdate: (id: string | number, name: string, value: string, exclusion: string) => void;
  onRemove: (id: string | number) => void;
  onSelect: (id: string | number) => void;
  dict: LangDictType;
};

//=============================
// 테이블 Grid 클래스
//=============================
const GRID_COLS = "grid grid-cols-[1.05fr_1fr_1fr_56px] gap-1 px-4";

//=============================
// Component
//=============================
const SegmentListPanel = ({
  segments,
  selectedSegmentId,
  onAdd,
  onUpdate,
  onRemove,
  onSelect,
  dict,
}: Props) => {
  // 편집 중인 행 ID (null: 편집 없음, "new": 새 행 추가중)
  const [editingId, setEditingId] = useState<string | number | "new" | null>(null);
  const [editingRow, setEditingRow] = useState<EditingRow>({
    SegmentName: "",
    SegmentValue: "",
    ExclusionValue: "",
  });
  const [rowErrors, setRowErrors] = useState<RowErrors>({});
  const nameInputRef = useRef<HTMLInputElement>(null);

  // = 삭제 확인 팝업 =
  const [deleteTarget, setDeleteTarget] = useState<DeleteTarget | null>(null);

  // 편집 모드 진입 시 첫 번째 input에 포커스
  useEffect(() => {
    if (editingId !== null) {
      setTimeout(() => nameInputRef.current?.focus(), 50);
    }
  }, [editingId]);

  // = 새 행 추가 시작 =
  const handleStartAdd = useCallback(() => {
    setEditingId("new");
    setEditingRow({ SegmentName: "", SegmentValue: "", ExclusionValue: "" });
    setRowErrors({});
  }, []);

  // = 편집 시작 =
  const handleStartEdit = useCallback((seg: SegmentObj) => {
    setEditingId(seg.Id as string | number);
    setEditingRow({
      SegmentName: seg.SegmentName,
      SegmentValue: seg.SegmentValue,
      ExclusionValue: seg.ExclusionValue,
    });
    setRowErrors({});
  }, []);

  // = 저장 (추가 또는 수정) =
  const handleSave = useCallback(() => {
    const errors = validateRow(editingRow.SegmentName, editingRow.SegmentValue, dict);
    if (Object.keys(errors).length > 0) {
      setRowErrors(errors);
      return;
    }

    if (editingId === "new") {
      onAdd(editingRow.SegmentName, editingRow.SegmentValue, editingRow.ExclusionValue);
    } else if (editingId !== null) {
      onUpdate(editingId, editingRow.SegmentName, editingRow.SegmentValue, editingRow.ExclusionValue);
    }
    setEditingId(null);
    setRowErrors({});
  }, [dict, editingId, editingRow, onAdd, onUpdate]);

  // = 취소 =
  const handleCancel = useCallback(() => {
    setEditingId(null);
    setRowErrors({});
  }, []);

  // = 삭제 확인 -> 실행 =
  const handleDeleteConfirm = useCallback(() => {
    if (deleteTarget) {
      onRemove(deleteTarget.segmentId);
      if (editingId === deleteTarget.segmentId) setEditingId(null);
    }
    setDeleteTarget(null);
  }, [deleteTarget, editingId, onRemove]);

  // = 편집 input 변경 =
  const handleEditChange = useCallback(
    (field: keyof EditingRow, value: string) => {
      setEditingRow((prev) => ({ ...prev, [field]: value }));
      if (rowErrors[field as keyof RowErrors]) {
        setRowErrors((prev) => {
          const next = { ...prev };
          delete next[field as keyof RowErrors];
          return next;
        });
      }
    },
    [rowErrors],
  );

  // = 편집 행 렌더링 (추가/수정) =
  const renderEditRow = () => (
    <>
      <EditInput
        value={editingRow.SegmentName}
        field="SegmentName"
        placeholder={dict.Name}
        error={rowErrors.SegmentName}
        inputRef={nameInputRef}
        onChange={handleEditChange}
        onSave={handleSave}
        onCancel={handleCancel}
      />
      <EditInput
        value={editingRow.SegmentValue}
        field="SegmentValue"
        placeholder={dict.Variable + dict.Value}
        error={rowErrors.SegmentValue}
        onChange={handleEditChange}
        onSave={handleSave}
        onCancel={handleCancel}
      />
      <EditInput
        value={editingRow.ExclusionValue}
        field="ExclusionValue"
        placeholder={dict.ExclusionColumn + dict.Value}
        onChange={handleEditChange}
        onSave={handleSave}
        onCancel={handleCancel}
      />
      <div className="flex items-start gap-a pt-1">
        <button
          type="button"
          onClick={handleSave}
          className="p-1 rounded text-[#3182f6] hover:bg-[#eaf4fe] transition-colors"
          title={`${dict.Save} (Enter)`}
        >
          <SvgIcon name="plus" size={14} />
        </button>
        <button
          type="button"
          onClick={handleCancel}
          className="p-1 rounded text-[#8b95a1] hover:bg-[#f2f4f6] transition-colors"
          title={`${dict.Cancel} (Esc)`}
        >
          <SvgIcon name="x" />
        </button>
      </div>
    </>
  );

  return (
    <div className="flex flex-col h-full">
      {/* 헤더: 세그먼트 목록 + 개수 뱃지 + 추가버튼 */}
      <div className="px-4 pb-3 flex items-center justify-between">
        <span className="text-[13px] font-semibold text-[#4e5968]">
          {dict.Segment} {dict.List}
        </span>
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-semibold text-[#3182f6] bg-[#3182f6]/10 px-2 py-0.5 rounded-md">
            {segments.length}개
          </span>
          <button
            type="button"
            onClick={handleStartAdd}
            disabled={editingId !== null}
            className="flex items-center gap-1 px-2.5 py-1.5 rounded-md text-[12px] font-semibold text-[#3182f6] bg-[#eaf4fe] hover:bg-[#d4e8fd] disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            <SvgIcon name="plus" />
            추가
          </button>
        </div>
      </div>

      {/* 테이블 */}
      <div className="border-t border-[#e5e8eb] flex-1 overflow-y-auto">
        {/* 테이블 헤더 */}
        <div className={`${GRID_COLS} gap-1 px-4 py-2.5 bg-[#f9fafb] border-b border-[#e5e8eb]`}>
          <span className="text-[11px] font-semibold text-[#4e5968] uppercase tracking-wide">{dict.Segment + dict.Name}</span>
          <span className="text-[11px] font-semibold text-[#4e5968] uppercase tracking-wide">{dict.Segment + dict.Variable}</span>
          <span className="text-[11px] font-semibold text-[#4e5968] uppercase tracking-wide">{dict.ExclusionColumn}</span>
        </div>
        {/* 데이터 행 */}
        {segments.map((seg) => {
          const isEditing = editingId === seg.Id;
          const isSelected = selectedSegmentId === seg.Id;

          return (
            <div
              key={seg.Id}
              className={[
                `${GRID_COLS} border-b border-[#f2f4f6] transition-colors items-center`,
                isEditing ? "py-2 bg-[#fafbfc]" : "py-2.5",
                !isEditing && isSelected ? "bg-[#eaf4fe]" : "",
                !isEditing && !isSelected ? "hover:bg-[#f8f9fa] cursor-pointer" : "",
              ].join(" ")}
              onClick={() => {
                if (!isEditing) onSelect(seg.Id);
              }}
            >
              {isEditing ? (
                renderEditRow()
              ) : (
                <>
                  <button
                    type="button"
                    onClick={(e) => { e.stopPropagation(); onSelect(seg.Id); }}
                    className={[
                      "text-left text-[13px] font-semibold truncate",
                      isSelected ? "text-[#3182f6]" : "text-[#3182f6] hover:underline truncate",
                    ].join(" ")}
                  >
                    {seg.SegmentName}
                  </button>
                  <span className="text-[13px] text-[#191f28] truncate">{seg.SegmentValue}</span>
                  <span className="text-[13px] text-[#8b95a1] truncate">{seg.ExclusionValue || "-"}</span>
                  {/* 수정/삭제 버튼 */}
                  <div className="flex items-center gap-1">
                    <button
                      type="button"
                      onClick={(e) => { e.stopPropagation(); handleStartEdit(seg); }}
                      className="p-1 rounded text-[#8b95a1] hover:text-[#3182f6] hover:bg-[#eaf4fe] transition-colors"
                      title={dict.Modify}
                    >
                      <SvgIcon name="edit" />
                    </button>
                    <button
                      type="button"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteTarget({
                          segmentId: seg.Id,
                          segmentName: seg.SegmentName,
                        });
                      }}
                      className="p-1 rounded text-[#8b95a1] hover:text-[#f04452] hover:bg-[#fef2f2] transition-colors"
                      title={dict.Delete}
                    >
                      <SvgIcon name="trash" />
                    </button>
                  </div>
                </>
              )}
            </div>
          );
        })}
        {/* 새 행 추가 (편집 모드) */}
        {editingId === "new" && (
          <div className={`${GRID_COLS} py-2 border-b border-[#f2f4f6] bg-[#fafbfc] items-center`}>
            {renderEditRow()}
          </div>
        )}
        {/* 빈 상태 */}
        {segments.length === 0 && editingId === null && (
          <div className="flex flex-col items-center justify-center py-10 text-[#b0b8c1]">
            <p className="text-[13px]">{dict.SegmentNoData}</p>
            <button
              type="button"
              onClick={handleStartAdd}
              className="mt-2 pr-3 text-[12px] font-semibold text-[#3182f6] hover:underline"
            >
              + {dict.SegmentAdd}
            </button>
          </div>
        )}
      </div>
      {/* 삭제 확인 팝업 */}
      <CommonPopup
        open={deleteTarget !== null}
        onCloseAction={() => setDeleteTarget(null)}
        type="danger"
        title={dict.Segment + dict.Delete}
        message={`"${deleteTarget?.segmentName ?? ""}" ${dict.SegmentDelete}`}
        confirmText={dict.Delete}
        cancelText={dict.Cancel}
        showCancel
        onConfirm={handleDeleteConfirm}
      />
    </div>
  );
};

export default SegmentListPanel;
