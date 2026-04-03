let API_URL = localStorage.getItem("iot_api_url") || "";
let currentThing = null;
let refreshTimer = null;

// Init
if (API_URL) {
  document.getElementById("apiUrl").value = API_URL;
  loadThings();
}

function saveApiUrl() {
  API_URL = document.getElementById("apiUrl").value.replace(/\/+$/, "");
  localStorage.setItem("iot_api_url", API_URL);
  loadThings();
}

async function api(path, options = {}) {
  const res = await fetch(`${API_URL}${path}`, options);
  if (!res.ok) throw new Error(`API error: ${res.status}`);
  return res.json();
}

async function loadThings() {
  const el = document.getElementById("thingList");
  el.innerHTML = "加载中...";
  try {
    const things = await api("/things");
    if (things.length === 0) {
      el.innerHTML = "暂无设备";
      return;
    }
    el.innerHTML = things
      .map(
        (t) =>
          `<button class="thing-btn" onclick="selectThing('${t.thingName}')">${t.thingName}</button>`
      )
      .join("");
  } catch (e) {
    el.innerHTML = `加载失败: ${e.message}`;
  }
}

async function selectThing(thingName) {
  currentThing = thingName;
  document.querySelectorAll(".thing-btn").forEach((btn) => {
    btn.classList.toggle("active", btn.textContent === thingName);
  });
  document.getElementById("selectedThing").textContent = `- ${thingName}`;
  document.getElementById("shadowPanel").style.display = "block";
  document.getElementById("historyPanel").style.display = "block";

  await refreshShadow();
  await loadHistory();

  // Auto refresh every 5s
  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(refreshShadow, 5000);
}

async function refreshShadow() {
  if (!currentThing) return;
  try {
    const shadow = await api(`/things/${currentThing}/shadow`);
    renderShadow(shadow);
  } catch (e) {
    document.getElementById("shadowGrid").innerHTML = `<p>获取失败: ${e.message}</p>`;
  }
}

function renderShadow(shadow) {
  const reported = shadow.state?.reported || {};
  const desired = shadow.state?.desired || {};

  // Render reported state cards
  const grid = document.getElementById("shadowGrid");
  const cards = [
    { label: "温度", value: reported.temperature != null ? `${reported.temperature}°C` : "-" },
    { label: "湿度", value: reported.humidity != null ? `${reported.humidity}%` : "-" },
    { label: "固件版本", value: reported.firmware || "-" },
    {
      label: "状态",
      value: reported.status
        ? `<span class="status ${reported.status}"></span>${reported.status}`
        : "-",
    },
  ];
  grid.innerHTML = cards
    .map(
      (c) => `<div class="shadow-card"><label>${c.label}</label><div class="value">${c.value}</div></div>`
    )
    .join("");

  // Render controls (toggles for switch-like properties)
  const controls = document.getElementById("controls");
  const switchProps = [
    { key: "power", label: "电源开关" },
    { key: "led", label: "LED 指示灯" },
    { key: "nightMode", label: "夜间模式" },
    { key: "autoMode", label: "自动模式" },
  ];

  controls.innerHTML = switchProps
    .map((prop) => {
      const isOn = desired[prop.key] === true || (desired[prop.key] == null && reported[prop.key] === true);
      return `
        <div class="control-item">
          <label>${prop.label}</label>
          <label class="toggle">
            <input type="checkbox" ${isOn ? "checked" : ""} onchange="toggleProp('${prop.key}', this.checked)" />
            <span class="slider"></span>
          </label>
        </div>`;
    })
    .join("");
}

async function toggleProp(key, value) {
  if (!currentThing) return;
  try {
    await api(`/things/${currentThing}/shadow`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ desired: { [key]: value } }),
    });
    // Refresh after a short delay to let device process
    setTimeout(refreshShadow, 500);
  } catch (e) {
    alert(`更新失败: ${e.message}`);
  }
}

async function loadHistory() {
  if (!currentThing) return;
  try {
    const items = await api(`/things/${currentThing}/history?limit=20`);
    const tbody = document.getElementById("historyBody");
    tbody.innerHTML = items
      .map((item) => {
        const time = new Date(item.timestamp).toLocaleString("zh-CN");
        const r = item.reported || {};
        return `<tr>
          <td>${time}</td>
          <td>${r.temperature != null ? r.temperature + "°C" : "-"}</td>
          <td>${r.humidity != null ? r.humidity + "%" : "-"}</td>
          <td>${r.status ? `<span class="status ${r.status}"></span>${r.status}` : "-"}</td>
        </tr>`;
      })
      .join("");
  } catch (e) {
    document.getElementById("historyBody").innerHTML = `<tr><td colspan="4">加载失败: ${e.message}</td></tr>`;
  }
}
