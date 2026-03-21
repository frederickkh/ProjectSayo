"use client";

import ChatSkeleton from "../components/ChatSkeleton";

export default function Home() {
  return (
    <div className="min-h-screen bg-gradient-to-br from-slate-50 via-blue-50 to-slate-100 dark:from-slate-950 dark:via-blue-950 dark:to-slate-900 p-4 font-sans flex items-center justify-center">
      <div className="w-full max-w-2xl">
        <ChatSkeleton />
      </div>
    </div>
  );
}
