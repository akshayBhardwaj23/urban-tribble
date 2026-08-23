import type { JWT } from "next-auth/jwt";
import CredentialsProvider from "next-auth/providers/credentials";
import GoogleProvider from "next-auth/providers/google";
import { accessTokenExpiresAt } from "@/lib/access-token";
import { resolveApiBase } from "@/lib/api-base";

const API_BASE = resolveApiBase();

/** Re-mint the API token this long before it expires, so live pages never see a 401. */
const REFRESH_BEFORE_EXPIRY_MS = 10 * 60 * 1000;

/** A hung backend must not hang every session read. */
const BOOTSTRAP_TIMEOUT_MS = 10_000;

/** How long a signed-in browser keeps its session cookie without any activity. */
const SESSION_MAX_AGE_SECONDS = 30 * 24 * 60 * 60;

const INTERNAL_AUTH_SECRET = (() => {
  const configured = process.env.INTERNAL_AUTH_SECRET?.trim();
  if (configured) return configured;
  if (process.env.NODE_ENV === "production") {
    throw new Error(
      "INTERNAL_AUTH_SECRET is not set. Set it to match the backend before building for production."
    );
  }
  return "dev-internal-auth-secret-change-in-production";
})();

type SignInUser = {
  id: string;
  email: string;
  name?: string | null;
  image?: string | null;
  accessToken?: string;
};

type BootstrapResponse = {
  id: string;
  email: string;
  name: string | null;
  image: string | null;
  access_token: string;
};

async function bootstrapAccessToken(user: {
  email: string;
  name?: string | null;
  image?: string | null;
}): Promise<BootstrapResponse | null> {
  try {
    const res = await fetch(`${API_BASE}/api/auth/bootstrap`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Internal-Auth-Secret": INTERNAL_AUTH_SECRET,
      },
      body: JSON.stringify({
        email: user.email,
        name: user.name ?? null,
        image: user.image ?? null,
      }),
      signal: AbortSignal.timeout(BOOTSTRAP_TIMEOUT_MS),
    });
    if (!res.ok) return null;
    return (await res.json()) as BootstrapResponse;
  } catch {
    return null;
  }
}

function applyBootstrap(token: JWT, boot: BootstrapResponse): JWT {
  token.sub = boot.id;
  token.accessToken = boot.access_token;
  token.accessTokenExpires = accessTokenExpiresAt(boot.access_token) ?? undefined;
  token.email = boot.email;
  token.name = boot.name;
  token.picture = boot.image;
  delete token.error;
  return token;
}

/** Drop the API token and tell the browser to sign in again. */
function expireSession(token: JWT): JWT {
  delete token.accessToken;
  delete token.accessTokenExpires;
  token.error = "SessionExpired";
  return token;
}

/**
 * Keep the API token alive for as long as the NextAuth session lasts.
 *
 * The API token expires in hours while the session cookie lasts weeks, so
 * without this a still-signed-in browser would 401 on every call. Runs on each
 * session read and re-mints server-to-server once the token nears its expiry.
 */
async function refreshApiAccessToken(token: JWT): Promise<JWT> {
  // Sessions issued before `accessTokenExpires` existed fall back to the token.
  const expiresAt =
    typeof token.accessTokenExpires === "number"
      ? token.accessTokenExpires
      : accessTokenExpiresAt(token.accessToken);
  const now = Date.now();

  if (token.accessToken && expiresAt && now < expiresAt - REFRESH_BEFORE_EXPIRY_MS) {
    token.accessTokenExpires = expiresAt;
    return token;
  }

  const email = typeof token.email === "string" ? token.email.trim() : "";
  if (!email) return expireSession(token);

  const boot = await bootstrapAccessToken({
    email,
    name: token.name,
    image: token.picture,
  });
  if (boot?.access_token) return applyBootstrap(token, boot);

  // Backend unreachable but the current token still has life in it: keep using
  // it rather than signing the user out over a blip.
  if (token.accessToken && expiresAt && now < expiresAt) {
    token.accessTokenExpires = expiresAt;
    return token;
  }
  return expireSession(token);
}

export const authOptions = {
  providers: [
    GoogleProvider({
      clientId: process.env.GOOGLE_CLIENT_ID ?? "",
      clientSecret: process.env.GOOGLE_CLIENT_SECRET ?? "",
    }),
    CredentialsProvider({
      id: "test-login",
      name: "Test login",
      credentials: {
        email: { label: "Email", type: "email" },
        secret: { label: "Internal key", type: "password" },
      },
      async authorize(credentials) {
        const email = credentials?.email?.trim();
        if (!email) return null;
        const secret = (credentials?.secret as string | undefined) ?? "";

        try {
          const res = await fetch(`${API_BASE}/api/auth/test-login`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ email, secret }),
          });
          if (!res.ok) return null;
          const u = (await res.json()) as {
            id: string;
            email: string;
            name: string | null;
            image: string | null;
            access_token: string;
          };
          return {
            id: u.id,
            email: u.email,
            name: u.name ?? undefined,
            image: u.image ?? undefined,
            accessToken: u.access_token,
          };
        } catch {
          return null;
        }
      },
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
            access_token: string;
          };
          return {
            id: u.id,
            email: u.email,
            name: u.name ?? undefined,
            image: u.image ?? undefined,
            accessToken: u.access_token,
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
        if (process.env.NODE_ENV === "production") return null;
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
  session: { strategy: "jwt" as const, maxAge: SESSION_MAX_AGE_SECONDS },
  pages: {
    signIn: "/login",
  },
  callbacks: {
    async jwt({ token, user }: { token: JWT; user?: SignInUser }) {
      if (!user) {
        // Every later session read: renew the API token before it lapses.
        return refreshApiAccessToken(token);
      }

      token.email = user.email;
      token.name = user.name;
      token.picture = user.image;
      delete token.error;

      if (user.accessToken) {
        token.sub = user.id;
        token.accessToken = user.accessToken;
        token.accessTokenExpires =
          accessTokenExpiresAt(user.accessToken) ?? undefined;
        return token;
      }

      if (user.email) {
        // Google OAuth / dev-bypass: mint a FastAPI token server-side.
        const boot = await bootstrapAccessToken({
          email: user.email,
          name: user.name,
          image: user.image,
        });
        if (boot?.access_token) return applyBootstrap(token, boot);
      }
      return token;
    },
    async session({
      session,
      token,
    }: {
      session: {
        user?: {
          email?: string | null;
          name?: string | null;
          image?: string | null;
        };
        accessToken?: string;
        error?: "SessionExpired";
      };
      token: JWT;
    }) {
      if (session.user) {
        session.user.email = (token.email as string) ?? "";
        session.user.name = token.name as string | null | undefined;
        session.user.image = token.picture as string | null | undefined;
      }
      session.accessToken = token.accessToken;
      session.error = token.error;
      return session;
    },
  },
};
