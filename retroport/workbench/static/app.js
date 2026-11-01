const $ = id => document.getElementById(id);
let polling = null;
let initialized = false;

async function api(path, body) {
  const options = body === undefined ? {} : {method: "POST", headers: {"Content-Type": "application/json"}, body: JSON.stringify(body)};
  const response = await fetch(path, options);
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `请求失败（${response.status}）`);
  return data;
}

function values() {
  return {data: $("data-dir").value.trim(), input: $("input").value.trim(), phys_dir: $("phys-dir").value.trim(),
          output: $("output").value.trim(), prefix: $("prefix").value.trim(), recursive: $("recursive").checked,
          kind: $("kind").value};
}

function fill(settings) {
  $("data-dir").value = settings.data || "";
  $("input").value = settings.input || "";
  $("phys-dir").value = settings.phys_dir || "";
  $("output").value = settings.output || "";
  $("prefix").value = settings.prefix || "";
  $("recursive").checked = settings.recursive !== false;
  $("kind").value = settings.kind || "creature";
  updateKind();
}

function updateKind() {
  const names = {creature: "WXLCreaturePhysics.phy2", spell: "WXLSpellPhysics.phy2", equipment: "WXLEquipPlusPhysics.phy2"};
  const name = names[$("kind").value] || names.creature;
  $("output-table").textContent = `输出目录\\DBFilesClient\\${name}`;
  $("generate").textContent = `生成 ${name}`;
}

function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toast.timer);
  toast.timer = setTimeout(() => $("toast").hidden = true, 7000);
}

function textCell(row, text, cls = "") {
  const cell = document.createElement("td");
  cell.textContent = text;
  if (cls) cell.className = cls;
  row.appendChild(cell);
}

function showScan(scan) {
  if (!scan) return;
  $("scan-panel").hidden = false;
  $("scan-summary").textContent = `${scan.total} 个文件：${scan.ready} 个可生成，${scan.none} 个无物理，${scan.failed} 个失败`;
  $("scan-summary").className = "status " + (scan.failed ? "warn" : "good");
  const body = $("scan-rows");
  body.replaceChildren();
  for (const item of scan.items) {
    const row = document.createElement("tr");
    textCell(row, item.name);
    const label = item.state === "ready" ? "可生成" : item.state === "none" ? "无物理" : "读取失败";
    textCell(row, label, `tag ${item.state}`);
    textCell(row, item.source || "");
    textCell(row, (item.keys || []).join("\n"));
    body.appendChild(row);
  }
}

function showResult(job) {
  const box = $("result");
  if (!job || job.state === "idle" || job.state === "running") return;
  if (job.state === "failed") {
    box.hidden = false;
    box.className = "result error";
    box.textContent = `${job.name}失败：${job.error || "未知错误"}`;
    return;
  }
  if (job.name === "扫描") showScan(job.result);
  if (job.name !== "生成物理表") return;
  const r = job.result || {};
  box.hidden = false;
  box.className = "result";
  box.replaceChildren();
  const title = document.createElement("div");
  title.innerHTML = `<b>已生成${r.kind_label || ""}物理表：当前共 ${r.rows || 0} 条记录，本次处理 ${r.models || 0} 个模型。</b>`;
  const path = document.createElement("div");
  path.textContent = r.table || "";
  box.append(title, path);
  if (r.existing_rows > 0) {
    const merged = document.createElement("div");
    merged.textContent = `增量合并：保留 ${r.kept || 0} 条旧记录，新增 ${r.added || 0} 条，更新 ${r.updated || 0} 条同键记录。`;
    box.appendChild(merged);
  }
  if (r.backup) {
    const backup = document.createElement("div");
    backup.className = "muted";
    backup.textContent = `旧表备份：${r.backup}`;
    box.appendChild(backup);
  }
}

function render(data) {
  if (!initialized) {
    fill(data.settings);
    initialized = true;
  }
  $("version").textContent = data.app.version ? `v${data.app.version}` : "";
  const tools = data.tools;
  $("tools-status").textContent = tools.downloaded ? "已下载，可使用" : "尚未下载";
  $("tools-status").className = "status " + (tools.downloaded ? "good" : "warn");
  $("tools-path").textContent = tools.path;
  const job = data.job || {state: "idle"};
  const busy = job.state === "running";
  for (const id of ["download", "scan", "generate"]) $(id).disabled = busy;
  document.querySelectorAll("[data-pick]").forEach(b => b.disabled = busy || !data.picker);
  const state = $("state");
  state.className = "pill " + (busy ? "busy" : job.state === "failed" ? "failed" : tools.downloaded ? "ready" : "");
  state.textContent = busy ? `${job.name}进行中…` : job.state === "failed" ? "任务失败" : tools.downloaded ? "物理工具就绪" : "等待下载物理工具";
  $("log").textContent = (data.log || []).join("\n") || "暂无日志";
  showResult(job);
}

async function refresh(schedule = true) {
  try {
    const data = await api("/api/status");
    render(data);
    if (schedule && data.job.state === "running") {
      clearTimeout(polling);
      polling = setTimeout(() => refresh(true), 700);
    }
  } catch (e) {
    toast(e.message);
  }
}

async function action(path, body) {
  try {
    const data = await api(path, body);
    render(data);
    clearTimeout(polling);
    polling = setTimeout(() => refresh(true), 400);
  } catch (e) {
    toast(e.message);
  }
}

$("download").addEventListener("click", () => action("/api/tools/download", values()));
$("scan").addEventListener("click", () => action("/api/scan", values()));
$("generate").addEventListener("click", () => action("/api/generate", values()));
$("open-output").addEventListener("click", async () => {
  try { await api("/api/open-output", {}); } catch (e) { toast(e.message); }
});

document.querySelectorAll("[data-pick]").forEach(button => button.addEventListener("click", async () => {
  try {
    const data = await api("/api/pick", {kind: button.dataset.pick});
    if (!data.path) return;
    const target = {"model": "input", "input-folder": "input", "phys": "phys-dir", "output": "output", "data": "data-dir"}[button.dataset.pick];
    $(target).value = data.path;
    const status = await api("/api/settings", values());
    render(status);
    if (button.dataset.pick === "data") $("output").value = status.settings.output || "";
  } catch (e) { toast(e.message); }
}));

for (const id of ["input", "phys-dir", "output", "prefix", "recursive"]) {
  $(id).addEventListener("change", () => api("/api/settings", values()).catch(e => toast(e.message)));
}
$("kind").addEventListener("change", () => {
  updateKind();
  api("/api/settings", values()).catch(e => toast(e.message));
});
$("data-dir").addEventListener("change", async () => {
  try {
    const status = await api("/api/settings", values());
    render(status);
    $("output").value = status.settings.output || "";
  } catch (e) { toast(e.message); }
});

window.addEventListener("beforeunload", () => {
  // 即使用户输入路径后直接关窗（没有触发 change），也保存最后一次界面值。
  navigator.sendBeacon("/api/settings", new Blob([JSON.stringify(values())], {type: "application/json"}));
  navigator.sendBeacon("/api/bye", "{}");
});
setInterval(() => api("/api/hello", {}).catch(() => {}), 60000);
api("/api/hello", {}).catch(() => {});
refresh(false);
