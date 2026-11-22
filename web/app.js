"use strict";

const view = document.querySelector("#view");
const navigation = document.querySelector("#navigation");
const statusLine = document.querySelector("#status");
const notice = document.querySelector("#notice");
const sections = {
  camp: "Поселение", story: "История", journey: "Походы", hero: "Герой", work: "Занятия",
  journal: "Журнал", company: "Отряд", town: "Город",
};
let game;
let busy = false;
let noticeTimer;
let townPage;
let townRequest = 0;

function make(tag, options = {}, ...children) {
  const element = document.createElement(tag);
  for (const [key, value] of Object.entries(options)) {
    if (value !== null && value !== undefined) element.setAttribute(key, value);
  }
  element.append(...children.flat().filter(child => child != null));
  return element;
}

function image(key) {
  return make("img", { src: `/art/${key}`, alt: "", decoding: "async" });
}

function banner(art, title, text) {
  return make("section", { class: "hero", "aria-labelledby": "page-title" },
    image(art),
    make("div", { class: "hero-content" }, make("h1", { id: "page-title" }, title),
      text ? make("p", {}, text) : null));
}

function tile(art, title, detail, action, selected = false) {
  const children = [image(art), make("h3", {}, title), detail ? make("small", {}, detail) : null];
  const klass = selected ? "tile chosen" : "tile";
  if (action.startsWith("#")) return make("a", { class: klass, href: action }, children);
  const button = make("button", { class: klass, type: "button" }, children);
  button.addEventListener("click", () => perform(action));
  return button;
}

function button(label, command, primary = false) {
  const element = make("button", { class: primary ? "action primary" : "action", type: "button" }, label);
  element.addEventListener("click", () => perform(command));
  return element;
}

function grid(...tiles) { return make("div", { class: "grid" }, ...tiles); }
function actions(...buttons) { return make("div", { class: "actions" }, ...buttons); }
function heading(text) { return make("h2", {}, text); }

function inputForm(fieldLabel, submit, command, numeric = false, limit = 24) {
  const field = make("input", {
    placeholder: fieldLabel, "aria-label": fieldLabel, required: "",
    maxlength: numeric ? 18 : limit, autocomplete: "off", inputmode: numeric ? "numeric" : "text",
    pattern: numeric ? "[0-9]+" : null,
  });
  const form = make("form", {}, field, make("button", { class: "action primary", type: "submit" }, submit));
  form.addEventListener("submit", event => {
    event.preventDefault();
    if (field.value.trim()) perform(`${command} ${field.value.trim()}`);
  });
  return form;
}

async function request(command) {
  const response = await fetch(command ? "/api/action" : "/api/state", command ? {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ command }),
  } : {});
  if (!response.ok) throw new Error("Сервер игры недоступен. Попробуй ещё раз.");
  return response.json();
}

function showNotice(text) {
  const close = make("button", { type: "button", "aria-label": "Закрыть сообщение" }, "×");
  close.addEventListener("click", () => { notice.hidden = true; });
  notice.replaceChildren(document.createTextNode(text), close);
  notice.hidden = false;
  clearTimeout(noticeTimer);
  noticeTimer = setTimeout(() => { notice.hidden = true; }, 6500);
}

async function perform(command) {
  if (busy) return;
  busy = true;
  const buttons = [...view.querySelectorAll("button")];
  buttons.forEach(element => { element.disabled = true; });
  try {
    const response = await request(command);
    game = response.state;
    if (response.town) {
      townPage = response.town;
      if (townSection() !== townPage.section) location.hash = townPage.section ? `#town-${townPage.section}` : "#town";
    }
    if (command?.startsWith("/adventure_") && game.encounter) location.hash = "#journey";
    render();
    if (command?.startsWith("/create ") && townSection() !== null) openTown();
    const openedScreen = (game.encounter && command?.startsWith("/adventure_"))
      || (game.practice && ["/practice_scout", "/practice_herbalist"].includes(command));
    if (response.message && !openedScreen) {
      const hasLiveActions = (game.battle && command?.startsWith("/turn_"))
        || (game.encounter && command?.startsWith("/choose_"))
        || (game.practice && command?.startsWith("/practice_answer_"));
      const text = hasLiveActions ? response.message.split("\n", 1)[0] : response.message;
      const cleaned = text.replace(/(^|[\s·])\/[a-z][a-z0-9_]*/g, "$1").replace(/\s*·\s*(?=\n|$)/gm, "").trim();
      if (cleaned) showNotice(cleaned);
    } else if (openedScreen) {
      notice.hidden = true;
    }
  } catch (error) {
    showNotice(error.message);
  } finally {
    buttons.forEach(element => { element.disabled = false; });
    busy = false;
  }
}

async function profileRequest(operation, key) {
  const response = await fetch("/api/profile", {
    method: "POST", headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ operation, key }),
  });
  if (!response.ok) throw new Error("Не удалось открыть профиль.");
  const result = await response.json();
  if (result.error) throw new Error(result.error);
  return result;
}

function profilePanel() {
  const exportButton = make("button", { type: "button", class: "action" }, "Создать ключ переноса");
  const key = make("input", { readonly: "", hidden: "", "aria-label": "Одноразовый ключ переноса" });
  exportButton.addEventListener("click", async () => {
    exportButton.disabled = true;
    try {
      const result = await profileRequest("issue");
      key.hidden = false;
      key.value = result.key;
      key.focus();
      key.select();
    } catch (error) {
      showNotice(error.message);
    } finally {
      exportButton.disabled = false;
    }
  });
  return make("section", { class: "panel" },
    make("p", {}, "Одноразовый ключ переносит героя в пустой профиль браузера на этом сервере. Храни его отдельно."),
    actions(exportButton, key));
}

function restoreForm() {
  const key = make("input", { required: "", maxlength: 48, pattern: "[a-f0-9]{48}",
    autocomplete: "off", placeholder: "Ключ героя", "aria-label": "Ключ героя" });
  const submit = make("button", { type: "submit", class: "action" }, "Перенести героя");
  const form = make("form", {}, key, submit);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    submit.disabled = true;
    try {
      const result = await profileRequest("restore", key.value);
      game = result.state;
      location.hash = "#hero";
      render();
      showNotice("Герой перенесён.");
    } catch (error) {
      showNotice(error.message);
    } finally {
      submit.disabled = false;
    }
  });
  return form;
}

function camp() {
  return [
    banner("village", "Поселение у леса", "Снарядись, выбери путь и возвращайся сюда между походами."),
    heading("Продолжить историю"),
    make("section", { class: "panel" },
      make("h3", {}, game.story.current?.title || "Летопись завершена"),
      make("p", {}, game.story.current?.description || game.story.ending),
      make("a", { class: "action primary", href: "#story" }, "Открыть летопись")),
    heading("Куда пойти"),
    grid(tile("misty-forest", "В поход", "Шесть локаций и пошаговая охота", "#journey"),
      tile("bag", "К герою", "Характеристики и снаряжение", "#hero"),
      tile("quests", "К доске заданий", "Поговорить с Мирой или Орином", "#company"),
      tile("patrol", "Выбрать занятие", "Герой продолжит путь в твоё отсутствие", "#work"),
      tile("smithy", "Городские занятия", "Ремесло, добыча и соревнования", "#town")),
  ];
}

function metre(label, current, maximum) {
  return make("div", {}, make("strong", {}, `${label} · ${current}/${maximum}`),
    make("progress", { value: current, max: maximum, "aria-label": label }));
}

function storyPage() {
  const story = game.story;
  const current = story.current;
  const milestones = story.chapters.map((title, index) => make("li", {
    class: index === story.completed ? "active-chapter" : null,
    "aria-current": index === story.completed ? "step" : null,
  }, `${index + 1}. ${title}${index < story.completed ? " · завершена" : ""}`));
  const guide = current
    ? make("section", { class: "panel battle" }, heading("Цели главы"),
      make("ul", { class: "story-goals" }, current.goals.map(goal => make("li", {},
        make("span", {}, `${goal.done ? "✓" : "○"} ${goal.label}`),
        goal.done ? null : make("a", { class: "action", href: goal.destination }, "Открыть")))),
      make("p", {}, `Награда: ${current.xp} опыта и ${current.coins} монет`),
      current.ready ? button("Завершить главу", `/story_claim_${current.key}`, true) : null)
    : null;
  return [
    banner(current?.art || "village", current?.title || "Летопись завершена", current?.description || story.ending),
    guide,
    heading(`Главы · ${story.completed}/${story.chapters.length}`),
    make("ol", { class: "chapter-list panel" }, milestones),
  ];
}

function regionPage(route) {
  const available = game.hero.level >= route.level;
  const start = button("Отправиться", `/adventure_${route.key}`, true);
  start.disabled = !available;
  const details = route.difficulty ? `Базовый ранг навыка: ${route.difficulty}.` : "Подходит для первого похода.";
  return [
    banner(route.art, route.name, route.description),
    make("section", { class: "panel battle" },
      make("p", {}, `Уровень ${route.level} · этапов: ${route.scenes}`),
      make("p", {}, details),
      route.scenes > 1 ? make("p", {}, `Подготовка с ранга ${Math.max(0, route.difficulty - 1)} облегчает финал.`) : null,
      make("p", { class: "muted" }, `Твои ранги: следопыт ${Math.floor(game.hero.scout / 3)}, травник ${Math.floor(game.hero.herbalist / 3)}.`),
      actions(available ? start : make("p", {}, `Откроется на уровне ${route.level}.`),
        make("a", { class: "action", href: "#journey" }, "Все походы"),
        make("a", { class: "action", href: "#work" }, "Развить навыки"))),
  ];
}

function journeys() {
  const battle = game.battle;
  const encounter = game.encounter;
  if (battle) {
    return [
      banner(battle.art, battle.name, battle.turn % 3 === 0 ? "Противник готовит сильный удар." : "Противник готовит обычную атаку."),
      make("section", { class: "panel battle" }, make("h3", {}, `Ход ${battle.turn}`),
        make("div", { class: "meters" }, metre("Герой", battle.hp, battle.max_hp), metre("Противник", battle.foe_hp, battle.foeMax)),
        actions(battle.actions.map(({key, label}) => button(label, `/turn_${key}`, key === "strike")))),
    ];
  }
  if (encounter) {
    return [
      banner(encounter.art, encounter.title, encounter.description),
      make("section", { class: "panel battle" },
        encounter.total > 1 ? make("p", {}, `Этап ${encounter.stage}/${encounter.total}`) : null,
        encounter.required !== null ? make("p", {}, `Требуемый ранг профессии: ${encounter.required}`) : null,
        encounter.bonus ? make("p", {}, `За успех: +${encounter.bonus} монет.`) : null,
        encounter.detour ? make("div", { class: "detour" },
          make("h3", {}, "Попутный выбор"), make("p", {}, encounter.detour.description),
          actions(encounter.detour.aid_available
            ? button(`${encounter.detour.aid} · ${encounter.detour.cost} монет, −1 ранг`, "/choose_aid") : null,
            button(`${encounter.detour.risk} · +1 ранг, +${encounter.detour.bonus} монет`, "/choose_risk"))) : null,
        actions(encounter.choices.map((choice, i) => button(choice, `/choose_${i + 1}`, i === 0)),
          button("Вернуться в поселение", "/choose_leave"))),
    ];
  }
  return [
    banner("misty-forest", "Походы", "В лесу важны внимательность и подготовка. Выбери маршрут или противника."),
    heading("Маршруты"),
    grid(game.routes.map(route => tile(route.art, route.name,
      `С уровня ${route.level}${route.scenes > 1 ? " · 2 этапа" : ""}`, `#route-${route.key}`))),
    heading("Пошаговая охота"),
    grid(game.enemies.map(enemy => tile(enemy.art, enemy.name, `С уровня ${enemy.level}`, `/hunt_${enemy.key}`))),
  ];
}

function heroPage() {
  const hero = game.hero;
  const slots = { armor: "Броня", charm: "Оберег", weapon: "Оружие", ring: "Кольцо", amulet: "Амулет" };
  return [
    banner("hero", hero.name, `Уровень ${hero.level} · Здоровье ${hero.hp} · Атака ${hero.attack}`),
    make("section", { class: "panel battle" }, metre("Опыт до следующего уровня", hero.xp % 30, 30),
      make("p", {}, `${hero.coins} монет`)),
    heading("Снаряжение"),
    game.bag.length ? grid(game.bag.map(item => tile(item.key, item.name,
      `${slots[item.slot]} · +${item.bonus} · ×${item.quantity}${item.worn ? " · надето" : " · надеть"}`,
      `/equip_${item.key}`, item.worn))) : make("p", { class: "muted" }, "Сумка пуста. Найди первую добычу в походе."),
    heading("Профессии"),
    grid(Object.entries(game.professions).map(([key, name]) => tile(key, name,
      `Очков навыка: ${hero[key]} · Тренировка за 5 монет`, `/train_${key}`))),
    heading("Профиль браузера"),
    profilePanel(),
  ];
}

function practicePanel(practice) {
  const legend = {
    "#": ["wall", "Преграда", "■"], "@": ["player", "Герой", "✧"],
    "X": ["goal", "Цель", "✦"], "~": ["water", "Топь", "≈"],
  };
  const board = practice.board
    ? make("div", { class: "trail", role: "img", "aria-label": practice.board.join(", ") },
      practice.board.flatMap(row => [...row].map(cell => {
        const [style, title, symbol] = legend[cell] || ["ground", "Тропа", "·"];
        return make("span", { class: style, title, "aria-hidden": "true" }, symbol);
      })))
    : make("div", { class: "meters" },
      metre(`Температура, цель ${practice.target}`, practice.heat, 6),
      metre("Готовые порции", practice.progress, 3));
  return make("section", { class: "panel" }, make("h3", {}, practice.title),
    make("p", {}, practice.description),
    make("p", {}, `Осталось ходов: ${practice.remaining}${practice.stock === undefined ? "" : ` · Сырьё: ${practice.stock}`}`),
    board,
    actions(practice.actions.map(({key, label}) => button(label, `/practice_answer_${key}`)),
      button("Завершить", "/practice_answer_cancel")));
}

function work() {
  const practice = game.practice;
  return [
    banner(practice?.skill === "herbalist" ? "herbalist-game" : "patrol", "Занятия",
      "Выбирай, чем герой займётся между визитами, и развивай профессии в испытаниях."),
    heading("Фоновое занятие"),
    grid(game.jobs.map(job => tile(job.art, job.name, job.description, `/offline_${job.key}`, game.job === job.key))),
    heading("Испытания профессий"),
    practice ? practicePanel(practice) :
      grid(tile("scout-game", "Тропа по следам", "Проложи путь по карте", "/practice_scout"),
        tile("herbalist-game", "Настой у котла", "Управляй огнём и добавляй порции", "/practice_herbalist")),
  ];
}

function journal() {
  const date = new Intl.DateTimeFormat("ru", { dateStyle: "short", timeStyle: "short" });
  return [
    banner("journal", "Журнал героя", "Последние события, рассчитанные с учётом выбранного занятия."),
    actions(button("Обновить журнал")),
    game.journal.length ? grid(game.journal.map(entry => make("article", { class: "panel event-card" },
      entry.art ? image(entry.art) : null,
      make("time", {}, date.format(new Date(entry.occurred_at * 1000))), make("p", {}, entry.summary)))) :
      make("p", { class: "muted" }, "Первое фоновое событие появится примерно через 30 минут после создания героя."),
  ];
}

function company() {
  return [
    banner("colossus", "Квесты и отряд", "Выполняй поручения жителей или собери других героев для рейда."),
    heading("Поручения"),
    grid(game.quests.map(quest => tile(quest.art, quest.title,
      `${quest.npc} · ${quest.description}`, `/quest_${quest.key}`))),
    heading("Совместная игра"),
    make("section", { class: "panel" }, make("h3", {}, "Рейд на Каменного колосса"),
      actions(button("Мой отряд", "/raid"), button("Создать отряд", "/raid_open"),
        button("Начать рейд", "/raid_start"), button("Выйти", "/raid_leave")),
      inputForm("Номер отряда", "Вступить", "/raid join", true)),
    make("section", { class: "panel battle" }, make("h3", {}, "Дуэли"),
      make("p", {}, `Идентификатор твоего героя: ${game.hero.user_id}`),
      actions(button("Вызовы и счёт", "/pvp"), button("Отклонить вызов", "/pvp_decline")),
      inputForm("ID соперника", "Вызвать", "/pvp challenge", true),
      inputForm("ID соперника", "Принять вызов", "/pvp accept", true)),
  ];
}

function townSection() {
  const found = /^#town(?:-([a-z]+))?$/.exec(location.hash);
  if (!found) return null;
  return game?.townSections?.includes(found[1]) ? found[1] : "";
}

async function openTown() {
  const section = townSection();
  if (section === null || !game?.hero) return;
  const requestId = ++townRequest;
  try {
    const response = await request(section ? `/town ${section}` : "/town");
    if (requestId !== townRequest || townSection() !== section) return;
    game = response.state;
    townPage = response.town;
    render();
  } catch (error) {
    showNotice(error.message);
  }
}

function townScreen(section) {
  if (!townPage || townPage.section !== section) {
    return [make("p", { role: "status" }, "Загрузка городских занятий…")];
  }
  if (!section) {
    return [banner(townPage.art, "Городские занятия", townPage.text),
      heading("Куда заглянуть"),
      grid(townPage.buttons.map(item => tile(item.art, item.label, "", `#town-${item.command.split(" ")[1]}`)))];
  }
  const text = townPage.text.split("\n").filter(Boolean);
  return [
    banner(townPage.art, townPage.title, text[0] || ""),
    make("section", { class: "panel battle" },
      ...text.slice(1).map(line => make("p", {}, line)),
      actions(townPage.buttons.map(item => button(item.label, `/${item.command}`)),
        button("Обновить", `/town ${section}`),
        make("a", { class: "action", href: "#town" }, "Все городские занятия")),
      townPage.fields.map(field => inputForm(field.label, "Отправить", `/${field.command}`, false, 200))),
  ];
}

function render() {
  view.removeAttribute("aria-busy");
  navigation.hidden = !game.hero;
  if (!game.hero) {
    statusLine.textContent = "";
    view.replaceChildren(banner("village", "Живой мир", "Твоя история начинается у границы Туманного леса."),
      make("section", { class: "panel battle" }, make("h2", {}, "Создай героя"),
        inputForm("Имя героя", "Войти в мир", "/create"), restoreForm()));
    return;
  }
  const page = location.hash.slice(1);
  const region = page.startsWith("route-") ? game.routes.find(route => route.key === page.slice(6)) : null;
  const town = townSection();
  const current = town !== null ? "town" : region ? "journey" : Object.hasOwn(sections, page) ? page : "camp";
  navigation.replaceChildren(...Object.entries(sections).map(([key, label]) =>
    make("a", { href: `#${key}`, "aria-current": key === current ? "page" : null }, label)));
  statusLine.textContent = `${game.hero.name} · ур. ${game.hero.level} · ${game.hero.coins} монет`;
  const pages = { camp, story: storyPage, journey: journeys, hero: heroPage, work, journal, company };
  view.replaceChildren(...(town !== null ? townScreen(town) : region ? regionPage(region) : pages[current]()));
}

window.addEventListener("hashchange", () => {
  notice.hidden = true;
  if (game) render();
  openTown();
  window.scrollTo(0, 0);
});
request().then(response => { game = response.state; render(); openTown(); }).catch(error => {
  view.removeAttribute("aria-busy");
  view.replaceChildren(make("p", {}, error.message),
    make("a", { class: "action", href: "/" }, "Перезагрузить"));
});
