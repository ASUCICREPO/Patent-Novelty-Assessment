import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Enable static export for AWS Amplify deployment
  output: 'export',
  trailingSlash: true,
  images: {
    unoptimized: true
  }
};

export default nextConfig;
