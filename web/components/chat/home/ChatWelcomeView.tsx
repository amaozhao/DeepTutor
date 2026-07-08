"use client";

interface ChatWelcomeViewProps {
  greeting: string;
}

export default function ChatWelcomeView({ greeting }: ChatWelcomeViewProps) {
  return (
    <div className="flex flex-1 min-h-0 flex-col items-center justify-end pb-14 animate-fade-in">
      <div className="flex items-center justify-center gap-4">
        <img
          src="/logo_black.png"
          alt="DeepTutor"
          width={40}
          height={40}
          className="h-10 w-10 select-none"
          draggable={false}
        />
        <h1 className="font-serif text-[40px] font-medium leading-[1.1] tracking-[-0.015em] text-[var(--foreground)]">
          {greeting}
        </h1>
      </div>
    </div>
  );
}
