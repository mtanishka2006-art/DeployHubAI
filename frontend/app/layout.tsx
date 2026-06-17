import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "@/components/auth-provider";
import { LoginGate } from "@/components/login-gate";
import { AppShell } from "@/components/app-shell";

export const metadata: Metadata = {
  title: "DeployHub AI — Mission Control",
  description: "AI infrastructure observability and incident mission control",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className="dark">
      <body className="min-h-screen antialiased">
        <AuthProvider>
          <LoginGate>
            <AppShell>{children}</AppShell>
          </LoginGate>
        </AuthProvider>
      </body>
    </html>
  );
}
