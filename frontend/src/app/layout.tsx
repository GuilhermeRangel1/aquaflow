import type { Metadata } from "next";
import "./globals.css";
import "./dashboard/dashboard.css";
import { ThemeProvider } from "./theme-provider";

export const metadata: Metadata = {
  title: "aquaflow",
  description: "Acompanhe o consumo de água da sua propriedade com clareza.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="pt-BR"
      className="h-full antialiased"
    >
      <body className="min-h-full flex flex-col"><ThemeProvider>{children}</ThemeProvider></body>
    </html>
  );
}
