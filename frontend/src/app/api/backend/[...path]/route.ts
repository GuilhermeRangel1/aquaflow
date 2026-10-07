import { NextRequest, NextResponse } from "next/server";

type BackendTokens = { access_token: string; refresh_token: string; expires_in: number };
const accessCookie = "aquaflow_access";
const refreshCookie = "aquaflow_refresh";

async function backendUrl(path: string[], search: string) {
  const origin = process.env.AQUAFLOW_API_URL ?? "http://localhost:8000";
  return `${origin}/api/v1/${path.join("/")}${search}`;
}

async function send(url: string, method: string, body: string | undefined, access?: string, deviceKey?: string | null) {
  const headers = new Headers({ "Content-Type": "application/json" });
  if (access) headers.set("Authorization", `Bearer ${access}`);
  if (deviceKey) headers.set("X-Device-Key", deviceKey);
  return fetch(url, { method, headers, body, cache: "no-store" });
}

async function proxy(request: NextRequest, context: { params: Promise<{ path: string[] }> }) {
  const { path } = await context.params;
  if (path[0] !== "auth" && path[0] !== "properties" && path[0] !== "devices" && path[0] !== "ingestion") {
    return NextResponse.json({ code: "not_found", message: "Route not found" }, { status: 404 });
  }

  const url = await backendUrl(path, request.nextUrl.search);
  const method = request.method;
  const body = method === "GET" || method === "HEAD" ? undefined : await request.text();
  const isLogin = path[0] === "auth" && ["login", "register"].includes(path[1] ?? "");
  const isRefresh = path[0] === "auth" && path[1] === "refresh";
  const isLogout = path[0] === "auth" && path[1] === "logout";
  const refresh = request.cookies.get(refreshCookie)?.value;

  let upstream: Response;
  if (isLogout && refresh) {
    upstream = await send(url, method, JSON.stringify({ refresh_token: refresh }), request.cookies.get(accessCookie)?.value);
  } else {
    upstream = await send(url, method, body, request.cookies.get(accessCookie)?.value, request.headers.get("x-device-key"));
  }

  const publicAuth = path[0] === "auth" && ["login", "register", "refresh", "logout"].includes(path[1] ?? "");
  if (upstream.status === 401 && refresh && (!publicAuth || isLogout)) {
    const renewed = await send(await backendUrl(["auth", "refresh"], ""), "POST", JSON.stringify({ refresh_token: refresh }));
    if (renewed.ok) {
      const tokens = (await renewed.json()) as BackendTokens;
      const retryBody = isLogout ? JSON.stringify({ refresh_token: tokens.refresh_token }) : body;
      upstream = await send(url, method, retryBody, tokens.access_token, request.headers.get("x-device-key"));
      const response = await relay(upstream);
      setSessionCookies(response, tokens);
      return response;
    }
  }

  if (upstream.status === 204) {
    const response = new NextResponse(null, { status: 204 });
    if (isLogout) clearSessionCookies(response);
    return response;
  }

  const data = await upstream.json().catch(() => ({ code: "upstream_error", message: "API returned an invalid response" }));
  if (upstream.ok && isLogin) {
    const authData = data as { tokens: BackendTokens; user: unknown };
    const response = NextResponse.json({ user: authData.user }, { status: upstream.status });
    setSessionCookies(response, authData.tokens);
    return response;
  }
  if (upstream.ok && isRefresh) {
    const tokens = data as BackendTokens;
    const response = NextResponse.json({ refreshed: true }, { status: upstream.status });
    setSessionCookies(response, tokens);
    return response;
  }
  if (upstream.ok && isLogout) {
    const response = NextResponse.json(data, { status: upstream.status });
    clearSessionCookies(response);
    return response;
  }
  return NextResponse.json(data, { status: upstream.status });
}

async function relay(upstream: Response) {
  if (upstream.status === 204) return new NextResponse(null, { status: 204 });
  const data = await upstream.json().catch(() => ({ code: "upstream_error", message: "API returned an invalid response" }));
  return NextResponse.json(data, { status: upstream.status });
}

function setSessionCookies(response: NextResponse, tokens: BackendTokens) {
  const secure = process.env.NODE_ENV === "production";
  response.cookies.set(accessCookie, tokens.access_token, {
    httpOnly: true, secure, sameSite: "lax", path: "/", maxAge: tokens.expires_in,
  });
  response.cookies.set(refreshCookie, tokens.refresh_token, {
    httpOnly: true, secure, sameSite: "lax", path: "/", maxAge: 30 * 24 * 60 * 60,
  });
}

function clearSessionCookies(response: NextResponse) {
  response.cookies.delete(accessCookie);
  response.cookies.delete(refreshCookie);
}

export const GET = proxy;
export const POST = proxy;
export const PATCH = proxy;
export const DELETE = proxy;
