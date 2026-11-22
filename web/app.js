"use strict";

const view = document.querySelector("#view");
const navigation = document.querySelector("#navigation");
const statusLine = document.querySelector("#status");
const notice = document.querySelector("#notice");
const navigationItems = [
  ["camp", "Главная", "⌂"], ["journey", "Походы", "⚔︎"], ["hero", "Герой", "♙"],
  ["town", "Город", "▦"], ["journal", "Журнал", "≡"],
];
const navigationParents = { story: "camp", work: "camp", company: "camp" };
let game;
let busy = false;
let caveTimer;
let townPage;
let townReceivedAt;
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

function banner(art, title, text, options = {}) {
  return make("section", { class: options.compact ? "hero hero-compact" : "hero", "aria-labelledby": "page-title" },
    image(art),
    make("div", { class: "hero-content" }, make("h1", { id: "page-title", tabindex: "-1" }, title),
      text ? make("p", {}, text) : null, options.footer));
}

function tile(art, title, detail, action, selected = false, locked = false) {
  const children = [image(art), make("h3", {}, title), detail ? make("small", {}, detail) : null];
  const klass = selected ? "tile chosen" : "tile";
  if (action.startsWith("#")) return make("a", { class: klass, href: action }, children);
  const button = make("button", { class: klass, type: "button", "data-command": action,
    "aria-pressed": selected ? "true" : null, disabled: locked ? "" : null }, children);
  button.addEventListener("click", () => perform(action));
  return button;
}

function button(label, command, primary = false) {
  const element = make("button", { class: primary ? "action primary" : "action", type: "button", "data-command": command }, label);
  element.addEventListener("click", () => perform(command));
  return element;
}

function cardList(...cards) {
  return make("ul", { class: "card-list" }, cards.flat().map(card => make("li", {}, card)));
}
function actions(...buttons) { return make("div", { class: "actions" }, ...buttons); }
function heading(text) { return make("h2", {}, text); }
function link(label, destination, primary = false) {
  return make("a", { class: primary ? "action primary" : "action", href: destination }, label);
}
function back(label, destination) { return make("a", { class: "back-link", href: destination }, "← ", label); }
function feedbackPanel(...children) { return make("section", { class: "panel battle", "data-feedback": "" }, children); }
function focusTitle() { (view.querySelector("h1") || view).focus({ preventScroll: true }); }
function mountNotice() {
  const target = view.querySelector("[data-feedback]");
  const art = view.querySelector(".hero");
  if (target) target.prepend(notice);
  else if (art) art.after(notice);
  else view.prepend(notice);
}

function inputForm(fieldLabel, submit, command, numeric = false, limit = 24) {
  const field = make("input", {
    required: "",
    maxlength: numeric ? 18 : limit, autocomplete: "off", inputmode: numeric ? "numeric" : "text",
    pattern: numeric ? "[0-9]+" : null,
  });
  const labeled = make("label", { class: "form-field" }, make("span", {}, fieldLabel), field);
  const form = make("form", {}, labeled, make("button", { class: "action primary", type: "submit" }, submit));
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

}

async function perform(command) {
  if (busy) return;
  busy = true;
  const focusedCommand = document.activeElement?.dataset.command;
  const buttons = [...view.querySelectorAll("button:not(:disabled)")];
  notice.hidden = true;
  buttons.forEach(element => { element.disabled = true; });
  try {
    const response = await request(command);
    game = response.state;
    if (response.town) {
      townPage = response.town;
      townReceivedAt = performance.now();
      if (townSection() !== townPage.section) location.hash = townPage.section ? `#town-${townPage.section}` : "#town";
    }
    if (command?.startsWith("/adventure_") && game.encounter) location.hash = "#journey";
    render();
    if (focusedCommand) {
      const current = [...view.querySelectorAll("[data-command]:not(:disabled)")]
        .find(element => element.dataset.command === focusedCommand);
      (current || view.querySelector("[data-feedback] button:not(:disabled)") || view.querySelector("h1"))?.focus({ preventScroll: true });
    }
    if (command?.startsWith("/create ") && townSection() !== null) openTown();
    const openedScreen = (game.hero && command?.startsWith("/create "))
      || (game.encounter && command?.startsWith("/adventure_"))
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
  const story = game.story;
  const chapter = story.current;
  let next = ["Продолжить историю", "#story"];
  if (game.battle) next = ["Продолжить бой", "#journey"];
  else if (game.encounter) next = ["Продолжить поход", "#journey"];
  else if (game.activeContest) next = ["Продолжить испытание", "#town-battle"];
  else if (game.practice) next = ["Продолжить мини-игру", "#work"];
  else if (chapter?.ready) next = ["Забрать награду главы", "#story"];
  else if (!chapter) next = ["Посмотреть летопись", "#story"];
  const goal = chapter?.goals.find(item => !item.done);
  const description = game.battle ? `${game.battle.name} · ход ${game.battle.turn}`
    : game.encounter ? `${game.encounter.title} · этап ${game.encounter.stage}/${game.encounter.total}`
    : game.activeContest ? "Испытание на арене продолжается"
    : game.practice ? game.practice.title
    : chapter ? `Глава ${story.completed + 1}/${story.chapters.length} · ${chapter.title}` : "История поселения завершена.";
  return [
    banner("village", "Поселение у леса", description, { footer: actions(link(...next, true),
      next[1] === "#story" ? null : link("История", "#story")) }),
    goal && next[1] === "#story" ? make("p", { class: "next-goal" }, "Следующая цель: ", goal.label) : null,
    heading("Быстрый доступ"),
    cardList(tile("misty-forest", "Походы", "Маршруты и пошаговые бои", "#journey"),
      tile("bag", "Герой", "Снаряжение и профессии", "#hero"),
      tile("quests", "Задания и отряд", "Поручения, рейды и дуэли", "#company"),
      tile("patrol", "Занятия", "Фоновая работа и мини-игры", "#work")),
  ].filter(Boolean);
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
    ? feedbackPanel(heading("Цели главы"),
      make("ul", { class: "story-goals" }, current.goals.map(goal => make("li", {},
        make("span", {}, `${goal.done ? "✓" : "○"} ${goal.label}`),
        goal.done ? null : make("a", { class: "action", href: goal.destination }, "Открыть")))),
      make("p", {}, `Награда: ${current.xp} опыта и ${current.coins} монет`),
      current.ready ? button("Завершить главу", `/story_claim_${current.key}`, true) : null)
    : null;
  return [
    banner(current?.art || "village", current?.title || "Летопись завершена", current?.description || story.ending, { compact: true }),
    guide,
    heading(`Главы · ${story.completed}/${story.chapters.length}`),
    make("ol", { class: "chapter-list panel" }, milestones),
  ];
}

function regionPage(route) {
  const available = game.hero.level >= route.level;
  const start = button("Отправиться", `/adventure_${route.key}`, true);
  const details = route.difficulty ? `Базовый ранг навыка: ${route.difficulty}.` : "Подходит для первого похода.";
  return [
    back("Походы", "#journey"),
    banner(route.art, route.name, route.description, { compact: true }),
    feedbackPanel(
      make("p", {}, `Уровень ${route.level} · этапов: ${route.scenes}`),
      make("p", {}, details),
      route.scenes > 1 ? make("p", {}, `Подготовка с ранга ${Math.max(0, route.difficulty - 1)} облегчает финал.`) : null,
      make("p", { class: "muted" }, `Твои ранги: следопыт ${Math.floor(game.hero.scout / 3)}, травник ${Math.floor(game.hero.herbalist / 3)}.`),
      actions(available ? start : make("p", {}, `Откроется на уровне ${route.level}.`),
        link("Развить навыки", "#work"))),
  ];
}

function journeys() {
  const battle = game.battle;
  const encounter = game.encounter;
  if (battle) {
    return [
      banner(battle.art, battle.name, "", { compact: true }),
      feedbackPanel(make("div", { class: "combat-line" }, make("h3", {}, `Ход ${battle.turn}`),
        make("span", { class: battle.turn % 3 === 0 ? "warning-chip" : "muted" },
          battle.turn % 3 === 0 ? "⚠ Готовится сильный удар" : "Обычная атака противника")),
        make("div", { class: "meters" }, metre("Герой", battle.hp, battle.max_hp), metre("Противник", battle.foe_hp, battle.foeMax)),
        actions(battle.actions.map(({key, label}) => button(label, `/turn_${key}`, key === "strike")))),
    ];
  }
  if (encounter) {
    return [
      banner(encounter.art, encounter.title, encounter.description, { compact: true }),
      feedbackPanel(
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
    cardList(game.routes.map(route => tile(route.art, route.name,
      `${game.hero.level < route.level ? "Закрыто · " : ""}Уровень ${route.level}${route.scenes > 1 ? " · 2 этапа" : ""}`, `#route-${route.key}`))),
    heading("Пошаговая охота"),
    cardList(game.enemies.map(enemy => tile(enemy.art, enemy.name,
      game.hero.level < enemy.level ? `Закрыто · уровень ${enemy.level}` : "Начать бой",
      `/hunt_${enemy.key}`, false, game.hero.level < enemy.level))),
  ];
}

function heroPage() {
  const hero = game.hero;
  const wornFirst = [...game.bag].sort((a, b) => Number(b.worn) - Number(a.worn));
  const slots = { armor: "Броня", charm: "Оберег", weapon: "Оружие", ring: "Кольцо", amulet: "Амулет" };
  return [
    banner("hero", hero.name, `Уровень ${hero.level} · Здоровье ${hero.hp} · Атака ${hero.attack}`, { compact: true }),
    make("section", { class: "panel battle" }, metre("Опыт до следующего уровня", hero.xp % 30, 30),
      make("p", {}, `${hero.coins} монет`)),
    heading("Снаряжение"),
    wornFirst.length ? cardList(wornFirst.map(item => tile(item.key, item.name,
      `${slots[item.slot]} · +${item.bonus} · ×${item.quantity}${item.worn ? " · надето" : " · надеть"}`,
      `/equip_${item.key}`, item.worn))) : make("p", { class: "muted" }, "Сумка пуста. Найди первую добычу в походе."),
    heading("Профессии"),
    cardList(Object.entries(game.professions).map(([key, name]) => tile(key, name,
      `Очков навыка: ${hero[key]} · Тренировка за 5 монет`, `/train_${key}`))),
    make("details", { class: "panel battle" }, make("summary", {}, "Перенос героя"), profilePanel()),
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
  return feedbackPanel(make("h3", {}, practice.title),
    make("p", {}, practice.description),
    make("p", {}, `Осталось ходов: ${practice.remaining}${practice.stock === undefined ? "" : ` · Сырьё: ${practice.stock}`}`),
    board,
    actions(practice.actions.map(({key, label}) => button(label, `/practice_answer_${key}`)),
      button("Завершить", "/practice_answer_cancel")));
}

function work() {
  const practice = game.practice;
  const lessons = [heading("Мини-игры профессий"),
    practice ? practicePanel(practice) :
      cardList(tile("scout-game", "Тропа по следам", "Проложи путь по карте", "/practice_scout"),
        tile("herbalist-game", "Настой у котла", "Управляй огнём и добавляй порции", "/practice_herbalist"))];
  const jobs = [heading("Фоновое занятие"),
    cardList(game.jobs.map(job => tile(job.art, job.name,
      game.job === job.key ? `Выбрано · ${job.description}` : job.description,
      `/offline_${job.key}`, game.job === job.key)))];
  return [
    back("Главная", "#camp"),
    banner(practice?.skill === "herbalist" ? "herbalist-game" : "patrol", "Занятия",
      "Выбирай работу героя между визитами и развивай профессии в мини-играх.", { compact: true }),
    ...(practice ? [...lessons, ...jobs] : [...jobs, ...lessons]),
  ];
}

function journal() {
  const date = new Intl.DateTimeFormat("ru", { dateStyle: "short", timeStyle: "short" });
  return [
    banner("journal", "Журнал героя", "Последние события, рассчитанные с учётом выбранного занятия."),
    actions(button("Обновить журнал")),
    game.journal.length ? cardList(game.journal.map(entry => make("article", { class: "panel event-card" },
      entry.art ? image(entry.art) : null,
      make("time", {}, date.format(new Date(entry.occurred_at * 1000))), make("p", {}, entry.summary)))) :
      make("p", { class: "muted" }, "Первое фоновое событие появится примерно через 30 минут после создания героя."),
  ];
}

function company() {
  return [
    banner("colossus", "Квесты и отряд", "Выполняй поручения жителей или собери других героев для рейда."),
    heading("Поручения"),
    cardList(game.quests.map(quest => tile(quest.art, quest.title,
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
  const found = /^#town(?:-([a-z_]+))?$/.exec(location.hash);
  if (!found) return null;
  return game?.townSections?.includes(found[1]) ? found[1] : "";
}

async function openTown(focus = false) {
  const section = townSection();
  if (section === null || !game?.hero) return;
  const requestId = ++townRequest;
  try {
    const response = await request(section ? `/town ${section}` : "/town");
    if (requestId !== townRequest || townSection() !== section) return;
    game = response.state;
    townPage = response.town;
    townReceivedAt = performance.now();
    render();
    if (focus) focusTitle();
  } catch (error) {
    showNotice(error.message);
  }
}

function townScreen(section) {
  if (!townPage || townPage.section !== section) {
    return [make("p", { role: "status" }, "Загружаем городские занятия…")];
  }
  const parent = townPage.parent ? `#town-${townPage.parent}` : "#town";
  if (townPage.directory) {
    return [
      ...(section ? [back("Город", "#town")] : []),
      banner(townPage.art, section ? townPage.title : "Городские занятия", townPage.text, { compact: true }),
      cardList(townPage.buttons.map(item => tile(item.art, item.label, item.detail,
        `#town-${item.command.split(" ")[1]}`))),
    ];
  }
  const [first, ...details] = townPage.text.split("\n").filter(Boolean);
  const resourceItems = Object.entries(townPage.resources || {});
  const more = details.map(line => make("p", {}, line));
  const fullText = ["clan", "records", "chat", "forum", "guildchat", "mail", "collection", "forge", "lab"].includes(section)
    || (section === "battle" && game.activeContest);
  return [
    back(townPage.parent ? "К разделу" : "Город", parent),
    banner(townPage.art, townPage.title, "", { compact: true }),
    feedbackPanel(
      townPage.readyAt ? make("p", { class: "timer-status", "data-cave-timer": "" }, first) : make("p", {}, first),
      resourceItems.length ? make("ul", { class: "resource-list", "aria-label": "Материалы" },
        resourceItems.map(([name, amount]) => make("li", {}, name, " ", make("strong", {}, String(amount))))) : null,
      fullText ? more : null,
      actions(townPage.buttons.map((item, index) => button(item.label, `/${item.command}`, index === 0)),
        button("Обновить", `/town ${section}`)),
      !fullText && more.length ? make("details", { class: "activity-details" }, make("summary", {}, "Правила и подробности"), more) : null,
      townPage.fields.map(field => inputForm(field.label, field.submit, `/${field.command}`, field.numeric, 200))),
  ];
}

function startCaveTimer() {
  const text = view.querySelector("[data-cave-timer]");
  const collect = view.querySelector('[data-command="/town cave collect"]');
  if (!text || !collect || !townPage?.readyAt) return;
  const started = townReceivedAt;
  const duration = Math.max(0, townPage.readyAt - townPage.serverTime);
  const update = () => {
    const left = Math.max(0, duration - Math.floor((performance.now() - started) / 1000));
    text.textContent = left ? `Герой вернётся через ${left} сек.` : "Добыча готова. Её можно забрать.";
    collect.disabled = left > 0;
    if (!left) clearInterval(caveTimer);
  };
  caveTimer = setInterval(update, 1000);
  update();
}

function render() {
  clearInterval(caveTimer);
  view.removeAttribute("aria-busy");
  navigation.hidden = !game.hero;
  statusLine.hidden = !game.hero;
  if (!game.hero) {
    view.replaceChildren(banner("village", "Живой мир", "Твоя история начинается у границы Туманного леса."),
      feedbackPanel(heading("Создай героя"), inputForm("Имя героя", "Войти в мир", "/create"),
        make("details", { class: "activity-details" }, make("summary", {}, "Уже есть герой"), restoreForm())));
    mountNotice();
    return;
  }
  const page = location.hash.slice(1);
  const pages = { camp, story: storyPage, journey: journeys, hero: heroPage, work, journal, company };
  const region = page.startsWith("route-") ? game.routes.find(route => route.key === page.slice(6)) : null;
  const town = townSection();
  const current = town !== null ? "town" : region ? "journey" : Object.hasOwn(pages, page) ? page : "camp";
  const activeNav = navigationParents[current] || current;
  navigation.replaceChildren(...navigationItems.map(([key, label, symbol]) =>
    make("a", { href: `#${key}`, "aria-current": key === activeNav ? "page" : null },
      make("span", { "aria-hidden": "true", class: "nav-icon" }, symbol), label)));
  statusLine.replaceChildren(make("strong", {}, game.hero.name),
    make("span", {}, `Ур. ${game.hero.level} · ${game.hero.coins} монет`));
  const content = town !== null ? townScreen(town) : region ? regionPage(region) : pages[current]();
  view.replaceChildren(...content.filter(Boolean));
  mountNotice();
  startCaveTimer();
}

document.querySelector(".skip-link").addEventListener("click", event => {
  event.preventDefault();
  focusTitle();
});
window.addEventListener("hashchange", () => {
  notice.hidden = true;
  window.scrollTo(0, 0);
  if (!game) return;
  render();
  focusTitle();
  openTown(true);
});
request().then(response => { game = response.state; render(); openTown(); }).catch(error => {
  view.removeAttribute("aria-busy");
  view.replaceChildren(make("p", {}, error.message),
    make("a", { class: "action", href: "/" }, "Перезагрузить"));
});
