/**
 * Mint a short-lived HS256 JWT for Flask consumption.
 *
 * Auth mechanism A2:
 *   1. Next.js route handlers call getToken({ req, secret: process.env.AUTH_SECRET })
 *      from "next-auth/jwt" to decode the Auth.js v5 JWE-encrypted session token.
 *   2. This function re-signs the user identity as a plain HS256 JWT (60s TTL)
 *      that Flask can verify with PyJWT using INTERNAL_JWT_SECRET.
 *
 * Required environment variables (server-side only):
 *   - AUTH_SECRET      — already set; used by getToken() to decrypt the JWE
 *   - INTERNAL_JWT_SECRET — shared with scraper/.env.local (must be the same value)
 *
 * NOTE: Server Actions do NOT have a `req` object and CANNOT call getToken().
 * Server Actions must fetch same-origin route handlers (e.g. fetch("/api/watchlist"))
 * which handle token minting internally. This function is for route handlers only.
 */

import { SignJWT } from "jose";
import type { JWT } from "next-auth/jwt";

/**
 * Takes a decoded Auth.js JWT payload (already decrypted via getToken)
 * and returns a short-lived HS256 token Flask can validate.
 *
 * @param token  The result of getToken({ req, secret: AUTH_SECRET })
 * @returns      Signed HS256 JWT string (60-second TTL)
 * @throws       If INTERNAL_JWT_SECRET is not configured
 */
export async function mintInternalToken(token: JWT): Promise<string> {
  const secret = process.env.INTERNAL_JWT_SECRET;
  if (!secret) {
    throw new Error(
      "INTERNAL_JWT_SECRET is not set. " +
        "Add it to anistream/.env.local (must match scraper/.env.local)."
    );
  }

  const encodedSecret = new TextEncoder().encode(secret);

  return new SignJWT({
    sub: token.sub,
    role: (token as JWT & { role?: string }).role ?? "USER",
  })
    .setProtectedHeader({ alg: "HS256" })
    .setExpirationTime("60s")
    .sign(encodedSecret);
}
