import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "InsightMesh | Autonomous Event Analytics & Ingestion Engine",
  description: "AI-powered ClickHouse schema inference, DDL generation, and natural language analytics for Atlys.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="bg-slate-950 text-slate-100 min-h-screen flex flex-col antialiased">
        {children}
      </body>
    </html>
  );
}
