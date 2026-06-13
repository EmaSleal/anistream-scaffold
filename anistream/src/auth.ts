import NextAuth from "next-auth";
import Google from "next-auth/providers/google";

const FLASK_URL = process.env.FLASK_URL ?? "http://localhost:5000";

export const { handlers, signIn, signOut, auth } = NextAuth({
  trustHost: true,
  providers: [Google],
  pages: { signIn: "/login" },
  callbacks: {
    async signIn({ user, account }) {
      if (account?.provider === "google" && account.providerAccountId && user.email) {
        const res = await fetch(`${FLASK_URL}/api/auth/sync-user`, {
          method: "POST",
          headers: {
            "Content-Type": "application/json",
            "X-Service-Key": process.env.SERVICE_SECRET!,
          },
          body: JSON.stringify({
            id: account.providerAccountId,
            email: user.email,
            name: user.name ?? null,
            photo_url: user.image ?? null,
          }),
        });
        if (!res.ok) return false;
      }
      return true;
    },
    async jwt({ token, account }) {
      if (account) {
        token.sub = account.providerAccountId;
        const res = await fetch(
          `${FLASK_URL}/api/auth/role/${account.providerAccountId}`,
          {
            headers: { "X-Service-Key": process.env.SERVICE_SECRET! },
          },
        );
        if (!res.ok) { token.role = "USER"; return token; }
        const { role } = (await res.json()) as { role: string };
        token.role = role ?? "USER";
      }
      return token;
    },
    session({ session, token }) {
      session.user.id = token.sub!;
      session.user.role = (token.role as string) ?? "USER";
      return session;
    },
  },
});
