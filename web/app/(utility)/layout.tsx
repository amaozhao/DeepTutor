import AuthGate from "@/components/auth/AuthGate";
import UtilitySidebar from "@/components/sidebar/UtilitySidebar";

export default function UtilityLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <AuthGate>
      <div className="flex h-screen overflow-hidden">
        <UtilitySidebar />
        <main className="flex-1 overflow-hidden bg-[var(--background)]">
          {children}
        </main>
      </div>
    </AuthGate>
  );
}
