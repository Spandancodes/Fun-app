import type { NextConfig } from "next";
const config: NextConfig = process.env.STATIC_EXPORT === "true"
  ? { output: "export", devIndicators: false }
  : {
      devIndicators: false,
      async rewrites() {
        return [
          {
            source: "/api/:path*",
            destination:
              (process.env.BACKEND_URL || "http://127.0.0.1:8000") + "/api/:path*",
          },
        ];
      },
    };
export default config;
