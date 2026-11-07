import type { Conversation, Message } from "./types.js";
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
    : (parsed?.data?.records ?? parsed?.records);
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
      typeof record?.conversation_id !== "string" ||
      !record.conversation_id.trim()
    )
      fail("нет conversation_id.");
    const id = record.conversation_id.trim();
    if (ids.has(id)) fail(`ID «${id}» повторяется в файле.`);
    ids.add(id);
    if (!["RU", "KZ", "EN"].includes(record.language))
      fail("language должен быть RU, KZ или EN.");
    if (!["agent chat", "voice call"].includes(record.channel))
      fail("channel должен быть agent chat или voice call.");
    if (!Array.isArray(record.transcript) || !record.transcript.length)
      fail("transcript должен содержать хотя бы одну реплику.");
    const transcript: Message[] = record.transcript.map(
      (
        m: { text: unknown; timestamp: unknown; speaker: string },
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
          timestamp: m.timestamp as string,
          speaker: m.speaker as Message["speaker"],
          text: m.text as string,
        };
      },
    );
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
      channel: record.channel,
      language: record.language,
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
