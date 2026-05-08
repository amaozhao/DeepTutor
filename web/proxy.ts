import { NextRequest, NextResponse } from "next/server";

const AUTH_ENABLED = process.env.NEXT_PUBLIC_AUTH_ENABLED === "true";
const LOGIN_PATH = "/login";
const COOKIE_NAME = "dt_token";

export function proxy(req: NextRequest) {
  // Auth is disabled by default, so local development keeps the open workspace.
  if (!AUTH_ENABLED) return NextResponse.next();

  const { pathname } = req.nextUrl;

  if (
    pathname.startsWith(LOGIN_PATH) ||
    pathname.startsWith("/register") ||
    pathname.startsWith("/_next") ||
    pathname.startsWith("/favicon")
  ) {
    return NextResponse.next();
  }

  const token = req.cookies.get(COOKIE_NAME)?.value;

  if (!token) {
    const loginUrl = req.nextUrl.clone();
    loginUrl.pathname = LOGIN_PATH;
    loginUrl.searchParams.set("next", pathname);
    return NextResponse.redirect(loginUrl);
  }

  return NextResponse.next();
}

export const config = {
  matcher: ["/((?!api|_next/static|_next/image|favicon.ico).*)"],
};
