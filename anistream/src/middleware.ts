import { auth } from "@/auth";
import { NextResponse } from "next/server";

export default auth((req) => {
  const { pathname } = req.nextUrl;

  // Temporary request logging — remove once production is verified stable
  if (pathname.startsWith("/api")) {
    console.log(`[nextjs] ${req.method} ${pathname} uid=${req.auth?.user?.id ?? "anon"}`);
    return NextResponse.next();
  }

  const isLoggedIn = !!req.auth;

  if (isLoggedIn && pathname === "/login") {
    return NextResponse.redirect(new URL("/", req.url));
  }

  const isPublic = pathname === "/" || pathname === "/login";
  if (!isLoggedIn && !isPublic) {
    return NextResponse.redirect(new URL("/login", req.url));
  }
});

export const config = {
  matcher: ["/((?!_next/static|_next/image|favicon.ico).*)"],
};
