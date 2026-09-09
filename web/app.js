"use strict";

const model = {
  accounts: [],
  catalog: { achievements: [], characters: [], categories: {} },
  state: null,
  accountId: null,
  slot: null,
  characterOrder: "unfinished",
};

const viewRoot = document.querySelector("#view");
const statusRoot = document.querySelector("#app-status");
const slotStatus = document.querySelector("#slot-status");
const dialog = document.querySelector("#update-dialog");
const accountSelect = document.querySelector("#account-select");
const slotSelect = document.querySelector("#slot-select");
const updateStatus = document.querySelector("#update-status");
const updateButton = document.querySelector("#run-update");
const toast = document.querySelector("#toast");

const escapeHtml = (value) => String(value ?? "").replace(/[&<>'"]/g, (character) => ({
  "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
})[character]);

const formatTime = (value) => {
  if (!value) return "时间未知";
  const date = new Date(value);
  return Number.isNaN(date.valueOf()) ? "时间未知" : date.toLocaleString("zh-CN", { hour12: false });
};

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const payload = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(payload?.error?.message || `请求失败（${response.status}）`);
  }
  return payload;
}

function activeAchievements() {
  const hasProgress = Boolean(model.state?.achievements?.length);
  const source = hasProgress ? model.state.achievements : model.catalog.achievements;
  return source.map((item) => ({
    ...item,
    steam_unlocked: hasProgress ? Boolean(item.steam_unlocked) : null,
    status: hasProgress ? (item.steam_unlocked ? "unlocked" : "locked") : "unknown",
  }));
}

function relationItems(characterId) {
  return activeAchievements().filter((achievement) =>
    (achievement.character_relations || []).some((relation) => relation.character_id === characterId));
}

function categoryLabel(categoryId) {
  return model.catalog.categories?.[categoryId]?.name_zh || categoryId;
}

function pageHeader(kicker, title, copy, aside = "") {
  return `<section class="page-head">
    <div><p class="eyebrow">${escapeHtml(kicker)}</p><h1>${escapeHtml(title)}</h1><p class="page-copy">${escapeHtml(copy)}</p></div>
    ${aside}
  </section>`;
}

function achievementList(items) {
  if (!items.length) return `<div class="empty-state">这里暂时没有符合条件的成就。</div>`;
  return `<div class="achievement-list">${items.map((item) => {
    const unlocked = item.status === "unlocked";
    const known = item.status !== "unknown";
    const unlockCondition = item.unlock_condition_zh || item.unlock_condition_en || item.description;
    const tags = (item.categories || []).map((id) =>
      `<span class="tag">${escapeHtml(categoryLabel(id))}</span>`).join("");
    return `<article class="achievement-row ${escapeHtml(item.status)}">
      <span class="status-mark" aria-label="${known ? (unlocked ? "已解锁" : "未解锁") : "尚未读取"}">${known ? (unlocked ? "✓" : "○") : "·"}</span>
      <div>
        <h3>${escapeHtml(item.name_zh || item.name_en)}</h3>
        <p>${escapeHtml(unlockCondition || "暂无解锁说明")}</p>
        <div class="tag-list">${tags}</div>
      </div>
      <span class="achievement-id">#${escapeHtml(item.id)}</span>
    </article>`;
  }).join("")}</div>`;
}

function nextTarget() {
  const locked = activeAchievements().filter((item) => !item.steam_unlocked);
  return locked.find((item) => (item.character_relations || []).length) || locked[0] || null;
}

function renderCharacters() {
  const achievements = activeAchievements();
  const hasProgress = Boolean(model.state?.achievements?.length);
  const unlocked = achievements.filter((item) => item.steam_unlocked).length;
  const target = hasProgress ? nextTarget() : null;
  const targetRelation = target?.character_relations?.[0];
  const targetCharacter = model.catalog.characters.find((item) => item.id === targetRelation?.character_id);
  const aside = `<div class="total-progress"><strong>${hasProgress ? unlocked : "—"}</strong> / ${achievements.length || "—"}<br>STEAM ACHIEVEMENTS</div>`;
  const note = !hasProgress
    ? `<section class="next-note" aria-label="首次更新"><span class="note-pin" aria-hidden="true"></span><div><small>LOCAL PROGRESS</small><strong>尚未读取进度</strong></div><button class="text-button" type="button" data-open-update>选择账户与存档 →</button></section>`
    : target
    ? `<section class="next-note" aria-label="下一局建议"><span class="note-pin" aria-hidden="true"></span><div><small>NEXT RUN</small><strong>${escapeHtml(targetCharacter?.name_zh || "下一目标")} · ${escapeHtml(target.name_zh || target.name_en)}</strong></div>${targetCharacter ? `<button class="text-button" type="button" data-character="${escapeHtml(targetCharacter.id)}">查看角色目标 →</button>` : ""}</section>`
    : `<section class="next-note"><span class="note-pin" aria-hidden="true"></span><div><small>NEXT RUN</small><strong>当前目录中的成就均已完成</strong></div></section>`;
  const characterRows = model.catalog.characters.map((character, index) => {
    const related = relationItems(character.id);
    const complete = related.filter((item) => item.steam_unlocked).length;
    return { character, related, complete, remaining: related.length - complete, index };
  });
  if (hasProgress && model.characterOrder === "unfinished") {
    characterRows.sort((a, b) => b.remaining - a.remaining || a.index - b.index);
  }
  const cards = characterRows.map(({ character, related, complete, remaining }) => {
    const percent = related.length ? Math.round((complete / related.length) * 100) : 0;
    return `<button class="character-card ${hasProgress && related.length && complete === related.length ? "complete" : ""}" type="button" data-character="${escapeHtml(character.id)}" data-tainted="${Boolean(character.tainted)}">
      <span class="character-sigil" aria-hidden="true">${escapeHtml(character.sigil)}</span>
      <span><h3>${escapeHtml(character.name_zh)}</h3><p>${hasProgress ? `${complete} / ${related.length} · ${Math.max(0, remaining)} 未完成` : "尚未读取进度"}</p><span class="progress-track" aria-label="${hasProgress ? `完成 ${percent}%` : "进度未知"}"><span style="width:${hasProgress ? percent : 0}%"></span></span></span>
    </button>`;
  }).join("");
  const sorting = `<label class="inline-control" for="character-order">排序<select id="character-order" ${hasProgress ? "" : "disabled"}><option value="unfinished" ${model.characterOrder === "unfinished" ? "selected" : ""}>未完成优先</option><option value="game" ${model.characterOrder === "game" ? "selected" : ""}>角色原顺序</option></select></label>`;
  viewRoot.innerHTML = `${pageHeader("CHARACTER ARCHIVE", "今天打谁？", "先选角色，再看这局能推进哪些解锁。", aside)}${note}<div class="section-head"><h2>角色档案</h2>${sorting}</div><section class="character-grid" aria-label="角色列表">${cards}</section>`;
}

function renderCharacter(characterId) {
  const character = model.catalog.characters.find((item) => item.id === characterId);
  if (!character) {
    viewRoot.innerHTML = `<div class="error-state"><strong>没有这个角色</strong>请从角色首页重新选择。</div>`;
    return;
  }
  const items = relationItems(characterId).sort((a, b) => Number(a.steam_unlocked) - Number(b.steam_unlocked) || a.id - b.id);
  const hasProgress = Boolean(model.state?.achievements?.length);
  const complete = items.filter((item) => item.steam_unlocked).length;
  const defaultStatus = "all";
  viewRoot.innerHTML = `<button class="back-button" type="button" data-view-link="characters">← 返回角色</button>${pageHeader(character.tainted ? "TAINTED CHARACTER" : "CHARACTER", character.name_zh, hasProgress ? `${complete} / ${items.length} 项相关成就已完成` : "尚未读取进度", `<div class="total-progress"><strong>${hasProgress ? complete : "—"}</strong> / ${items.length}</div>`)}
    <div class="section-head"><h2>相关成就</h2><span>未解锁在前</span></div>
    <div class="character-filters">
      <label class="inline-control" for="character-status-filter">状态<select id="character-status-filter"><option value="locked" ${defaultStatus === "locked" ? "selected" : ""}>未解锁</option><option value="all" ${defaultStatus === "all" ? "selected" : ""}>全部</option><option value="unlocked">已解锁</option></select></label>
      <label class="inline-control" for="relation-filter">关系<select id="relation-filter"><option value="all">全部关系</option><option value="required_character">必须使用该角色</option><option value="unlocks_character">解锁该角色</option><option value="starting_item_for_character">初始物品</option><option value="related_character">其他明确关系</option></select></label>
    </div><div id="character-results"></div>`;
  const updateResults = () => {
    const status = document.querySelector("#character-status-filter").value;
    const relationType = document.querySelector("#relation-filter").value;
    const filtered = items.filter((item) => {
      const relationMatch = relationType === "all" || (item.character_relations || []).some(
        (relation) => relation.character_id === characterId && relation.type === relationType);
      return (status === "all" || item.status === status) && relationMatch;
    });
    document.querySelector("#character-results").innerHTML = achievementList(filtered);
  };
  ["#character-status-filter", "#relation-filter"].forEach((selector) =>
    document.querySelector(selector).addEventListener("input", updateResults));
  updateResults();
}

function renderCategories(selectedId = null) {
  const achievements = activeAchievements();
  const cards = Object.entries(model.catalog.categories).map(([id, category]) => {
    const items = achievements.filter((item) => (item.categories || []).includes(id));
    const complete = items.filter((item) => item.steam_unlocked).length;
    return `<button class="category-card" type="button" data-category="${escapeHtml(id)}"><h2>${escapeHtml(category.name_zh)}</h2><p>${escapeHtml(category.description)}</p><span class="category-count">${complete} / ${items.length}</span></button>`;
  }).join("");
  let detail = "";
  if (selectedId && model.catalog.categories[selectedId]) {
    const items = achievements.filter((item) => (item.categories || []).includes(selectedId))
      .sort((a, b) => Number(a.steam_unlocked) - Number(b.steam_unlocked) || a.id - b.id);
    detail = `<div class="section-head"><h2>${escapeHtml(model.catalog.categories[selectedId].name_zh)}</h2><span>${items.length} 项</span></div>${achievementList(items)}`;
  }
  viewRoot.innerHTML = `${pageHeader("UNLOCK METHODS", "按解锁方式浏览", "同一成就可以同时属于角色、路线或特殊单局等多个分类。")}<section class="category-grid" aria-label="成就分类">${cards}</section>${detail}`;
}

function renderAll() {
  const categories = Object.entries(model.catalog.categories).map(([id, category]) =>
    `<option value="${escapeHtml(id)}">${escapeHtml(category.name_zh)}</option>`).join("");
  viewRoot.innerHTML = `${pageHeader("COMPLETE INDEX", "全部成就", "按中文、英文或数字 ID 搜索，必要时再组合状态与分类。")}
    <div class="toolbar" role="search">
      <input id="achievement-search" type="search" placeholder="搜索名称、说明或 ID" aria-label="搜索成就">
      <select id="status-filter" aria-label="解锁状态"><option value="all">全部状态</option><option value="locked">未解锁</option><option value="unlocked">已解锁</option></select>
      <select id="category-filter" aria-label="解锁方式"><option value="all">全部分类</option>${categories}</select>
    </div><div id="all-results"></div>`;
  const updateResults = () => {
    const query = document.querySelector("#achievement-search").value.trim().toLocaleLowerCase();
    const status = document.querySelector("#status-filter").value;
    const category = document.querySelector("#category-filter").value;
    const items = activeAchievements().filter((item) => {
      const haystack = `${item.id} ${item.name_zh || ""} ${item.name_en || ""} ${item.description || ""} ${item.unlock_condition_zh || ""} ${item.unlock_condition_en || ""}`.toLocaleLowerCase();
      return (!query || haystack.includes(query))
        && (status === "all" || item.status === status)
        && (category === "all" || (item.categories || []).includes(category));
    }).sort((a, b) => Number(a.steam_unlocked) - Number(b.steam_unlocked) || a.id - b.id);
    document.querySelector("#all-results").innerHTML = achievementList(items);
  };
  ["#achievement-search", "#status-filter", "#category-filter"].forEach((selector) =>
    document.querySelector(selector).addEventListener("input", updateResults));
  updateResults();
}

function route() {
  const hash = location.hash.replace(/^#/, "") || "characters";
  const [section, id] = hash.split("/");
  document.querySelectorAll("[data-view]").forEach((button) => {
    const active = button.dataset.view === section || (section === "character" && button.dataset.view === "characters") || (section === "category" && button.dataset.view === "categories");
    if (active) button.setAttribute("aria-current", "page");
    else button.removeAttribute("aria-current");
  });
  if (section === "character") renderCharacter(id);
  else if (section === "categories") renderCategories();
  else if (section === "category") renderCategories(id);
  else if (section === "all") renderAll();
  else renderCharacters();
}

function accountById(id) {
  return model.accounts.find((account) => account.id === id);
}

function fillSlots() {
  const account = accountById(accountSelect.value);
  slotSelect.innerHTML = account?.slots?.length
    ? account.slots.map((slot) => `<option value="${slot.number}">档位 ${slot.number} · ${escapeHtml(formatTime(slot.modified_at))}</option>`).join("")
    : `<option value="">没有可用存档</option>`;
  updateButton.disabled = !account?.slots?.length;
}

function fillUpdateDialog() {
  accountSelect.innerHTML = model.accounts.length
    ? model.accounts.map((account) => `<option value="${escapeHtml(account.id)}">账户 ${escapeHtml(account.id)}</option>`).join("")
    : `<option value="">未找到 Isaac 本地数据</option>`;
  if (model.accountId) accountSelect.value = model.accountId;
  fillSlots();
  if (model.slot) slotSelect.value = String(model.slot);
  updateStatus.textContent = model.accounts.length ? "" : "请确认 Steam 已安装且本机存在 AppID 250900 的数据。";
}

function openUpdateDialog() {
  fillUpdateDialog();
  dialog.showModal();
}

function showToast(message) {
  toast.textContent = message;
  toast.classList.add("show");
  window.setTimeout(() => toast.classList.remove("show"), 3200);
}

async function loadSnapshot() {
  if (!model.accountId || !model.slot) return;
  try {
    model.state = await api(`/api/state?account_id=${encodeURIComponent(model.accountId)}&slot=${model.slot}`);
  } catch (error) {
    if (!String(error.message).includes("还没有本地进度快照")) throw error;
    model.state = null;
  }
}

async function boot() {
  statusRoot.textContent = "正在读取本地目录…";
  try {
    const [accounts, catalog] = await Promise.all([api("/api/accounts"), api("/api/catalog")]);
    model.accounts = accounts.accounts || [];
    model.catalog = catalog;
    const account = model.accounts[0];
    if (account?.slots?.length) {
      const slot = [...account.slots].sort((a, b) => new Date(b.modified_at) - new Date(a.modified_at))[0];
      model.accountId = account.id;
      model.slot = slot.number;
      await loadSnapshot();
    }
    statusRoot.textContent = catalog.warning || "";
    slotStatus.textContent = model.state
      ? `档位 ${model.slot} · ${formatTime(model.state.generated_at)}`
      : "等待首次更新";
    route();
  } catch (error) {
    statusRoot.textContent = "";
    viewRoot.innerHTML = `<div class="error-state"><strong>无法读取本地服务</strong>${escapeHtml(error.message)}<br>请从 start.ps1 启动页面后重试。</div>`;
  }
}

document.querySelectorAll("[data-view]").forEach((button) => button.addEventListener("click", () => {
  location.hash = button.dataset.view;
}));

viewRoot.addEventListener("click", (event) => {
  const character = event.target.closest("[data-character]");
  const category = event.target.closest("[data-category]");
  const viewLink = event.target.closest("[data-view-link]");
  const openUpdate = event.target.closest("[data-open-update]");
  if (openUpdate) openUpdateDialog();
  else if (character) location.hash = `character/${character.dataset.character}`;
  else if (category) location.hash = `category/${category.dataset.category}`;
  else if (viewLink) location.hash = viewLink.dataset.viewLink;
});

viewRoot.addEventListener("change", (event) => {
  if (event.target.id === "character-order") {
    model.characterOrder = event.target.value;
    renderCharacters();
  }
});

document.querySelector("#open-update").addEventListener("click", openUpdateDialog);
document.querySelector("#close-update").addEventListener("click", () => dialog.close());
document.querySelector("#cancel-update").addEventListener("click", () => dialog.close());
accountSelect.addEventListener("change", fillSlots);
document.querySelector("#update-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const accountId = accountSelect.value;
  const slot = Number(slotSelect.value);
  updateButton.disabled = true;
  updateStatus.textContent = "正在只读解析本地文件…";
  try {
    model.state = await api("/api/update", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ account_id: accountId, slot }),
    });
    model.accountId = accountId;
    model.slot = slot;
    slotStatus.textContent = `档位 ${slot} · ${formatTime(model.state.generated_at)}`;
    dialog.close();
    route();
    const added = model.state.changes?.new_steam_unlocks?.length || 0;
    showToast(added ? `更新完成：新增 ${added} 项 Steam 成就` : "更新完成：进度未变化");
  } catch (error) {
    updateStatus.textContent = error.message;
  } finally {
    updateButton.disabled = false;
  }
});

window.addEventListener("hashchange", route);
boot();
