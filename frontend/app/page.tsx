"use client";

import Image from "next/image";
import ChatSkeleton from "../components/ChatSkeleton";

export default function Home() {
  return (
    <div className="flex min-h-[auto] flex-col items-center justify-center bg-background p-4 font-sans dark:bg-black">
      {/* Header with logos */}
      <header className="mb-8 flex items-center gap-4">
        <Image
          className="dark:invert"
          src="/next.svg"
          alt="Next.js logo"
          width={50}
          height={20}
          priority
        />
        <Image
          className="dark:invert"
          src="/vercel.svg"
          alt="Vercel logo"
          width={50}
          height={20}
          priority
        />
      </header>

      {/* Intro text */}
      <section className="flex flex-col items-center gap-6 text-center sm:items-start sm:text-left mb-8">
        <h1 className="max-w-xs text-3xl font-semibold leading-10 tracking-tight text-black dark:text-zinc-50">
          Internal Chatbot For Teachers.
        </h1>
        <p className="max-w-md text-lg leading-8 text-zinc-600 dark:text-zinc-400">
          Looking for help? Try typing into the chat below!
        </p>
      </section>

      {/* Links/buttons */}
      
      {/* Chat Skeleton */}
      <section className="w-full max-w-2xl mx-auto">
        <ChatSkeleton />
      </section>
    </div>
  );
}
