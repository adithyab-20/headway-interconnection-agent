import type { NextConfig } from "next";

// The API (python -m interconnection_agent.api) serves /api; the site proxies to it so the
// browser only ever talks to one origin.
const api = process.env.HEADWAY_API ?? "http://127.0.0.1:8000";

const config: NextConfig = {
  // The browser tests run their own copy beside a developer's, in a folder of their own.
  distDir: process.env.HEADWAY_DIST_DIR ?? ".next",
  async rewrites() {
    return [{ source: "/api/:path*", destination: `${api}/api/:path*` }];
  },
  // Answering a question with the model can take a while. (Writing is started, then checked on.)
  experimental: { proxyTimeout: 300_000 },
};

export default config;
