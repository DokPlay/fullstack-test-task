import type { Metadata } from "next";
import { IBM_Plex_Mono, Manrope } from "next/font/google";

import "bootstrap/dist/css/bootstrap.min.css";
import "./globals.css";

const manrope = Manrope({
  subsets: ["latin", "cyrillic"],
  variable: "--font-sans",
});

const ibmPlexMono = IBM_Plex_Mono({
  subsets: ["latin", "cyrillic"],
  variable: "--font-mono",
  weight: ["400", "500"],
});

export const metadata: Metadata = {
  title: "Тестовое задание Fullstack",
  description: "Панель управления загрузкой файлов, статусами обработки и алертами.",
  icons: {
    icon: "/favicon.ico",
    shortcut: "/favicon.ico",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="ru">
      <body className={`${manrope.variable} ${ibmPlexMono.variable} app-shell`}>
        {children}
      </body>
    </html>
  );
}
