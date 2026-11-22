"use strict";

const view = document.querySelector("#view");
const navigation = document.querySelector("#navigation");
const statusLine = document.querySelector("#status");
const notice = document.querySelector("#notice");
const sections = {
  camp: "Поселение", journey: "Походы", hero: "Герой", work: "Занятия",
  journal: "Журнал", company: "Отряд",
};
let game;
let busy = false;
let noticeTimer;

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

function inputForm(fieldLabel, submit, command, numeric = false) {
  const field = make("input", {
    placeholder: fieldLabel, "aria-label": fieldLabel, required: "",
    maxlength: numeric ? 18 : 24, autocomplete: "off", inputmode: numeric ? "numeric" : "text",
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
    render();
    if (response.message) {
      const text = command?.startsWith("/turn_") && game.battle
        ? response.message.split("\n", 1)[0]
        : response.message;
      const cleaned = text.replace(/(^|[\s·])\/[a-z][a-z0-9_]*/g, "$1").replace(/\s*·\s*(?=\n|$)/gm, "").trim();
      if (cleaned) showNotice(cleaned);
    }
  } catch (error) {
    showNotice(error.message);
  } finally {
    buttons.forEach(element => { element.disabled = false; });
    busy = false;
  }
}

function camp() {
  return [
    banner("village", "Поселение у леса", "Снарядись, выбери путь и возвращайся сюда между походами."),
    heading("Куда пойти"),
    grid(tile("misty-forest", "В поход", "Лес, башня и пошаговая охота", "#journey"),
      tile("bag", "К герою", "Характеристики и снаряжение", "#hero"),
      tile("quests", "К доске заданий", "Поговорить с Мирой или Орином", "#company"),
      tile("patrol", "Выбрать занятие", "Герой продолжит путь в твоё отсутствие", "#work")),
  ];
}

function metre(label, current, maximum) {
  return make("div", {}, make("strong", {}, `${label} · ${current}/${maximum}`),
    make("progress", { value: current, max: maximum, "aria-label": label }));
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
      banner(game.hero.route === "forest" ? "misty-forest" : "old-tower",
        game.hero.route === "forest" ? "Туманный лес" : "Старая башня", encounter.description),
      actions(encounter.choices.map((choice, i) => button(choice, `/choose_${i + 1}`, i === 0))),
    ];
  }
  return [
    banner("misty-forest", "Походы", "В лесу важны внимательность и подготовка. Выбери маршрут или противника."),
    heading("Маршруты"),
    grid(tile("misty-forest", "Туманный лес", "С уровня 1", "/adventure_forest"),
      tile("old-tower", "Старая башня", "С уровня 2", "/adventure_ruins")),
    heading("Пошаговая охота"),
    grid(game.enemies.map(enemy => tile(enemy.art, enemy.name, `С уровня ${enemy.level}`, `/hunt_${enemy.key}`))),
  ];
}

function heroPage() {
  const hero = game.hero;
  const slots = { armor: "Броня", charm: "Оберег", weapon: "Оружие" };
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
  ];
}

function work() {
  const practice = game.practice;
  return [
    banner(practice?.skill === "herbalist" ? "herbalist-game" : "patrol", "Занятия",
      "Выбирай, чем герой займётся между визитами, и развивай профессии в испытаниях."),
    heading("Фоновое занятие"),
    grid(game.jobs.map(job => tile(job.art, job.name, job.description, `/offline_${job.key}`, game.job === job.key))),
    heading("Испытания профессий"),
    practice ? make("section", { class: "panel" },
      make("h3", {}, `Задание ${practice.step}/3`), make("p", {}, practice.prompt),
      actions(practice.choices.map((answer, i) => button(answer, `/practice_answer_${i + 1}`)),
        button("Завершить", "/practice_answer_cancel"))) :
      grid(tile("scout-game", "Читать следы", "Испытание следопыта", "/practice_scout"),
        tile("herbalist-game", "Подобрать травы", "Испытание травника", "/practice_herbalist")),
  ];
}

function journal() {
  const date = new Intl.DateTimeFormat("ru", { dateStyle: "short", timeStyle: "short" });
  return [
    banner("journal", "Журнал героя", "Последние события, рассчитанные с учётом выбранного занятия."),
    actions(button("Обновить журнал")),
    game.journal.length ? grid(game.journal.map(entry => make("article", { class: "panel" },
      make("time", {}, date.format(new Date(entry.occurred_at * 1000))), make("p", {}, entry.summary)))) :
      make("p", { class: "muted" }, "Первое фоновое событие появится примерно через 30 минут после создания героя."),
  ];
}

function company() {
  return [
    banner("colossus", "Квесты и отряд", "Выполняй поручения жителей или собери других героев для рейда."),
    heading("Поручения"),
    grid(tile("mira", "Дозорница Мира", "Два успешных похода в лес", "/quest_forest"),
      tile("orin", "Архивист Орин", "Победа над Пепельным смотрителем", "/quest_keeper")),
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

function render() {
  view.removeAttribute("aria-busy");
  navigation.hidden = !game.hero;
  if (!game.hero) {
    statusLine.textContent = "";
    view.replaceChildren(banner("village", "Живой мир", "Твоя история начинается у границы Туманного леса."),
      make("section", { class: "panel battle" }, make("h2", {}, "Создай героя"),
        inputForm("Имя героя", "Войти в мир", "/create")));
    return;
  }
  const page = location.hash.slice(1);
  const current = Object.hasOwn(sections, page) ? page : "camp";
  navigation.replaceChildren(...Object.entries(sections).map(([key, label]) =>
    make("a", { href: `#${key}`, "aria-current": key === current ? "page" : null }, label)));
  statusLine.textContent = `${game.hero.name} · ур. ${game.hero.level} · ${game.hero.coins} монет`;
  const pages = { camp, journey: journeys, hero: heroPage, work, journal, company };
  view.replaceChildren(...pages[current]());
}

window.addEventListener("hashchange", () => {
  notice.hidden = true;
  if (game) render();
  window.scrollTo(0, 0);
});
request().then(response => { game = response.state; render(); }).catch(error => {
  view.removeAttribute("aria-busy");
  view.replaceChildren(make("p", {}, error.message),
    make("a", { class: "action", href: "/" }, "Перезагрузить"));
});
