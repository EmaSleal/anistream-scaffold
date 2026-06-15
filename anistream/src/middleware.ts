import { auth } from "@/auth";
import { NextResponse } from "next/server";

export default auth((req) => {
  const { pathname } = req.nextUrl;

  // 1. API pass-through + logging — runs before any redirect
  if (pathname.startsWith("/api")) {
    console.log(`[nextjs] ${req.method} ${pathname} uid=${req.auth?.user?.id ?? "anon"}`);
    return NextResponse.next();
  }

  const isLoggedIn = !!req.auth;
  const isMarketing = pathname === "/";
  const isLogin = pathname === "/login";

  // 2. Authenticated users do not see marketing or login -> push to /home
  if (isLoggedIn && (isMarketing || isLogin)) {
    return NextResponse.redirect(new URL("/home", req.url));
  }

  // 3. Unauthenticated users may only reach public surfaces
  const isPublic = isMarketing || isLogin;
  if (!isLoggedIn && !isPublic) {
    return NextResponse.redirect(new URL("/", req.url));
  }

  // 4. Fall through
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
