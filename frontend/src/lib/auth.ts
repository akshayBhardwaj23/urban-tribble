import type { JWT } from "next-auth/jwt";
import CredentialsProvider from "next-auth/providers/credentials";
import GoogleProvider from "next-auth/providers/google";

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

type SignInUser = {
  id: string;
  email: string;
  name?: string | null;
  image?: string | null;
};

export const authOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID ?? "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "",
    }),
    CredentialsProvider({
      id: "email-otp",
      name: "Email OTP",
      credentials: {
        email: { label: "Email", type: "email" },
        code: { label: "Code", type: "text" },
      },
      async authorize(credentials) {
        const email = credentials?.email?.trim();
        const code = credentials?.code?.trim();
        if (!email || !code) return null;

        try {
          const res = await fetch(`${API_BASE}/api/auth/otp/verify`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, code }),
          });
          if (!res.ok) return null;
          const u = (await res.json()) as {
            id: string;
            email: string;
            name: string | null;
            image: string | null;
          };
          return {
            id: u.id,
            email: u.email,
            name: u.name ?? undefined,
            image: u.image ?? undefined,
          };
        } catch {
          return null;
        }
      },
    }),
    CredentialsProvider({
      id: "dev-bypass",
      name: "Dev bypass",
      credentials: {},
      authorize() {
        if (process.env.AUTH_BYPASS !== "true") return null;
        const email =
          process.env.AUTH_BYPASS_EMAIL?.trim().toLowerCase() ||
          "dev-bypass@local.test";
        const name = process.env.AUTH_BYPASS_NAME || "Dev User";
        return {
          id: `bypass:${email}`,
          email,
          name,
          image: undefined,
        };
      },
    }),
  ],
  session: { strategy: "jwt" as const },
  pages: {
    signIn: "/login",
  },
  callbacks: {
    async jwt({ token, user }: { token: JWT; user?: SignInUser }) {
      if (user) {
        token.sub = user.id;
        token.email = user.email;
        token.name = user.name;
        token.picture = user.image;
      }
      return token;
    },
    async session({
      session,
      token,
    }: {
      session: { user?: { email?: string | null; name?: string | null; image?: string | null } };
      token: JWT;
    }) {
      if (session.user) {
        session.user.email = (token.email as string) ?? "";
        session.user.name = token.name as string | null | undefined;
        session.user.image = token.picture as string | null | undefined;
      }
      return session;
    },
  },
};
