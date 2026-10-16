
/**
 * @file next.config.ts
 * @description N-Serving 프론트엔드 Next.js 빌드 및 보안 설정
 *
 * @project N-Serving (ML Serving Platform)
 *
 * @overview
 * 퍼블리싱 프로젝트를 기준으로 기존 개발 프로젝트의
 * 인증, API 통신 및 업무 기능을 이관하기 위한 설정 파일이다.
 *
 * 퍼블리싱 프로젝트의 standalone 배포 설정을 유지하고,
 * 기존 프로젝트에서 사용하던 DevExtreme 빌드 설정과
 * 공통 보안 응답 헤더를 통합한다.
 *
 * @migration
 * - 기준 프로젝트: N-Serving 퍼블리싱 프로젝트
 * - 이관 대상: 기존 N-Serving 개발 프로젝트
 * - 설정 파일: next.config.mjs → next.config.ts
 * - 퍼블리싱 구조와 기존 업무 기능의 호환성을 우선한다.
 *
 * @security
 * - CSP는 Report-Only로 적용하여 위반 사항만 확인한다.
 * - 인증 및 API 프록시 응답에 캐시 방지 헤더를 적용한다.
 * - HSTS는 운영 HTTPS 환경에서 선택적으로 활성화한다.
 * - 실제 인증과 접근 권한 검증은 별도 인증·API 계층에서 수행한다.
 *
 * @note
 * - 환경별 보안 설정은 빌드 시점의 환경변수를 기준으로 생성된다.
 * - 설정 변경 후 타입 검사, 빌드 및 주요 기능 회귀 테스트가 필요하다.
 */

import type { NextConfig } from "next"; // Next.js 설정 항목의 타입을 검사합니다.

// ───────────────────────────────────────────────────────────────
// 1. 환경 설정
// ───────────────────────────────────────────────────────────────

// 개발 환경에서만 필요한 CSP 완화 정책을 구분합니다.
const isDev = process.env.NODE_ENV === "development";

// HTTPS 운영 환경에서 HSTS 적용 여부를 명시적으로 제어합니다.
const enableHsts = process.env.ENABLE_HSTS === "true";

// 환경변수에 입력된 주소가 올바른 출처 형식인지 확인합니다.
function readOriginEnv(name: string) {
  const value = process.env[name] ?? ""; // 미설정 환경에서는 빈 문자열을 사용합니다.

  if (!value) return ""; // Keycloak 출처가 필요하지 않은 환경도 허용합니다.

  // URL 파싱이 가능한 값인지 먼저 확인합니다.
  if (!URL.canParse(value)) {
    throw new Error(`${name}에 올바른 URL을 입력해야 합니다.`);
  }

  const url = new URL(value); // 출처와 경로를 구분하기 위해 URL 객체를 생성합니다.

  // HTTP 또는 HTTPS 출처만 허용합니다.
  if (!["http:", "https:"].includes(url.protocol)) {
    throw new Error(`${name}은 HTTP 또는 HTTPS 주소여야 합니다.`);
  }

  // 경로·쿼리·끝 슬래시가 포함된 값은 허용하지 않습니다.
  if (url.origin !== value) {
    throw new Error(`${name}에는 출처만 입력해야 합니다. 예: https://sso.example.co.kr`);
  }

  return value; // 검증된 출처만 CSP 설정에 사용합니다.
}

// Keycloak Issuer와 별도로 브라우저 보안 정책에 사용할 출처를 읽습니다.
const keycloakOrigin = readOriginEnv("KEYCLOAK_ORIGIN");

// CSP 위반 보고 엔드포인트는 설정된 경우에만 사용합니다.
const cspReportUri = process.env.CSP_REPORT_URI ?? "";

// 출처가 설정된 경우에만 Keycloak을 허용 목록에 포함합니다.
const keycloakSources = keycloakOrigin ? [keycloakOrigin] : [];

// ───────────────────────────────────────────────────────────────
// 2. CSP 정책 (Report-Only)
// ───────────────────────────────────────────────────────────────

// 브라우저에서 허용할 리소스 출처를 정의합니다.
const cspDirectives: Record<string, string[]> = {
  "default-src": ["'self'"], // 별도 지정하지 않은 리소스는 동일 출처만 허용합니다.

  "script-src": [
    "'self'",
    "'unsafe-inline'", // 기존 Next.js 인라인 스크립트와의 호환성을 우선합니다.
    ...(isDev ? ["'unsafe-eval'"] : []), // 개발 환경에서만 eval을 허용합니다.
  ],

  "style-src": ["'self'", "'unsafe-inline'"], // DevExtreme의 인라인 스타일 사용을 고려합니다.

  "img-src": ["'self'", "data:", "blob:"], // 기존 이미지 및 Blob 기반 리소스를 허용합니다.

  "font-src": ["'self'", "data:"], // 사내 폰트 및 아이콘 폰트 사용을 허용합니다.

  "connect-src": [
    "'self'",
    ...(isDev ? ["ws:"] : []), // 개발 환경의 HMR 웹소켓 연결을 허용합니다.
  ],

  "frame-src": ["'self'"], // 기본적으로 동일 출처의 프레임만 허용합니다.

  "form-action": ["'self'", ...keycloakSources], // 인증 과정에서 필요한 폼 제출 출처를 허용합니다.

  "frame-ancestors": ["'none'"], // 외부 페이지에서 애플리케이션을 iframe으로 삽입하지 못하도록 지정합니다.

  "base-uri": ["'self'"], // base 태그를 이용한 경로 변경을 제한합니다.

  "object-src": ["'none'"], // 사용하지 않는 플러그인 콘텐츠를 제한합니다.

  ...(cspReportUri ? { "report-uri": [cspReportUri] } : {}), // 보고 주소가 있을 때만 위반 보고를 활성화합니다.
};

// CSP 지시어를 실제 HTTP 헤더 문자열로 변환합니다.
const contentSecurityPolicy = Object.entries(cspDirectives)
  .map(([directive, sources]) => [directive, ...sources].join(" ")) // 각 지시어와 허용 출처를 연결합니다.
  .join("; "); // 브라우저가 해석할 수 있도록 지시어를 구분합니다.

// ───────────────────────────────────────────────────────────────
// 3. 공통 보안 응답 헤더
// ───────────────────────────────────────────────────────────────

// 응답 헤더의 구조를 명확하게 정의합니다.
type HeaderEntry = {
  key: string; // HTTP 응답 헤더 이름을 지정합니다.
  value: string; // HTTP 응답 헤더 값을 지정합니다.
};

// 애플리케이션 전체에 적용할 보안 헤더입니다.
const securityHeaders: HeaderEntry[] = [
  {
    key: "X-Content-Type-Options",
    value: "nosniff", // 브라우저의 MIME 유형 추측을 방지합니다.
  },
  {
    key: "X-Frame-Options",
    value: "DENY", // 외부 iframe 삽입을 제한합니다.
  },
  {
    key: "X-XSS-Protection",
    value: "0", // 구형 브라우저의 XSS 필터를 비활성화합니다.
  },
  {
    key: "Referrer-Policy",
    value: "strict-origin-when-cross-origin", // 다른 출처로 이동할 때 URL 경로 노출을 제한합니다.
  },
  {
    key: "Permissions-Policy",
    value: "camera=(), microphone=(), geolocation=(), payment=()", // 사용하지 않는 브라우저 권한을 제한합니다.
  },
  {
    key: "Content-Security-Policy-Report-Only",
    value: contentSecurityPolicy, // CSP 위반 사항을 확인하되 실제 리소스는 차단하지 않습니다.
  },
  ...(enableHsts
    ? [
        {
          key: "Strict-Transport-Security",
          value: "max-age=31536000", // HTTPS 접속을 1년 동안 유지하도록 브라우저에 알립니다.
        },
      ]
    : []), // HSTS가 비활성화된 환경에서는 헤더를 추가하지 않습니다.
];

// 인증 및 백엔드 프록시 응답에 사용할 캐시 방지 헤더입니다.
const noStoreHeaders: HeaderEntry[] = [
  {
    key: "Cache-Control",
    value: "no-store, max-age=0", // 사용자별 인증·업무 응답이 저장되지 않도록 합니다.
  },
  {
    key: "Pragma",
    value: "no-cache", // 구형 HTTP 프록시와의 호환성을 고려합니다.
  },
];

// ───────────────────────────────────────────────────────────────
// 4. Next.js 설정
// ───────────────────────────────────────────────────────────────

// 퍼블리싱 프로젝트의 배포 설정과 기존 개발 설정을 통합합니다.
const nextConfig: NextConfig = {
  output: "standalone", // Docker 실행에 필요한 서버 산출물을 생성합니다.

  reactStrictMode: true, // 개발 과정에서 잠재적인 부작용을 발견하도록 합니다.

  poweredByHeader: false, // 기본 X-Powered-By 응답 헤더를 제거합니다.

  webpack: (config, { dev }) => {
    // 기존 DevExtreme 개발 환경의 Inferno 설정을 유지합니다.
    if (dev) {
      config.resolve.alias = {
        ...(config.resolve.alias ?? {}), // 기존 별칭 설정을 보존합니다.
        inferno: "inferno/dist/index.dev.esm.js", // 개발용 Inferno 모듈을 사용합니다.
      };
    }

    return config; // 변경된 Webpack 설정을 반환합니다.
  },

  experimental: {
    optimizePackageImports: [
      "devextreme-react", // DevExtreme React 패키지의 import 최적화를 적용합니다.
      "devextreme", // DevExtreme 핵심 패키지의 import 최적화를 적용합니다.
    ],
  },

  transpilePackages: [
    "devextreme-react", // Next.js 빌드 과정에서 패키지를 변환합니다.
    "devextreme", // 핵심 패키지도 동일하게 처리합니다.
  ],

  images: {
    unoptimized: true, // Next.js 이미지 최적화 기능을 사용하지 않습니다.
  },

  async headers() {
    return [
      {
        source: "/:path*", // 모든 애플리케이션 경로에 공통 보안 헤더를 적용합니다.
        headers: securityHeaders, // 공통 보안 정책을 재사용합니다.
      },
      {
        source: "/api/auth/:path*", // 인증 관련 응답 경로를 지정합니다.
        headers: noStoreHeaders, // 인증 응답의 캐시 저장을 제한합니다.
      },
      {
        source: "/api/proxy/:path*", // 백엔드 프록시 응답 경로를 지정합니다.
        headers: noStoreHeaders, // 업무 데이터 응답의 캐시 저장을 제한합니다.
      },
    ];
  },
};

// Next.js 설정 파일은 프레임워크 규칙에 따라 default export를 사용합니다.
export default nextConfig;
