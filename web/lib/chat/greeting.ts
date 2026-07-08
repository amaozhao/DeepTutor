const FALLBACK_GREETING = "What would you like to learn?";

export function chatGreetingForHour(
  hour: number,
  random: () => number = Math.random,
): string {
  let bucket: string[];
  if (hour >= 5 && hour < 12) {
    bucket = [
      "Good morning.",
      "Morning — let's learn something.",
      FALLBACK_GREETING,
    ];
  } else if (hour >= 12 && hour < 17) {
    bucket = [
      "Good afternoon.",
      "Afternoon — what's on your mind?",
      FALLBACK_GREETING,
    ];
  } else if (hour >= 17 && hour < 22) {
    bucket = [
      "Good evening.",
      "Evening — what shall we explore?",
      FALLBACK_GREETING,
    ];
  } else {
    bucket = ["It's late today.", "Burning the midnight oil?", FALLBACK_GREETING];
  }
  return bucket[Math.floor(random() * bucket.length)];
}

export function currentChatGreeting(): string {
  return chatGreetingForHour(new Date().getHours());
}
