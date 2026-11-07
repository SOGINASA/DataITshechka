import type { Conversation, Message } from "./types.js";

export function detectLanguage(text: string): Conversation["language"] {
  const normalized = text.toLocaleLowerCase();
  if (/[әғқңөұүһәі]/i.test(normalized)) return "KZ";
  const tokens = normalized.match(/[\p{L}]+/gu) || [];
  const kazakh = new Set(["иә", "сіз", "сізге", "маған", "қайда", "қалай", "үшін", "және", "рақмет", "өтінім", "өшірдім", "қосыңызшы"]);
  if (tokens.some((token) => kazakh.has(token))) return "KZ";
  if (/[а-яё]/i.test(normalized)) return "RU";
  if (/[a-z]/i.test(normalized)) return "EN";
  return "RU";
}

export function parseImport(raw: string): Conversation[] {
  let parsed: any;
  try {
    parsed = JSON.parse(raw);
  } catch {
    throw new Error(
      "Не удалось прочитать JSON. Проверьте скобки и кавычки в файле.",
    );
  }
  const records = Array.isArray(parsed)
    ? parsed
    : (parsed?.messages || parsed?.transcript ? [parsed] : parsed?.data?.records ?? parsed?.records);
  if (!Array.isArray(records) || records.length === 0)
    throw new Error(
      "Нужен непустой массив записей или ответ API с полем data.records.",
    );
  if (records.length > 100)
    throw new Error("За один раз можно добавить до 100 диалогов.");
  const ids = new Set();
  return records.map((record, index) => {
    const fail = (detail: string): never => {
      throw new Error(`Запись ${index + 1}: ${detail}`);
    };
    if (
      typeof (record?.conversation_id ?? record?.external_id) !== "string" ||
      !(record.conversation_id ?? record.external_id).trim()
    )
      fail("нет conversation_id.");
    const id = (record.conversation_id ?? record.external_id).trim();
    if (ids.has(id)) fail(`ID «${id}» повторяется в файле.`);
    ids.add(id);
    const channel = ({chat: "agent chat", call: "voice call"} as Record<string, Conversation["channel"]>)[record.channel] || record.channel;
    if (!["agent chat", "voice call"].includes(channel))
      fail("channel должен быть chat, call, agent chat или voice call.");
    const messages = record.transcript ?? record.messages;
    if (!Array.isArray(messages) || !messages.length)
      fail("transcript или messages должны содержать хотя бы одну реплику.");
    const transcript: Message[] = messages.map(
      (
        m: { id?: unknown; text: unknown; timestamp: unknown; speaker: string },
        i: number,
      ) => {
        if (
          !m ||
          typeof m.text !== "string" ||
          !m.text.trim() ||
          typeof m.timestamp !== "string" ||
          !["client", "operator", "bot", "system"].includes(m.speaker)
        )
          fail(`проверьте timestamp, speaker и text у реплики ${i + 1}.`);
        return {
          ...(typeof m.id === "string" ? {id: m.id} : {}),
          timestamp: m.timestamp as string,
          speaker: m.speaker as Message["speaker"],
          text: m.text as string,
        };
      },
    );
    const normalizedLanguage = ({ru: "RU", kk: "KZ", kz: "KZ", en: "EN"} as Record<string, Conversation["language"]>)[String(record.language || "").toLowerCase()];
    const language = normalizedLanguage
      ? normalizedLanguage
      : [undefined, null, "", "auto"].includes(record.language)
        ? detectLanguage(transcript.map((message) => message.text).join(" "))
        : fail("language должен быть RU, KZ, EN или отсутствовать для автоопределения.");
    let audioUrl: string | null = null;
    if (typeof record.audio_url === "string" && record.audio_url.trim()) {
      try {
        const url = new URL(record.audio_url);
        if (url.protocol !== "https:" && url.protocol !== "http:")
          fail("audio_url должен быть HTTP(S)-ссылкой.");
        audioUrl = url.href;
      } catch {
        fail("некорректная ссылка audio_url.");
      }
    }
    return {
      id,
      title:
        typeof record.title === "string" ? record.title : "Загруженный диалог",
      operator:
        typeof record.operator === "string" ? record.operator : "Оператор",
      channel,
      language,
      date: new Date().toISOString(),
      duration: "—",
      transcript,
      audioUrl,
      evaluations: [],
    };
  });
}
export const importExample = JSON.stringify(
  [
    {
      conversation_id: "new-ru-001",
      channel: "agent chat",
      language: "RU",
      transcript: [
        {
          timestamp: "00:00",
          speaker: "client",
          text: "Здравствуйте! Как получить отчёт по счёту?",
        },
        {
          timestamp: "00:12",
          speaker: "operator",
          text: "Здравствуйте! Отчёт можно скачать в личном кабинете в разделе «Документы».",
        },
      ],
      audio_url: null,
    },
  ],
  null,
  2,
);
