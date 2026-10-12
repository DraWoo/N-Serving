//
// 사전 키 추가/수정은 dictionaries/ko/*.json 에서 하세요.
// 이후 'npm run gen:dict' 또는 'npm run dev' 실행 시
// 이 파일이 자동으로 갱신됩니다.
//

/** common.json 사전 타입 */
export interface CommonDict {
  /** 이름 */
  Name: string;
  /** 값 */
  Value: string;
  /** 소유자 */
  Owner: string;
  /** 멤버 */
  Member: string;
  /** 생성자 */
  Creator: string;
  /** 마지막 수정일시 */
  LastModifiedDt: string;
  /** 생성일시 */
  CreatedDt: string;
  /** 설명 */
  Description: string;
  /** 마트 */
  Mart: string;
  /** 변수 */
  Variable: string;
  /** 데이터 */
  Data: string;
  /** 모델 */
  Model: string;
  /** 평점 */
  Score: string;
  /** 등급 */
  Grade: string;
  /** 개수 */
  Count: string;
  /** 행 */
  Row: string;
  /** 열 */
  Column: string;
}
