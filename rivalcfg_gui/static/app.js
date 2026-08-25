"use strict";

const SVG = "http://www.w3.org/2000/svg";
const TOKEN = document.documentElement.dataset.token;
const $ = (id) => document.getElementById(id);

const TROUBLE = {
  permission: "Permission needed",
  unreachable: "Not responding",
  bug: "Something broke",
  server: "Server unreachable",
};

const headline = (kind) => TROUBLE[kind] || "No mouse found";

const GROUP_ICON = {
  Performance: "gauge",
  Lighting: "light",
  Buttons: "buttons",
  Power: "battery",
  Other: "other",
};

let fields = [];
let values = {};
let online = null;
let spy = null;

/* ---- dom ------------------------------------------------------------- */
function el(tag, props = {}, ...children) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(props)) {
    if (value == null || value === false || key === "value") continue;
    if (key.includes("-")) node.setAttribute(key, value);
    else node[key] = value;
  }
  // set last: a range input clamps against whatever max is in place at the time
  if (props.value != null) node.value = props.value;
  node.append(...children.flat().filter((child) => child != null && child !== false));
  return node;
}

function icon(name, cls = "ico") {
  const svg = document.createElementNS(SVG, "svg");
  svg.setAttribute("class", cls);
  svg.setAttribute("aria-hidden", "true");
  const use = document.createElementNS(SVG, "use");
  use.setAttribute("href", "#i-" + name);
  svg.append(use);
  return svg;
}

const slug = (text) => text.toLowerCase().replace(/[^a-z0-9]+/g, "-");
const humanise = (text) => String(text).replace(/[-_]+/g, " ").replace(/^./, (c) => c.toUpperCase());
const longFlag = (flags) => flags.find((flag) => flag.startsWith("--")) || flags[0];
const clamp = (value, f) => Math.min(f.max, Math.max(f.min, Number(value) || f.min));

/* ---- api ------------------------------------------------------------- */
async function api(path, body) {
  const init = body
    ? {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Token": TOKEN },
        body: JSON.stringify(body),
      }
    : {};
  const response = await fetch(path, init);
  const data = await response.json().catch(() => ({}));
  if (response.ok) return data;
  throw Object.assign(new Error(data.error || response.statusText), data);
}

function toast(message, tone = "ok", hint = "") {
  const node = el(
    "div",
    { className: "toast", "data-tone": tone },
    icon(tone === "ok" ? "check" : "alert"),
    el("span", { className: "toast__text" }, el("span", {}, message), hint ? el("small", {}, hint) : null)
  );
  node.onclick = () => node.remove();
  $("toasts").append(node);
  setTimeout(() => node.remove(), tone === "ok" ? 2400 : 7000);
}

const fault = (error) => toast(error.message, "error", error.hint || "");

/* ---- writing --------------------------------------------------------- */
const timers = new Map();

function write(name, value, instant = false) {
  clearTimeout(timers.get(name));
  const send = async () => {
    try {
      values = (await api("/api/settings", { name, value })).values;
      flash(name);
      return true;
    } catch (error) {
      fault(error);
      return false;
    }
  };
  if (instant) return send();
  timers.set(name, setTimeout(send, 200));
  return Promise.resolve(true);
}

function flash(name) {
  const row = document.querySelector(`[data-field="${CSS.escape(name)}"]`);
  if (!row) return;
  row.classList.remove("row--flash");
  void row.offsetWidth;
  row.classList.add("row--flash");
}

/* ---- colour ---------------------------------------------------------- */
function toHex(value) {
  let text = String(value ?? "").trim();
  if (!text || text.toLowerCase() === "off") return null;
  if (/^[0-9a-f]{3}$|^[0-9a-f]{6}$/i.test(text)) text = "#" + text;
  const probe = el("span");
  probe.style.color = text;
  if (!probe.style.color) return null;
  probe.style.display = "none";
  document.body.append(probe);
  const rgb = getComputedStyle(probe).color.match(/\d+/g);
  probe.remove();
  if (!rgb) return null;
  return "#" + rgb.slice(0, 3).map((n) => (+n).toString(16).padStart(2, "0")).join("");
}

/* ---- button mapping -------------------------------------------------- */
function parseMapping(value, field) {
  const map = Object.fromEntries(field.buttons.map((b) => [b.key.toLowerCase(), b.default]));
  const inner = /^\s*buttons\((.*)\)\s*$/is.exec(String(value ?? ""));
  for (const pair of inner ? inner[1].split(";") : []) {
    const [key, action] = pair.split("=").map((part) => part.trim());
    if (key && action && key.toLowerCase() !== "layout") map[key.toLowerCase()] = action;
  }
  return map;
}

const formatMapping = (map) =>
  "buttons(" + Object.entries(map).map(([k, v]) => k + "=" + v).join("; ") + "; layout=qwerty)";

/* ---- controls -------------------------------------------------------- */
function scale(field) {
  const floor = field.min > 0 ? field.min : field.step;
  if (!(floor > 0 && field.max / floor >= 50)) {
    return {
      attrs: { min: field.min, max: field.max, step: field.step },
      toPos: (value) => value,
      fromPos: (pos) => clamp(pos, field),
    };
  }
  // a log thumb keeps 400 and 3200 far apart instead of both hugging the left
  const span = Math.log(field.max / floor);
  const snap = (raw) => clamp(Math.round(raw / field.step) * field.step, field);
  const base = field.min > 0 ? 0 : 1;
  return {
    attrs: { min: 0, max: 1000, step: 1 },
    toPos: (value) =>
      value <= field.min
        ? 0
        : Math.round(base + ((1000 - base) * Math.log(clamp(value, field) / floor)) / span),
    fromPos: (pos) =>
      pos <= 0 ? field.min : snap(floor * Math.exp((span * (pos - base)) / (1000 - base))),
  };
}

function dropdown(select) {
  return el("span", { className: "select" }, select, icon("chevron"));
}

function buildSelect(field, id) {
  const current = String(values[field.name] ?? field.default);
  const select = el("select", { className: "field", id });
  select.append(
    ...field.options.map((option) =>
      el("option", { value: String(option), selected: String(option) === current }, humanise(option))
    )
  );
  select.onchange = () =>
    write(field.name, field.options.find((option) => String(option) === select.value), true);
  return dropdown(select);
}

function buildSlider(field, id) {
  const axis = scale(field);
  const start = values[field.name] ?? field.default ?? field.min;
  const range = el("input", { type: "range", className: "range", id, value: axis.toPos(start), ...axis.attrs });
  const num = el("input", {
    type: "number",
    className: "field num",
    value: start,
    min: field.min,
    max: field.max,
    step: field.step,
    "aria-label": field.label + " value",
  });
  range.oninput = () => {
    num.value = axis.fromPos(Number(range.value));
    write(field.name, Number(num.value));
  };
  num.onchange = () => {
    num.value = clamp(num.value, field);
    range.value = axis.toPos(Number(num.value));
    write(field.name, Number(num.value), true);
  };
  return [range, num];
}

function buildColor(field, id) {
  const start = values[field.name] ?? field.default;
  const hexValue = toHex(start) || "#ffffff";
  const swatch = el("input", { type: "color", className: "swatch", id, value: hexValue });
  const hex = el("input", {
    type: "text",
    className: "field hex",
    value: hexValue,
    maxLength: 7,
    spellcheck: false,
    "aria-label": field.label + " hex value",
  });

  swatch.oninput = () => {
    hex.value = swatch.value;
    write(field.name, swatch.value);
  };
  hex.onchange = () => {
    const parsed = toHex(hex.value);
    if (!parsed) {
      hex.value = swatch.value;
      toast("That colour isn't one I recognise.", "error");
      return;
    }
    swatch.value = hex.value = parsed;
    write(field.name, parsed, true);
  };

  if (!field.nullable) return [swatch, hex];

  const lit = String(start).toLowerCase() !== "off";
  const toggle = el("input", {
    type: "checkbox",
    className: "switch",
    checked: lit,
    "aria-label": "Enable " + field.label.toLowerCase(),
  });
  const enable = (on) => {
    swatch.disabled = hex.disabled = !on;
  };
  toggle.onchange = () => {
    enable(toggle.checked);
    write(field.name, toggle.checked ? swatch.value : "off", true);
  };
  enable(lit);
  return [toggle, swatch, hex];
}

function buildDpi(field, id) {
  const start = values[field.name] ?? field.default ?? {};
  let presets = [...(start.presets || [field.min])];
  let active = Math.min(start.active || 0, presets.length - 1);

  const axis = scale(field);
  const list = el("div", { className: "stages" });
  const add = el("button", { type: "button", className: "btn btn--ghost" }, icon("plus"), "Add stage");
  const send = () => write(field.name, { presets, active }, true);

  function stage(dpi, index) {
    const label = "Stage " + (index + 1);
    const pick = el("input", {
      type: "radio",
      className: "stage__pick",
      name: id + "-active",
      checked: index === active,
      "aria-label": "Make " + label.toLowerCase() + " active",
    });
    const range = el("input", {
      type: "range", className: "range", value: axis.toPos(dpi),
      "aria-label": label + " DPI", ...axis.attrs,
    });
    const num = el("input", {
      type: "number", className: "field num", value: dpi,
      min: field.min, max: field.max, step: field.step,
      "aria-label": label + " DPI value",
    });
    const drop = el("button", {
      type: "button", className: "btn btn--icon", disabled: presets.length < 2,
      "aria-label": "Remove " + label.toLowerCase(),
    }, icon("close"));

    pick.onchange = () => {
      active = index;
      send();
    };
    range.oninput = () => {
      num.value = axis.fromPos(Number(range.value));
      presets[index] = Number(num.value);
      write(field.name, { presets, active });
    };
    num.onchange = () => {
      num.value = clamp(num.value, field);
      range.value = axis.toPos(Number(num.value));
      presets[index] = Number(num.value);
      send();
    };
    drop.onclick = () => {
      presets.splice(index, 1);
      active = Math.min(active, presets.length - 1);
      draw();
      send();
    };
    return el("div", { className: "stage" }, pick, range, num, drop);
  }

  function draw() {
    list.replaceChildren(...presets.map(stage));
    add.disabled = presets.length >= field.max_count;
  }

  add.onclick = () => {
    presets.push(presets.at(-1) ?? field.min);
    draw();
    send();
  };
  draw();
  return [list, add];
}

function buildButtons(field, id) {
  const map = parseMapping(values[field.name] ?? field.default, field);
  const grid = el("div", { className: "map" });

  for (const button of field.buttons) {
    const key = button.key.toLowerCase();
    const selectId = id + "-" + key;
    const select = el("select", { className: "field", id: selectId });
    const known = Object.values(field.actions).flat();
    if (map[key] && !known.includes(map[key])) {
      select.append(el("option", { value: map[key], selected: true }, map[key]));
    }
    for (const [name, actions] of Object.entries(field.actions)) {
      if (!actions.length) continue;
      const group = el("optgroup", { label: name });
      group.append(
        ...actions.map((action) =>
          el("option", { value: action, selected: action === map[key] }, action)
        )
      );
      select.append(group);
    }
    select.onchange = () => {
      map[key] = select.value;
      write(field.name, formatMapping(map), true);
    };
    grid.append(
      el(
        "div",
        { className: "map__item" },
        el("label", { className: "map__name", htmlFor: selectId }, button.key),
        dropdown(select)
      )
    );
  }
  return grid;
}

function buildAction(field, id) {
  const verb = /^enable/i.test(field.description) ? "Enable" : "Apply";
  const fire = el("button", { type: "button", className: "btn", id }, icon("check"), verb);
  fire.onclick = () => write(field.name, null, true);

  // these are one-shot commands with no off switch, re-sending a colour is the way back
  const colours = fields.filter((f) => f.control === "color" && !f.nullable);
  if (!colours.length) return fire;

  const undo = el("button", { type: "button", className: "btn" }, icon("reset"), "Restore colours");
  undo.onclick = async () => {
    const done = [];
    for (const colour of colours) {
      done.push(await write(colour.name, values[colour.name] ?? colour.default, true));
    }
    if (done.every(Boolean)) toast("Your colours are back on.");
  };
  return el("div", { className: "pair" }, fire, undo);
}

function buildText(field, id) {
  const input = el("input", {
    type: "text",
    className: "field",
    id,
    value: values[field.name] ?? field.default ?? "",
    placeholder: field.hint || "",
    spellcheck: false,
  });
  input.onchange = () => write(field.name, input.value, true);
  return input;
}

const CONTROLS = {
  select: buildSelect,
  slider: buildSlider,
  color: buildColor,
  dpi: buildDpi,
  buttons: buildButtons,
  action: buildAction,
  text: buildText,
};

/* ---- rendering ------------------------------------------------------- */
function buildRow(field) {
  const id = "f-" + field.name;
  const stacked = field.control === "dpi" || field.control === "buttons";
  const labelled = ["select", "slider", "color", "text"].includes(field.control);
  const control = el("div", { className: "row__control" }, (CONTROLS[field.control] || buildText)(field, id));

  if (!labelled) {
    control.setAttribute("role", "group");
    control.setAttribute("aria-labelledby", id);
  }

  return el(
    "div",
    { className: "row" + (stacked ? " row--stack" : ""), "data-field": field.name },
    el(
      "div",
      {},
      el(labelled ? "label" : "h3", { className: "row__label", id: labelled ? null : id, htmlFor: labelled ? id : null }, field.label),
      field.description && el("p", { className: "row__hint" }, field.description),
      field.cli.length > 0 && el("p", { className: "row__cli" }, longFlag(field.cli))
    ),
    control
  );
}

function render() {
  const groups = new Map();
  for (const field of fields) {
    if (!groups.has(field.group)) groups.set(field.group, []);
    groups.get(field.group).push(field);
  }

  $("sections").replaceChildren(
    ...[...groups].map(([name, list]) =>
      el(
        "section",
        { className: "section", id: "g-" + slug(name) },
        el("div", { className: "section__head" }, icon(GROUP_ICON[name] || "other"), el("h2", { className: "section__title" }, name)),
        el("div", { className: "section__body" }, ...list.map(buildRow))
      )
    )
  );

  $("nav").replaceChildren(
    ...[...groups.keys()].map((name) =>
      el("a", { href: "#g-" + slug(name) }, icon(GROUP_ICON[name] || "other"), name)
    )
  );
  watchSections();
}

function watchSections() {
  spy?.disconnect();
  const links = new Map(
    [...$("nav").children].map((link) => [link.getAttribute("href").slice(1), link])
  );
  const visible = new Set();
  spy = new IntersectionObserver(
    (entries) => {
      for (const entry of entries) {
        visible[entry.isIntersecting ? "add" : "delete"](entry.target.id);
      }
      const current = [...$("sections").children].map((s) => s.id).find((id) => visible.has(id));
      links.forEach((link, id) => link.setAttribute("aria-current", String(id === current)));
    },
    { rootMargin: "0px 0px -60% 0px" }
  );
  for (const section of $("sections").children) spy.observe(section);
}

/* ---- status ---------------------------------------------------------- */
function showBattery(info) {
  const box = $("battery");
  box.hidden = !info || info.level == null;
  if (box.hidden) return;
  const head = $("batteryValue");
  head.replaceChildren(info.is_charging ? icon("bolt") : "", info.level + "%");
  head.toggleAttribute("data-charging", Boolean(info.is_charging));
  $("batteryFill").style.setProperty("--pct", info.level + "%");
  $("batteryFill").toggleAttribute("data-low", info.level <= 20);
  $("batteryBar").setAttribute("aria-valuenow", info.level);
}

function applyStatus(status) {
  const was = online;
  online = Boolean(status.connected);

  $("pulse").dataset.state = online ? "on" : "off";
  $("pulse").setAttribute("aria-label", online ? "Connected" : "Not connected");
  const [, full = "", mode] = /^(.*?)\s*(?:\((.*)\))?$/s.exec(status.name || "") || [];
  $("deviceName").textContent = online ? full.replace(/^SteelSeries\s+/i, "") : headline(status.kind);
  $("deviceName").title = status.name || "";
  $("deviceMeta").textContent = online ? [mode, status.id].filter(Boolean).join(" · ") : "Not connected";
  showBattery(status.battery);
  $("save").disabled = $("reset").disabled = !online;

  if (online === was) return;
  if (online) return loadSchema();

  fields = [];
  $("skeleton").hidden = true;
  $("sections").hidden = true;
  $("offline").hidden = false;
  showTrouble(status);
  $("live").textContent = "Mouse disconnected";
}

function showTrouble({ kind, error, hint, fix }) {
  $("offlineTitle").textContent = headline(kind);
  $("offlineBody").textContent = error || "Plug it in, or give it a click if it has gone to sleep.";
  $("offlineHint").textContent = hint || "";
  $("offlineHint").hidden = !hint;
  $("offlineCommand").textContent = fix || "";
  $("offlineFix").hidden = !fix;
}

async function copyFix() {
  try {
    await navigator.clipboard.writeText($("offlineCommand").textContent);
    toast("Copied.");
  } catch {
    toast("Your browser wouldn't let me copy that, so select it by hand.", "error");
  }
}

async function loadSchema() {
  try {
    const data = await api("/api/schema");
    fields = data.fields;
    values = data.values;
    render();
    $("skeleton").hidden = true;
    $("offline").hidden = true;
    $("sections").hidden = false;
    $("live").textContent = "Mouse connected, settings loaded";
  } catch (error) {
    fault(error);
  }
}

async function poll() {
  try {
    applyStatus(await api("/api/status"));
  } catch {
    applyStatus({
      connected: false,
      kind: "server",
      error: "The page can't reach the server.",
      hint: "Check the terminal you started it from, it may have stopped.",
    });
  }
}

/* ---- actions --------------------------------------------------------- */
function wireActions() {
  $("retry").onclick = poll;
  $("offlineCopy").onclick = copyFix;

  $("save").onclick = async () => {
    const button = $("save");
    button.disabled = true;
    try {
      await api("/api/save", {});
      toast("Saved to the mouse's onboard memory.");
    } catch (error) {
      fault(error);
    }
    button.disabled = !online;
  };

  const reset = $("reset");
  const label = reset.querySelector("span");
  let armed = false;
  const disarm = () => {
    armed = false;
    reset.classList.remove("btn--danger");
    label.textContent = "Reset defaults";
  };

  reset.onclick = async () => {
    if (!armed) {
      armed = true;
      reset.classList.add("btn--danger");
      label.textContent = "Tap again to confirm";
      setTimeout(disarm, 4000);
      return;
    }
    disarm();
    try {
      values = (await api("/api/reset", {})).values;
      render();
      toast("Every setting is back to factory defaults.");
    } catch (error) {
      fault(error);
    }
  };
}

wireActions();
poll();
setInterval(() => document.visibilityState === "visible" && poll(), 5000);
document.addEventListener("visibilitychange", () => document.visibilityState === "visible" && poll());
