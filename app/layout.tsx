import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "广告素材体验分析与策略建议助手",
  description: "基于公开规则、合成数据和用户输入的广告体验分析个人作品。",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="zh-CN">
      <body>{children}</body>
    </html>
  );
}
