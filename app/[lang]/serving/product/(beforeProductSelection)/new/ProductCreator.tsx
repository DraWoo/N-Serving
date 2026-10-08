/**
 * @file ProductCreator.tsx
 * @description 새 상품 등록 페이지 메인 컴포넌트
 * ----------------------------------------------------
 * 기능 요약:
 * 1. 상품 기본 정보 입력( 이름, 설명, 상세 설명)
 * 2. 세그먼트 변수 설정(변수 이름, 제외 대상 변수)
 * 3. 세그먼트 목록 관리(추가/편집/삭제 - DataGrid)
 * 4. 세그먼트 상세 편집(모델/보정/등급 - SegmentManage)
 * 5. CommonPopup 확인 -> clientUpload로 FormData 전송
 * ----------------------------------------------------
 * 분리된 파일:
 * - SegmentListPanel.tsx -> 세그먼트 목록
 * - ProductConfirmContent.tsx -> 확인 팝업 본문
 * - productValidation.tsx -> 검증 로직 함수
 * 
 * 분리된 파일 (공용)
 * - components/common/InputField.tsx -> 공용 입력 필드
 * - components/common/CommonPopup.tsx -> 공용 팝업
 * - components/common/DxHtmlEditor.tsx -> HtmlEditor lazy wrapper
 * - components/serving/SegmentManager.tsx -> 세그먼트 상세
 * 
 * ====================================================
 * 변경 내역:
 * - [20260714] - product(타입분리)
 *                FormData 파일 전송: 동적 필드명(mdl_*) => 고정 필드명 files + models
 *                Form 전송 실패 시 팝업 추가
 *                DxHtmlEditor => lazyLoading 제거
 * ====================================================
 */

"use client";

import ...

type ProductCreatorProps = {
  dict: LangDictType,
  baseUrl: string
  lang?:string; // [20250825] - /ko default 값 설정
}

export default function ProductCreator({
  dict,
  baseUrl,
  lang ='ko'
}: ProductCreatorProps) : Element {
  const router = useRouter();
  // = state =
  /**[생성된 상품 ID - 0이면 미생성, > 0 이면 완료]*/
  const [newProductId, setNewProductId] = useState<number>(0);
  /**[상품 기본 정보 폼 데이터]*/
  const [newProduct, setNewProduct] = useState<ProductObj>(initProduct());
  /**[상품 기본 정보 폼 데이터]*/
  const [newSegments, setNewSegments] = useState<SegmentObj[]>([]);
  /**
   * 현재 선택된 세그먼트 (오른쪽 SegmentManager에 전달)
   * - null: 미선택 -> "선택하세요" 안내표시
   * - SegmentObj: 선택됨 -> SegmentManager 표시
   */
  const [selectedSegment, setSelectedSegment] = useState<SegmentObj | null>(null);
  /**[확인 모달 표시 여부]*/
  const [confirmVisible, setConfirmVisible] = useState(false);
  /**[제출 중 여부 - 버튼 중복 클릭 방지 ]*/
  const [isSubmitting, setIsSubmitting] = useState(false);
  /**[필드별 검증 에러 메시지]*/
  const [fieldErrors, setFieldErrors ] = useState<Record<string, string>>({});
  /**[form전송 실패 시 Error 핸들러]*/
  const [submitError, setSubmitError] = useState<string | null>(null);

  //=============================
  // Refs
  //=============================
  const productNameRef = useRef<HTMLInputElement>(null);
  const segmentColumnRef = useRef<HTMLInputElement>(null);
  const segmentIdCounter = useRef(1);

  //= 필드별 ref 매핑 =
  const fieldRefMap = useMemo(() => ({
    ProductName: productNameRef,
    SegmentColumn: segmentColumnRef,
  }), []);

  /**[Zustand store]*/
  const invalidateByPrefix = useApiCacheStore((state ) => state.invalidateByPrefix);
  const invalidateKey = useApiCacheStore((state ) => state.invalidate);

  //=============================
  // 상품 필드 변경 핸들러
  //=============================
  /**[상품 기본 정보 필드 변경 핸들러]*/
  const handleProductChanged = useCallback((key: keyof ProductObj, value: string) => {
    setNewProduct((prev ) => ({ ...prev, [key]: value }));
    // 해당 필드 에러 제거
    if (fieldErrors[key]) {
      setFieldErrors((prev ) => {
        const next = { ...prev};
        delete next[key];
        return next;
      });
    }
  },[fieldErrors]);

  //=============================
  // Grid 검증 함수
  //=============================

  /** SegmentManager 콜백 */
  const handleSegmentFileChanged = useCallback(
    (key: keyof SegmentObj, value: SegmentFileValue) => {
      setSelectedSegment((prev ) => (prev ? { ...prev, [key]: value } : prev));
    },[]);

  /**[세그먼트 전체 검증]*/
  const validateSegment = useCallback(() => {
    if (selectedSegment === null) return true;
    const seg: SegmentObj = selectedSegment;

    // = calibration 검증 =
    const calErrors = seg.HasCalibration
      ? validateCalibrationGrid(seg.Calibration, dict)
      : [];
    // = grade 검증 =
    const gradeErrors = seg.HasCalibration
      ? validateGradeGrid(seg.Grade, dict)
      : [];

    // = 모델 검증 =
    const modelErrors = validateModelGrid(seg.Models, dict);

    // = 에러가 있으면 alert + state 업데이트 =
    if (calErrors.length > 0 || gradeErrors.length > 0 || modelErrors.length > 0) {
      alert(
        [
          ...calErrors.map((x ) => `[Calibration] ${x}`),
          ...gradeErrors.map((x ) => `[Grade] ${x}`),
          ...modelErrors.map((x ) => `[Model] ${x}`),
        ].join('\n'),
      );
      setSelectedSegment((prev ) =>
        prev
          ? {
              ...prev,
              ValidationResult: {
                Calibration: calErrors,
                Grade: gradeErrors,
                Models: modelErrors,
              },
            }
          : prev,
      );
      return false;
    }
    return true;
  }, [dict, selectedSegment]);

  //=============================
  // 세그먼트 목록 콜백 (SegmentListPanel)
  //=============================

  /**[세그먼트 추가]*/
  const handleSegmentAdd = useCallback((name: string, value: string, exclusion: string) => {
    const id = `seg_${segmentIdCounter.current++}`;
    const newSeg = {
      ...initSegment(id, name),
      SegmentName: name,
      SegmentValue: value,
      ExclusionValue: exclusion,
    };
    setNewSegments((prev ) => [...prev, newSeg]);
  }, []);

  /**[세그먼트 수정]*/
  const handleSegmentUpdate = useCallback((id: string | number, name: string, value: string, exclusion: string) => {
    setNewSegments((prev ) =>
      prev.map((seg ) =>
        seg.Id === id
          ? { ...seg, SegmentName: name, SegmentValue: value, ExclusionValue: exclusion }
          : seg,
      ),
    );

    // 선택된 세그먼트도 동기화
    if (selectedSegment?.Id === id) {
      setSelectedSegment((prev ) =>
        prev
          ? { ...prev, SegmentName: name, SegmentValue: value, ExclusionValue: exclusion }
          : prev,
      );
    }
  }, [selectedSegment]);

  /**[세그먼트 삭제]*/
  const handleSegmentRemove = useCallback((id: string | number) => {
    setNewSegments((prev ) => prev.filter((seg ) => seg.Id !== id));
    if (selectedSegment?.Id === id) setSelectedSegment(null);
  }, [selectedSegment]);

  /**
   * 세그먼트 행 클릭 -> 오른쪽 SegmentManager 파널 전환
   * 동작 순서:
   * 1. 이전에 선택된 세그먼트가 있으면 -> validateSegment() 실행
   * 3. 검증 통과 -> 이전 세그먼트 상태를 newSegment[]에 반영
   * 4. 새 세그먼트 selectedSegment로 설정
   */
  const handleSegmentSelect = useCallback(
    (selectedId: string | number) => {
      setNewSegments((prev ) => {
        // 이전 선택 세그먼트가 있는 경우 -> 검증 후 저장
        if (selectedSegment) {
          if (selectedSegment.Id === selectedId) return prev;

          // 검증 실패: 다른 세그먼트로 넘어가지 못함
          const isValid = validateSegment();
          if (!isValid) return prev;

          // 이전 세그먼트 상태를 목록에 반영
          const updated = prev.map((seg ) =>
            seg.Id === selectedSegment.Id
              ? {
                  ...selectedSegment,
                  SegmentName: seg.SegmentName,
                  SegmentValue: seg.SegmentValue,
                  ExclusionValue: seg.ExclusionValue,
                }
              : seg,
          );

          // 새 세그먼트 선택 [ValidationResult 초기화]
          const next = updated.find((seg ) => seg.Id === selectedId);
          setSelectedSegment(
            next
              ? { ...next, ValidationResult: { Calibration: [], Grade: [], Models: [] } }
              : null,
          );
          return updated;
        }

        // 이전 선택 없음 -> 바로 선택
        setSelectedSegment(prev.find((seg ) => seg.Id === selectedId) ?? null);
        return prev;
      });
    },
    [selectedSegment, validateSegment], // [E] - 세그먼트 DataGrid 이벤트
  );

  //=============================
  // 모델 파일 업로드 완료 -> selectedSegment.Models 업데이트
  //=============================
  /**[모델 파일 업로드 완료 시 호출]*/
  const handleModelChanged = useCallback((uploaded: MdlFileObj) => {
    setSelectedSegment((prev ) => {
      if (!prev) return prev;
      return {
        ...prev,
        Models: prev.Models.map((m ) =>
          m.ModelId === uploaded.ModelId
            ? {
                ...m,
                ModelFile: uploaded.ModelFile,
                ModelType: uploaded.ModelType,
                SubTarget: uploaded.SubTarget,
              }
            : m,
        ),
      };
    });
  }, []);

  /**[폼 제출 핸들러]*/
  const handleSubmit = useCallback(
    (e: React.FormEvent<HTMLFormElement>) => {
      e.preventDefault();

      // 1차 상품 필드 검증
      const productErrors = validateProductFields(newProduct, dict);
      if (productErrors.length > 0) {
        const map: Record<string, string> = {};
        productErrors.forEach((error ) => {
          map[error.field] = error.message;
        });
        setFieldErrors(map);

        type FieldKey = keyof typeof fieldRefMap;
        // 첫 번째 에러 필드에 포커스
        const firstErrorField = productErrors[0].field;
        const targetRef = fieldRefMap[firstErrorField as FieldKey];
        setTimeout(() => targetRef?.current?.focus(), 50);
        return;
      }
      setFieldErrors({});

      // 2차 세그먼트 검증 (선택된 것이 있으면)
      if (selectedSegment) {
        if (!validateSegment()) return;
      }

      // 편집 중인 세그먼트 형태를 목록에 병합 후 모달 표시
      setNewSegments((prev ) => {
        setConfirmVisible(true);
        return prev.map((seg ) =>
          seg.Id === selectedSegment.Id
            ? {
                ...selectedSegment,
                SegmentName: seg.SegmentName,
                SegmentValue: seg.SegmentValue,
                ExclusionValue: seg.ExclusionValue,
              }
            : seg,
        );
      });
    },
    [dict, fieldRefMap, newProduct, selectedSegment, validateSegment],
  );

  /**[확인버튼클릭 -> clientUpload FormData 전송]*/
  const handleConfirmClick = useCallback(async () => {
    setIsSubmitting(true);

    const minWait = new Promise((resolve ) => setTimeout(resolve, 700));

    try {
      const formData = new FormData();

      // 상품/세그먼트 정보는 JSON 문자열로 (기준과 동일)
      formData.append("product", JSON.stringify(newProduct));
      formData.append("segments", JSON.stringify(newSegments));

      //----------------------------------------------------
      // * 모델 파일 전송 - files 고정 필드명 + models
      // - 순서: files를 append 한 순서 = models list 순서
      // - 파일이 없는 모델은 둘 다 제외
      //----------------------------------------------------
      const modelIdList: string[] = [];

      newSegments.forEach((seg ) => {
        seg.Models.forEach((m ) => {
          if (m.ModelFile) {
            formData.append("files", m.ModelFile); // 파일 -> 전부 "files"
            modelIdList.push(m.ModelId.toString()); // 같은 순서로 id
          }
        });
      });

      // models는 JSON list 전송
      formData.append("models", JSON.stringify(modelIdList));

      // [DEBUG] 전송 직전 FormData 내용 확인
      logFormData(formData, "상품 등록");

      // API 호출 - clientUpload
      interface CreateProductResponse {
        PRODUCT_ID: number;
      }

      const [result] = await Promise.all([
        clientUpload<CreateProductResponse>({
          endpoint: "serving/product",
          formData,
          method: "POST",
        }),
        minWait,
      ]);

      if (result !== null && "PRODUCT_ID" in result) {
        setNewProductId(result.PRODUCT_ID);

        // 상품 목록 cache 무효화 -> 목록 페이지 돌아갔을때 새 상품 렌더링
        invalidateKey(buildCacheKey({ endpoint: "serving/product-list", }));
        invalidateByPrefix("serving/product");

        // 백그라운드 미리 loading
        router.prefetch(`/${lang}${baseUrl}/${result.PRODUCT_ID}`);
      } else {
        setConfirmVisible(false);
        setSubmitError("상품 등록에 실패했습니다.\n입력 값을 확인 후 다시 시도해주세요.");
      }
    } finally {
      setIsSubmitting(false);
    }
  }, [baseUrl, invalidateByPrefix, invalidateKey, lang, newProduct, newSegments, router]);

  //=============================
  // Render
  //=============================
  return (
    <>
      <div className="min-h-screen bg-[#f7f8fa]">
        {/*====================================================
            page Header
        ====================================================*/}
        <div className="bg-white border-b border-[#e5e8eb] px-8 py-5 mb-6">
          <div className="max-w-[1280px] mx-auto px-8 pb-10">
            <div>
              <h3 className="text-lg font-extrabold text-[#191f28] tracking-tight">
                {dict.CreateNewProduct}
              </h3>
              <p className="text-[13px] text-[#8b95a1]">
                {dict.ProductSetupGuide}
              </p>
            </div>
          </div>
        </div>
        <div className="max-w-[1280px] mx-auto px-8 pb-10">
          <form onSubmit={handleSubmit}>
            {/*====================================================
                Step 1: 상품 기본 정보
            ====================================================*/}
            <section className="bg-white rounded-2xl border border-[#e5e8eb] mb-6 overflow-hidden">

              <div className="px-6 pt-5">
                <div className="flex items-center gap-2.5 mb-1">
                  <span
                    className="w-6 h-6 rounded-lg bg-[#3182f6] text-white text-xs font-bold flex items-center justify-center"
                  >
                    1
                  </span>
                  <h4 className="text-[16px] font-bold text-[#191f28] tracking-tight">
                    {dict.Product} {dict.BasicInfo}
                  </h4>
                </div>
                <p className="text-[13px] text-[#8b95a1] mb-4 pl-[34px]">
                  {dict.ProductNameDescGuide}
                </p>
              </div>

              <div className="px-6 pb-6">
                {/* 상품 이름 + 설명(가로 배치, 모바일에서 세로 전환) */}
                <div className="flex flex-wrap gap-3.5 mb-3.5">
                  <InputField
                    ref={productNameRef}
                    label={`${dict.Product} ${dict.Name}`}
                    value={newProduct.ProductName}
                    onChange={(v) => handleProductChanged("ProductName", v)}
                    placeholder="예: PRODUCT"
                    required
                    note={`영문 대문자 ${PRODUCT_NAME_LENGTH[0]}-${PRODUCT_NAME_LENGTH[1]}자`}
                    error={fieldErrors.ProductName}
                  />
                  <InputField
                    label={`${dict.Product} ${dict.Description}`}
                    value={newProduct.ProductShortDesc}
                    onChange={(v) => handleProductChanged("ProductShortDesc", v)}
                    placeholder={dict.ProductShortDesc}
                  />
                </div>
                {/* 상세 설명 - DxHtmlEditor (lazy) */}
                <div>
                  <label className="flex items-center gap-1 text-[13px] font-semibold text-[#4e5968] tracking-tight">
                    {dict.ProductAdditionalDetail}
                  </label>
                  <div>
                    <div
                      className="border border-[#e5e8eb] rounded-[10px] overflow-hidden bg-[#f9fafb] focus-within:border-[#3182f6] focus-within:ring-2 focus-within:ring-[#3182f6]/15 transition-all"
                    >
                      <DxHtmlEditor
                        value={newProduct.ProductLongDesc}
                        onValueChanged={(v) => handleProductChanged("ProductLongDesc", v)}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </section>
            {/*===================================
                Step 2: 세그먼트 변수 설정
            ===================================*/}
            <section className="bg-white rounded-2xl border border-[#e5e8eb] mb-4 overflow-hidden">
              <div className="px-6 pt-5">
                <div className="flex items-center gap-2.5 mb-1">
                  <span
                    className="w-6 h-6 rounded-lg bg-[#3182f6] text-white text-xs font-bold flex items-center justify-center"
                  >
                    2
                  </span>
                  <h4 className="text-[16px] font-bold text-[#191f28] tracking-tight">
                    {dict.Segment} {dict.Information}
                  </h4>
                </div>
                <p className="text-[13px] text-[#8b95a1] mb-4 pl-[34px]">
                  {dict.SegmentSetupGuide}
                </p>
              </div>
              <div className="px-6 pb-6 flex flex-wrap gap-3.5">
                {/* 상품 이름 + 설명(가로 배치, 모바일에서 세로 전환) */}
                <InputField
                  ref={segmentColumnRef}
                  label={`${dict.SegmentationColumn} ${dict.Name}`}
                  value={newProduct.SegmentColumn}
                  onChange={(v) => handleProductChanged("SegmentColumn", v)}
                  placeholder="예: SEG_TYPE"
                  required
                  error={fieldErrors.SegmentColumn}
                />
                <InputField
                  label={`${dict.ExclusionColumn} ${dict.Name}`}
                  value={newProduct.ExclusionColumn}
                  onChange={(v) => handleProductChanged("ExclusionColumn", v)}
                  placeholder="예: EXCL_FLAG"
                />
              </div>
            </section>

            {/*===================================
                Step 3: 세그먼트 구성
            ===================================*/}
            <section className="bg-white rounded-2xl border border-[#e5e8eb] mb-4 overflow-hidden">
              <div className="px-6 pt-5">
                <div className="flex items-center gap-2.5 mb-1">
                  <span
                    className="w-6 h-6 rounded-lg bg-[#3182f6] text-white text-xs font-bold flex items-center justify-center"
                  >
                    3
                  </span>
                  <h4 className="text-[16px] font-bold text-[#191f28] tracking-tight">
                    {dict.Segment} {dict.Management}
                  </h4>
                </div>
                <p className="text-[13px] text-[#8b95a1] mb-4 pl-[34px]">
                  {dict.SegmentSetupGuide}
                </p>
              </div>

              <div className="grid grid-cols-[340px_1fr] min-h-[520px] max-[900px]:grid-cols-1">
                {/* 세그먼트 목록 */}
                <div className="border-r border-[#e5e8eb] pb-5 max-[900px]:border-r-0 max-[900px]:border-b ${styles.segmentGrid}">
                  <SegmentListPanel
                    segments={newSegments}
                    selectedSegmentId={selectedSegment?.Id ?? null}
                    onAdd={handleSegmentAdd}
                    onUpdate={handleSegmentUpdate}
                    onRemove={handleSegmentRemove}
                    onSelect={handleSegmentSelect}
                    dict={dict}
                  />
                </div>

                {selectedSegment ? (
                  <div className="p-6 animate-[fadeIn_0.2s_ease-out]" key={selectedSegment.Id}>
                    <SegmentManager
                      segment={selectedSegment}
                      handleSegmentChanged={handleSegmentFileChanged}
                      handleModelChanged={handleModelChanged}
                      validateCalibrationGrid={(data: ScoreMappingObj[]) => validateCalibrationGrid(data, dict)}
                      validateGradeGrid={(data: GradeObj[]) => validateGradeGrid(data, dict)}
                      dict={dict}
                      mode="create"
                    />
                  </div>
                ) : (
                  // 미선택 시 안내화면
                  <div className="flex flex-col items-center justify-center min-h-[400px] text-[#8b95a1] pl-5">
                    <div className="text-[15px] font-semibold text-[#4e5968]">
                      {dict.SegmentSelectGuide}
                    </div>
                    <div className="text-[12px] text-[#b0b8c1] mt-1">
                      {dict.SegmentDetailGuide}
                    </div>
                  </div>
                )}
              </div>
            </section>

            {/* 제출버튼 */}
            <div className="flex justify-end pt-2">
              <button
                type="submit"
                disabled={isSubmitting}
                className="flex items-center gap-1.5 px-5 py-2 rounded-[4px] border border-[#3182f6] text-[#3182f6] bg-white text-sm font-bold tracking-tight hover:bg-[#f0f6ff] active:bg-[#e8f3ff] disabled:cursor-not-allowed transition-all duration-150"
              >
                <SvgIcon name="btnPlus" size={18} />
                {dict.CreateNewProduct}
              </button>
            </div>
          </form>
        </div>
        <CommonPopup
          open={confirmVisible}
          onCloseAction={() => {
            if (newProductId > 0) {
              router.replace(`/${lang}${baseUrl}/${newProductId}`);
            } else {
              setConfirmVisible(false);
            }
          }}
          type={newProductId > 0 ? "success" : "info"}
          onConfirm={
            newProductId > 0
              ? () => router.replace(`/${lang}${baseUrl}/${newProductId}`)
              : handleConfirmClick
          }
          title={newProductId > 0 ? "등록 완료" : dict.CreateNewProduct}
          confirmText={newProductId > 0 ? "확인" : dict.Confirm}
          cancelText={dict.Cancel}
          showCancel={newProductId === 0}
          showCloseButton={newProductId === 0}
          loading={isSubmitting}
          width={540}
        >
          <ProductConfirmContent
            newProductId={newProductId}
            newProduct={newProduct}
            newSegments={newSegments}
            dict={dict}
          />
        </CommonPopup>
        <CommonPopup
          open={submitError !== null}
          onCloseAction={() => setSubmitError(null)}
          type="danger"
          title="상품 등록 실패"
          message={submitError ?? ""}
          confirmText="확인"
          showCancel={false}
          onConfirm={() => setSubmitError(null)}
        />
        {/* fadeIn 애니메이션 */}
        <style>{`
          @keyframes fadeIn {
            from { opacity: 0; transform: translateY(6px); }
            to { opacity: 1; transform: translateY(0); }
          }
        `}</style>
      </div>
    </>
  );
}
