import type { NextConfig } from "next";

/**
 * 单端口发布适配：生产环境下把前端的 /api/* 反向代理到同机运行的 FastAPI 服务。
 *
 * 背景：本项目是前后端分离结构（Next.js 前端 + FastAPI 后端）。发布环境只暴露
 * 一个公网端口，因此由 Next.js 同时承担静态资源与 API 网关两个角色：
 *   - 浏览器请求同源 /api/*，由 Next.js rewrite 转发到 API_INTERNAL_ORIGIN
 *   - 前端代码全部走相对路径 /api/*，无需感知后端真实地址
 *
 * 本地开发（pnpm dev / pnpm dev:all）不受影响：zsh 下仅在设置了
 * UE_AGENT_SINGLE_PORT=1 时才启用该 rewrite，两个服务仍各自独立监听 3000/8000。
 */
const apiInternalOrigin = process.env.API_INTERNAL_ORIGIN ?? "http://127.0.0.1:8000";
const singlePort = process.env.UE_AGENT_SINGLE_PORT === "1";

const nextConfig: NextConfig = {
  transpilePackages: ["@ue-agent/ui"],
  async rewrites() {
    if (!singlePort) return [];
    return [
      {
        source: "/api/:path*",
        destination: `${apiInternalOrigin}/api/:path*`,
      },
    ];
  },
};

export default nextConfig;
