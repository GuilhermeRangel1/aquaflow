import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AquaFlow | Consumo de água",
  description: "Acompanhe o consumo de água da sua propriedade com clareza.",
};

export default function RootLayout({ children }: LayoutProps<"/">) {
  return (
    <html
      lang="pt-BR"
      className="h-full antialiased"
    >
      <body className="min-h-full flex flex-col">{children}</body>
    </html>
  );
}
