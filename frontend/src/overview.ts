import { getState } from "./state.js";
import { formatScore } from "./scoring.js";
import { esc, href, icon, heading, table, uploadButton, brandArt } from "./ui.js";
export function overviewView() {
  const overview = getState().overview;
  if (!overview) return "";
  const {conversations} = getState();
  const {average, total, assessed, attention, open_appeals: pending} = overview;
  return (
    heading("", "Обзор", "", uploadButton()) +
    `
    <div class="stats-strip" aria-label="Сводка качества">
      <div class="stat-item stat-primary"><span>Средняя оценка</span><strong>${formatScore(average)}<small> / 100</small></strong><span class="stat-meter" aria-hidden="true"><i style="width:${average ?? 0}%"></i></span></div>
      <a class="stat-item" href="#/dialogues">${brandArt("checklist")}<span>Оценено диалогов</span><strong>${assessed}<small> из ${total}</small></strong></a>
      <a class="stat-item stat-attention" href="#/dialogues?status=attention">${brandArt("dialogues")}<span>Ниже 80 баллов</span><strong>${attention}</strong></a>
      <a class="stat-item" href="#/appeals">${brandArt("appeals")}<span>Открытые апелляции</span><strong>${pending}</strong></a>
    </div>
    <div class="overview-workspace">
      <section class="panel recent-panel"><div class="panel-heading"><h2>Последние диалоги</h2><a href="#/dialogues" class="text-link">Все ${total}${icon("arrow", 17)}</a></div>${table([...conversations].sort((a, b) => new Date(b.date).valueOf() - new Date(a.date).valueOf()).slice(0, 6))}</section>
      <aside class="overview-side"><section class="panel appeals-queue"><div class="panel-heading"><h2>Апелляции</h2><span class="small-counter">${pending}</span></div><div class="queue-items">${
        overview.appeals
          .map((a) => `<a href="${href("appeals", a.id)}" class="queue-item"><div><strong>${esc(a.criterion_name)}</strong><span>${esc(a.operator_name || "Не указан")}</span></div>${icon("chevron", 18)}</a>`)
          .join("") || '<p class="queue-empty">Нет открытых апелляций</p>'
      }</div><a href="#/appeals" class="panel-bottom-link">Все апелляции${icon("arrow", 17)}</a></section><section class="pending-tile"><img src="./assets/media/headset-editorial.jpg" alt="Гарнитура и блокнот на рабочем столе" width="160" height="160"><div><strong>${total - assessed} диалога ждут оценки</strong><a class="text-link" href="#/dialogues?status=pending">Открыть${icon("arrow", 17)}</a></div></section></aside>
    </div>
    <details class="statistics-fold"><summary><span>Статистика</span><span class="muted">${esc(overview.trend[0]?.date)} — ${esc(overview.trend[overview.trend.length - 1]?.date)}</span>${icon("down", 18)}</summary><div class="statistics-content"><div class="segmented" aria-label="Представление статистики"><button data-action="chart" data-mode="trend" class="active" aria-pressed="true">Динамика</button><button data-action="chart" data-mode="criteria" aria-pressed="false">Критерии</button></div><div id="chart-content">${chartView("trend")}</div></div></details>`
  );
}
export function chartView(mode: string) {
  const overview = getState().overview;
  if (!overview) return "";
  if (mode === "criteria") {
    return `<div class="criteria-bars">${overview.criteria.map(({name, value}) =>
      `<div><div><span>${esc(name)}</span><strong>${formatScore(value)}<small> / 100</small></strong></div><span class="bar-track"><i style="width:${value ?? 0}%"></i></span></div>`).join("")}</div>`;
  }
  const dayLabel = (i: number) => new Date(overview.trend[i].date + "T12:00:00+05:00").toLocaleDateString("ru-RU", {day: "numeric", month: "short", timeZone: "Asia/Almaty"});
  const series = overview.trend.map(day => day.value);
  const points = series.flatMap((value, i) =>
    value === null
      ? []
      : [{ x: 44 + i * 90, y: 198 - (value / 100) * 160, value, i }],
  );
  const path = points.map((p, i) => `${i ? "L" : "M"}${p.x} ${p.y}`).join(" ");
  return `<div class="chart-legend"><span><i class="legend-dot"></i>Общая оценка</span></div><svg class="trend-chart" viewBox="0 0 620 238" role="img" aria-label="${esc(series.map((v, i) => `${dayLabel(i)}: ${formatScore(v)}`).join(", "))}">${[0, 25, 50, 75, 100].map((v) => `<g><line x1="38" x2="600" y1="${198 - (v / 100) * 160}" y2="${198 - (v / 100) * 160}" stroke="#e9ede8" stroke-dasharray="3 5"/><text x="24" y="${202 - (v / 100) * 160}" text-anchor="end">${v}</text></g>`).join("")}${points.length > 1 ? `<path d="${path} L${points[points.length - 1].x} 198 L${points[0].x} 198 Z" fill="#eaf3e8" opacity=".8"/>` : ""}<path d="${path}" fill="none" stroke="#367c50" stroke-width="2.6" stroke-linejoin="round"/>${points.map((p) => `<circle cx="${p.x}" cy="${p.y}" r="4.5" fill="#fff" stroke="#367c50" stroke-width="2"><title>${esc(dayLabel(p.i))}: ${formatScore(p.value)}</title></circle>`).join("")}${series.map((_, i) => `<text x="${44 + i * 90}" y="229" text-anchor="middle">${esc(dayLabel(i))}</text>`).join("")}</svg>`;
}
