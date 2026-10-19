export function guestStatus(ai = false) {
  return {
    token: "offline-guest-token", csrf_token: "offline-guest-csrf", remaining: 5,
    ai_enabled: ai, ttl_seconds: 600, max_files: 2, max_file_bytes: 2097152,
    max_rows: 1000, max_columns: 20, files: [] as Record<string, unknown>[],
    default_model: "inetcloud-knowledge", gemini_fallback_enabled: false,
    models: [
      { id: "inetcloud-knowledge", label: "Knowledge", provider: "inetcloud", configured: true },
      { id: "gemini", label: "Gemini", provider: "gemini", configured: true },
    ],
  };
}
