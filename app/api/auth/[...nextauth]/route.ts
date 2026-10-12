import NextAuth from "next-auth";
import { authOptions } from "@/lib/authOptions";

const handler : any = NextAuth(authOptions);

export const dynamic = "force-dynamic"; /** 모든 요청 런타임 실행 -> 항상 최신 상태 반영*/
export { handler as GET, handler as POST };
