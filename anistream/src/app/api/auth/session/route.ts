import { auth } from "@/auth";
import { NextResponse } from "next/server";

export async function GET() {
  const session = await auth();
  if (!session) return NextResponse.json(null);

  // Strip server-only fields before sending to the client.
  // auth() reads the JWT cookie directly so server-side role checks are unaffected.
  // eslint-disable-next-line @typescript-eslint/no-unused-vars
  const { id: _id, role: _role, ...safeUser } = session.user;
  return NextResponse.json({ user: safeUser, expires: session.expires });
}
