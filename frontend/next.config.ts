import type { NextConfig } from "next";
import path from "path";

const backendUrl = process.env.BACKEND_URL || "http://backend:8001";

const nextConfig: NextConfig = {
  output: "standalone",
  async rewrites() {
    return [
      {
        source      : "/api/backend-auth/:path*",
        destination : `${backendUrl}/auth/:path*`,
      },
      {
        source      : "/api/auth/:path*",
        destination : "/api/auth/:path*",
      },
      // Local development does not have nginx's direct SSE proxy routes.
      {
        source      : "/chat",
        destination : `${backendUrl}/chat`,
      },
      {
        source      : "/workflows/:path*",
        destination : `${backendUrl}/workflows/:path*`,
      },
      // The external API keeps its /api/v1 prefix in the backend router.
      {
        source      : "/api/v1/:path*",
        destination : `${backendUrl}/api/v1/:path*`,
      },
      // Exclude file-based API routes that need proper streaming
      {
        source      : "/api/wa/channels/:id/qr",
        destination : "/api/wa/channels/:id/qr",
      },
      {
        source      : "/api/:path*",
        destination : `${backendUrl}/:path*`,
      },
    ];
  },
  turbopack: {
    root: path.join(__dirname, '..'),
  },
  experimental: {
    proxyClientMaxBodySize: '100mb',
    proxyTimeout: 300000,
  },
  httpAgentOptions: {
    keepAlive: true,
  },
};

export default nextConfig;
