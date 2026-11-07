import { getState } from "./state.js";
import { finalValue, normalized, score, formatScore } from "./scoring.js";
import { esc, href, icon, heading, table, uploadButton, brandArt } from "./ui.js";
export function overviewView() {
  const { conversations, appeals } = getState();
  const assessed = conversations.filter((c) => c.evaluations.length);
  const scores = assessed
    .map((c) => score(c.evaluations[c.evaluations.length - 1], appeals))
    .filter((v): v is number => v !== null);
  const average = scores.length
    ? scores.reduce((a, b) => a + b, 0) / scores.length
    : null;
  const attention = conversations.filter((c) => {
    const value = score(c.evaluations[c.evaluations.length - 1], appeals);
    return value !== null && value < 80;
  });
  const pending = appeals.filter((a) => a.status === "open");
  return (
    heading("", "Обзор", "", uploadButton()) +
    `
    <div class="stats-strip" aria-label="Сводка качества">
      <div class="stat-item stat-primary"><span>Средняя оценка</span><strong>${formatScore(average)}<small> / 100</small></strong><span class="stat-meter" aria-hidden="true"><i style="width:${average ?? 0}%"></i></span></div>
      <a class="stat-item" href="#/dialogues">${brandArt("checklist")}<span>Оценено диалогов</span><strong>${assessed.length}<small> из ${conversations.length}</small></strong></a>
      <a class="stat-item stat-attention" href="#/dialogues?status=attention">${brandArt("dialogues")}<span>Ниже 80 баллов</span><strong>${attention.length}</strong></a>
      <a class="stat-item" href="#/appeals">${brandArt("appeals")}<span>Открытые апелляции</span><strong>${pending.length}</strong></a>
    </div>
    <div class="overview-workspace">
      <section class="panel recent-panel"><div class="panel-heading"><h2>Последние диалоги</h2><a href="#/dialogues" class="text-link">Все ${conversations.length}${icon("arrow", 17)}</a></div>${table([...conversations].sort((a, b) => new Date(b.date).valueOf() - new Date(a.date).valueOf()).slice(0, 6))}</section>
      <aside class="overview-side"><section class="panel appeals-queue"><div class="panel-heading"><h2>Апелляции</h2><span class="small-counter">${pending.length}</span></div><div class="queue-items">${
        pending
          .slice(0, 4)
          .map((a) => {
            const c = conversations.find((c) => c.id === a.conversationId)!;
            const e = c.evaluations.find((e) => e.id === a.evaluationId)!;
            const criterion = e.checklist.criteria.find(
              (cr) => cr.id === a.criterionId,
            )!;
            return `<a href="${href("appeals", a.id)}" class="queue-item"><div><strong>${esc(criterion.name)}</strong><span>${esc(c.operator)}</span></div>${icon("chevron", 18)}</a>`;
          })
          .join("") || '<p class="queue-empty">Нет открытых апелляций</p>'
      }</div><a href="#/appeals" class="panel-bottom-link">Все апелляции${icon("arrow", 17)}</a></section><section class="pending-tile"><img src="./assets/media/headset-editorial.jpg" alt="Гарнитура и блокнот на рабочем столе" width="160" height="160"><div><strong>${conversations.length - assessed.length} диалога ждут оценки</strong><a class="text-link" href="#/dialogues?status=pending">Открыть${icon("arrow", 17)}</a></div></section></aside>
    </div>
    <details class="statistics-fold"><summary><span>Статистика</span><span class="muted">1–7 ноября 2026</span>${icon("down", 18)}</summary><div class="statistics-content"><div class="segmented" aria-label="Представление статистики"><button data-action="chart" data-mode="trend" class="active" aria-pressed="true">Динамика</button><button data-action="chart" data-mode="criteria" aria-pressed="false">Критерии</button></div><div id="chart-content">${chartView("trend")}</div></div></details>`
  );
}
export function chartView(mode: string) {
  const { conversations, appeals } = getState();
  if (mode === "criteria") {
    const latest = conversations
      .find((c) => c.evaluations.length)
      ?.evaluations.slice(-1)[0];
    return `<div class="criteria-bars">${
      latest?.checklist.criteria
        .filter((c) => c.type !== "flag")
        .slice(0, 5)
        .map((criterion) => {
          const values = conversations.flatMap((c) => {
            const e = c.evaluations[c.evaluations.length - 1];
            const config = e?.checklist.criteria.find(
              (x) => x.id === criterion.id,
            );
            const value = e ? finalValue(e, criterion.id, appeals) : null;
            return value !== null && config
              ? [normalized(value, config) * 100]
              : [];
          });
          const value = values.length
            ? values.reduce((a, b) => a + b, 0) / values.length
            : 0;
          return `<div><div><span>${esc(criterion.name)}</span><strong>${formatScore(value)}<small> / 100</small></strong></div><span class="bar-track"><i style="width:${value}%"></i></span></div>`;
        })
        .join("") || ""
    }</div>`;
  }
  const series = Array.from({ length: 7 }, (_, i) => {
    const values = conversations
      .filter((c) => c.date.startsWith(`2026-11-0${i + 1}`))
      .map((c) => score(c.evaluations[c.evaluations.length - 1], appeals))
      .filter((v): v is number => v !== null);
    return values.length
      ? values.reduce((a, b) => a + b, 0) / values.length
      : null;
  });
  const points = series.flatMap((value, i) =>
    value === null
      ? []
      : [{ x: 44 + i * 90, y: 198 - (value / 100) * 160, value, i }],
  );
  const path = points.map((p, i) => `${i ? "L" : "M"}${p.x} ${p.y}`).join(" ");
  return `<div class="chart-legend"><span><i class="legend-dot"></i>Общая оценка</span></div><svg class="trend-chart" viewBox="0 0 620 238" role="img" aria-label="${esc(series.map((v, i) => `${i + 1} ноября: ${formatScore(v)}`).join(", "))}">${[0, 25, 50, 75, 100].map((v) => `<g><line x1="38" x2="600" y1="${198 - (v / 100) * 160}" y2="${198 - (v / 100) * 160}" stroke="#e9ede8" stroke-dasharray="3 5"/><text x="24" y="${202 - (v / 100) * 160}" text-anchor="end">${v}</text></g>`).join("")}${points.length > 1 ? `<path d="${path} L${points[points.length - 1].x} 198 L${points[0].x} 198 Z" fill="#eaf3e8" opacity=".8"/>` : ""}<path d="${path}" fill="none" stroke="#367c50" stroke-width="2.6" stroke-linejoin="round"/>${points.map((p) => `<circle cx="${p.x}" cy="${p.y}" r="4.5" fill="#fff" stroke="#367c50" stroke-width="2"><title>${p.i + 1} ноября: ${formatScore(p.value)}</title></circle>`).join("")}${series.map((_, i) => `<text x="${44 + i * 90}" y="229" text-anchor="middle">${i + 1} ноя</text>`).join("")}</svg>`;
}
