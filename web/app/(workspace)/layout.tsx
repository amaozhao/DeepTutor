import AuthGate from "@/components/auth/AuthGate";
import WorkspaceSidebar from "@/components/sidebar/WorkspaceSidebar";
import { UnifiedChatProvider } from "@/context/UnifiedChatContext";

export default function WorkspaceLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <AuthGate>
      <UnifiedChatProvider>
        <div className="flex h-screen overflow-hidden">
          <WorkspaceSidebar />
          <main className="flex-1 overflow-hidden bg-[var(--background)]">
            {children}
          </main>
        </div>
      </UnifiedChatProvider>
    </AuthGate>
  );
}
