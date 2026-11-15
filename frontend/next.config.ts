import type { NextConfig } from "next";
import path from "node:path";

const nextConfig: NextConfig = {
  // Keep production verification separate from an active development server.
  distDir: process.env.PHOENIX_BUILD_DIR || ".next",
  cacheComponents: true,
  partialPrefetching: true,
  async rewrites() {
    const api = (process.env.PHOENIX_API_URL || "http://localhost:8000").replace(/\/$/, "");
    return [{ source: "/api/:path*", destination: `${api}/:path*` }];
  },
  turbopack: {
    // Pin the project root to this folder so a stray lockfile elsewhere (e.g. ~/package-lock.json) is ignored quietly.
    root: path.resolve(__dirname),
  },
};

export default nextConfig;
