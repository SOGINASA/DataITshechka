import { getState } from "./state.js";
import { finalValue, normalized, score, formatScore } from "./scoring.js";
import { esc, href, icon, heading, table, uploadButton } from "./ui.js";
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
    heading(
      "РАБОЧЕЕ ПРОСТРАНСТВО",
      "Обзор качества",
      "Диалоги, оценки и задачи проверки в одном месте.",
      uploadButton(),
    ) +
    `<div class="overview-context"><span class="section-kicker">Пульс команды</span><span class="date-label">${icon("calendar", 15)}Демонстрационный набор<span class="context-divider"></span>1–7 ноября 2026</span></div><div class="stats-grid"><section class="stat-card featured"><div class="stat-label">Средняя оценка${icon("shield")}</div><div class="stat-number">${formatScore(average)}<span>/ 100</span></div><div class="stat-bottom"><span class="score-status">${(average ?? 0) >= 85 ? "Хороший уровень" : "Есть точки роста"}</span><span class="mini-meter"><i style="width:${average ?? 0}%"></i></span></div></section><a href="#/dialogues" class="stat-card"><div class="stat-label">Оценено диалогов${icon("check")}</div><div class="stat-number">${assessed.length}<span>из ${conversations.length}</span></div><div class="stat-bottom"><span>${conversations.length - assessed.length} ожидают оценки</span>${icon("external", 17)}</div></a><a href="#/dialogues?status=attention" class="stat-card"><div class="stat-label">Требуют внимания${icon("alert")}</div><div class="stat-number">${attention.length}<span>диалогов</span></div><div class="stat-bottom"><span><i class="tiny-dot amber"></i>Оценка ниже 80</span>${icon("external", 17)}</div></a><a href="#/appeals" class="stat-card"><div class="stat-label">Открытые апелляции${icon("scale")}</div><div class="stat-number">${pending.length}<span>обращения</span></div><div class="stat-bottom"><span>Ожидают вашего решения</span>${icon("external", 17)}</div></a></div><div class="analytics-grid"><section class="panel chart-panel"><div class="panel-heading"><div><h2>Качество обслуживания</h2><p>Средняя оценка по диалогам</p></div><div class="segmented" aria-label="Представление статистики"><button data-action="chart" data-mode="trend" class="active" aria-pressed="true">Динамика</button><button data-action="chart" data-mode="criteria" aria-pressed="false">Критерии</button></div></div><div id="chart-content">${chartView("trend")}</div><div class="chart-footer"><span class="muted">1–7 ноября 2026</span><span class="chart-note">${assessed.length} оценённых диалогов</span></div></section><section class="panel attention-panel"><div class="panel-heading"><div><h2>В фокусе</h2><p>Начните с этих диалогов</p></div><span class="small-counter">${attention.length + pending.length}</span></div><div class="attention-list">${pending
      .slice(0, 1)
      .map((a) => {
        const c = conversations.find((c) => c.id === a.conversationId)!;
        return `<a href="${href("appeals", a.id)}" class="attention-item"><span class="attention-icon amber-bg">${icon("scale")}</span><div><span class="attention-tag">АПЕЛЛЯЦИЯ</span><strong>${esc(c.operator)}</strong><p>Спорная оценка · ${esc(c.id)}</p></div>${icon("external", 16)}</a>`;
      })
      .join("")}${attention
      .slice(0, 2)
      .map(
        (c) =>
          `<a href="${href("dialogues", c.id)}" class="attention-item"><span class="attention-icon sage-bg">${icon("chat")}</span><div><span class="attention-tag">НУЖНА ПРОВЕРКА</span><strong>${esc(c.title)}</strong><p>${esc(c.operator)} · ${formatScore(score(c.evaluations[c.evaluations.length - 1], appeals))} баллов</p></div>${icon("external", 16)}</a>`,
      )
      .join(
        "",
      )}</div><a href="#/appeals" class="panel-bottom-link">Перейти к апелляциям${icon("arrow", 16)}</a></section></div><section class="panel recent-panel"><div class="panel-heading"><div class="heading-inline"><h2>Последние диалоги</h2><span class="small-counter">${conversations.length}</span></div><a href="#/dialogues" class="text-link">Все диалоги${icon("arrow", 15)}</a></div>${table([...conversations].sort((a, b) => new Date(b.date).valueOf() - new Date(a.date).valueOf()).slice(0, 5))}<div class="table-footer"><span>${icon("clock", 14)}Мок-данные для знакомства с интерфейсом</span><span>RU · KZ · EN</span></div></section>`
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
  return `<div class="chart-legend"><span><i class="legend-dot"></i>Общая оценка</span><span><i class="legend-line"></i>Демо-ориентир 85</span></div><svg class="trend-chart" viewBox="0 0 620 238" role="img" aria-label="${esc(series.map((v, i) => `${i + 1} ноября: ${formatScore(v)}`).join(", "))}">${[0, 25, 50, 75, 100].map((v) => `<g><line x1="38" x2="600" y1="${198 - (v / 100) * 160}" y2="${198 - (v / 100) * 160}" stroke="#e9ede8" stroke-dasharray="3 5"/><text x="24" y="${202 - (v / 100) * 160}" text-anchor="end">${v}</text></g>`).join("")}<line x1="38" x2="600" y1="62" y2="62" stroke="#a9b89d" stroke-dasharray="5 5"/>${points.length > 1 ? `<path d="${path} L${points[points.length - 1].x} 198 L${points[0].x} 198 Z" fill="#eaf3e8" opacity=".8"/>` : ""}<path d="${path}" fill="none" stroke="#367c50" stroke-width="2.6" stroke-linejoin="round"/>${points.map((p) => `<circle cx="${p.x}" cy="${p.y}" r="4.5" fill="#fff" stroke="#367c50" stroke-width="2"><title>${p.i + 1} ноября: ${formatScore(p.value)}</title></circle>`).join("")}${series.map((_, i) => `<text x="${44 + i * 90}" y="229" text-anchor="middle">${i + 1} ноя</text>`).join("")}</svg>`;
}
