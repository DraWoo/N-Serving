// lib/authOptions.ts (session / jwt 설정 부분만 발췌)
//
// ============================================================
// [수정 요약 — 이슈 2: 토큰이 30일로 발급되던 문제]
// ------------------------------------------------------------
// 원래 문제:
//   - session.maxAge: 30분으로 설정했는데 세션이 최대 30일 유지
//   - 금요일 로그인 → 월요일 접속 시 자동 진입 (금융권 보안 위반)
//
// 원인:
//   - strategy: "jwt"에서 실제 토큰 만료(exp)는 jwt.maxAge가 결정함
//   - jwt.maxAge를 누락 → NextAuth 기본값(30일=2592000초)으로 토큰 발급
//   - middleware는 getToken으로 토큰 exp(30일)만 봄 → session.maxAge(30분) 무력화
//   - 진단: middleware 로그에서 "수명초: 2592000"(30일) 확인됨
//
// 수정:
//   - jwt.maxAge를 명시적으로 추가 (session.maxAge와 동일 값으로 일치)
//   - 운영값은 30분, 테스트 시에만 60초로 줄여서 확인 후 원복
// ============================================================

export const authOptions = {
  // ... providers, callbacks 등 생략 ...

  secret: process.env.NEXTAUTH_SECRET,

  jwt: {
    // @ts-expect-error
    encryption: true,

    // ───────────────────────────────────────────────────────
    // [수정] ✅ 추가됨 — jwt.maxAge
    //   이 값이 실제 토큰의 exp(물리적 만료)를 결정함.
    //   누락 시 기본 30일로 발급되어 session.maxAge가 무력화됨.
    //   session.maxAge와 동일하게 맞추는 것이 실무 표준.
    // ───────────────────────────────────────────────────────
    maxAge: 30 * 60, // 30분 (운영) — 테스트 시 60으로 변경 후 반드시 원복
  },

  session: {
    strategy: "jwt" as const,
    maxAge: 30 * 60,   // 세션 유효 판단 30분
    updateAge: 5 * 60, // 5분
  },

  // ... 이하 생략 ...
};
