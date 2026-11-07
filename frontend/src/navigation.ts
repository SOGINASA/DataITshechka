import { icon } from "./ui.js";

export const navItems = [
  { id: "overview", label: "Обзор", icon: "dashboard" },
  { id: "dialogues", label: "Диалоги", icon: "chat" },
  { id: "checklists", label: "Чек-листы", icon: "checklist" },
  { id: "appeals", label: "Апелляции", icon: "scale" },
];

export function mobileHeader(section: string, detail: boolean) {
  if (detail && (section === "dialogues" || section === "appeals")) {
    const label = section === "dialogues" ? "Диалоги" : "Апелляции";
    return `<a class="mobile-brand mobile-back" href="#/${section}" aria-label="Назад: ${label}">${icon("back", 21)}<span>${label}</span></a>`;
  }
  return '<a class="mobile-brand" href="#/overview" aria-label="Freedom CQA — обзор"><img src="./assets/brand/freedom-logo.svg" alt="Freedom"><span>CQA</span></a>';
}

let viewportReady = false;
function watchKeyboard() {
  if (viewportReady) return;
  viewportReady = true;
  let restingHeight = window.innerHeight;
  const sync = () => {
    const viewport = window.visualViewport;
    const height = viewport?.height ?? window.innerHeight;
    const focused = document.activeElement;
    const editing = focused instanceof HTMLTextAreaElement ||
      (focused instanceof HTMLInputElement && !["checkbox", "radio", "button", "submit", "range", "file"].includes(focused.type));
    if (!editing) restingHeight = window.innerHeight;
    const keyboard = editing && Math.max(restingHeight - height, window.innerHeight - height) > 140;
    document.body.classList.toggle("mobile-keyboard", keyboard);
    document.documentElement.style.setProperty("--visible-height", `${height}px`);
    document.documentElement.style.setProperty("--keyboard-inset", `${keyboard ? Math.max(0, window.innerHeight - height - (viewport?.offsetTop ?? 0)) : 0}px`);
  };
  window.visualViewport?.addEventListener("resize", sync);
  window.visualViewport?.addEventListener("scroll", sync);
  window.addEventListener("resize", sync);
  document.addEventListener("focusin", sync);
  document.addEventListener("focusout", () => requestAnimationFrame(sync));
  sync();
}

// Keep the dock mounted across route renders: focus and the sliding indicator survive.
export function updateMobileNavigation(section: string, pending: number) {
  let dock = document.getElementById("mobile-dock");
  if (!dock) {
    dock = document.createElement("nav");
    dock.id = "mobile-dock";
    dock.className = "mobile-dock";
    dock.setAttribute("aria-label", "Разделы приложения");
    dock.innerHTML = `<span class="dock-selection" aria-hidden="true"></span>${navItems.map(item => `<a href="#/${item.id}" class="dock-item" data-section="${item.id}"><span class="dock-icon">${icon(item.icon, 23)}${item.id === "appeals" ? '<span class="dock-badge" hidden aria-hidden="true"></span>' : ""}</span><span>${item.label}</span></a>`).join("")}`;
    document.body.append(dock);
    watchKeyboard();
  }
  const index = Math.max(0, navItems.findIndex(item => item.id === section));
  dock.style.setProperty("--active-index", String(index));
  dock.querySelectorAll<HTMLAnchorElement>(".dock-item").forEach((link, i) => {
    const active = i === index;
    link.classList.toggle("active", active);
    if (active) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
    if (link.dataset.section === "appeals") {
      link.setAttribute("aria-label", pending ? `Апелляции, открытых: ${pending}` : "Апелляции");
      const badge = link.querySelector<HTMLElement>(".dock-badge")!;
      badge.hidden = pending === 0;
      badge.textContent = pending > 99 ? "99+" : String(pending);
    }
  });
}
