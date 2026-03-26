const state = {
  status: null,
  logs: [],
  config: null,
  appControl: null,
};

function byId(id) {
  return document.getElementById(id);
}

function text(value, fallback = "-") {
  return value === null || value === undefined || value === "" ? fallback : value;
}

function boolText(value) {
  if (value === null || value === undefined) return "-";
  return value ? "yes" : "no";
}

function egressText(egress) {
  if (!egress) return "未验证";
  const region = [egress.countryCode, egress.country, egress.city].filter(Boolean).join(" / ");
  return `${text(egress.ip)} · ${region || "地区未知"}`;
}

function egressMeta(egress) {
  if (!egress) return "-";
  return [egress.asn, egress.org, egress.source].filter(Boolean).join(" · ");
}

function checkLabel(check) {
  const labels = {
    tailscaleConnected: "Tailscale 已连接",
    miniReachable: "mini 可达",
    proxyReachable: "代理端口可达",
    upstreamReachableViaProxy: "代理上游可达",
    expectedRegionMatched: "代理出口地区符合预期",
    directEgressAvailable: "直连出口可用",
    directRegionMatched: "直连出口地区符合预期",
    proxyBypassed: "已绕过 mini 代理",
  };
  return labels[check.key] || check.key;
}

function modeLabel(mode) {
  const labels = {
    normal: "默认直连",
    studio: "工作室代理",
    studio_direct: "工作室直连",
    travel: "外出",
    fallback: "临时保底",
  };
  return labels[mode] || mode;
}

function renderStatus() {
  const status = state.status;
  if (!status) return;

  byId("summaryText").textContent = text(status.summary, "未验证");
  byId("summaryTime").textContent = status.lastVerifyAt
    ? `最近验证：${status.lastVerifyAt}`
    : "尚未完成验证";

  byId("modeBadge").textContent = modeLabel(status.networkMode);
  byId("devProxyPolicy").textContent = text(status.devProxyPolicy);
  byId("routeMode").textContent = text(status.routeMode);
  byId("criticalOps").textContent = text(status.criticalOpsRecommendation);
  byId("modeChangedAt").textContent = status.lastModeChangeAt
    ? `最近切换：${status.lastModeChangeAt}`
    : "尚未切换";
  byId("browserNotice").textContent = text(status.browserNotice);

  byId("connectionProfile").textContent = text(status.connectionProfile);
  byId("tailscaleState").textContent = text(status.tailscale?.state);
  byId("miniReachable").textContent = `${boolText(status.mini?.reachable)} · ${text(status.mini?.host)}`;
  byId("proxyReachable").textContent = `${boolText(status.proxy?.reachable)} · ${text(status.proxy?.host)}:${text(status.proxy?.port)}`;
  byId("proxyType").textContent = text(status.proxy?.type);

  const verification = status.lastVerification || {};
  byId("directEgressText").textContent = egressText(verification.directEgress);
  byId("directEgressMeta").textContent = egressMeta(verification.directEgress);
  byId("proxiedEgressText").textContent = egressText(verification.proxiedEgress);
  byId("proxiedEgressMeta").textContent = egressMeta(verification.proxiedEgress);

  byId("devProxySession").textContent = text(status.devProxySession);
  byId("devProxyEnvPath").textContent = text(status.devProxyFiles?.envPath);
  byId("devProxyShellPath").textContent = text(status.devProxyFiles?.shellPath);
  byId("devProxyCommand").textContent = text(status.devProxyFiles?.command);

  const checksList = byId("checksList");
  checksList.innerHTML = "";
  const checks = verification.checks || [];
  if (!checks.length) {
    checksList.innerHTML = "<li>尚未完成完整验证</li>";
  } else {
    checks.forEach((check) => {
      const li = document.createElement("li");
      li.textContent = `${check.ok ? "OK" : "FAIL"} · ${checkLabel(check)}`;
      checksList.appendChild(li);
    });
  }

  const errorsNode = byId("verifyErrors");
  errorsNode.innerHTML = "";
  const errors = verification.errors || {};
  const entries = Object.entries(errors);
  if (!entries.length) {
    errorsNode.innerHTML = '<div class="log-item">当前没有额外错误详情</div>';
  } else {
    entries.forEach(([key, value]) => {
      const div = document.createElement("div");
      div.className = "error-item";
      div.textContent = `${key}: ${value}`;
      errorsNode.appendChild(div);
    });
  }
}

function renderAppControl() {
  const app = state.appControl;
  if (!app) return;

  byId("appServiceStatus").textContent = app.service?.running
    ? `运行中 · PID ${text(app.service?.pid)}`
    : "已停止";
  byId("guiProxyStatus").textContent = app.guiProxy?.enabled ? "已注入" : "未注入";
  byId("codexAppStatus").textContent = app.apps?.codex?.running ? "运行中" : "未运行";
  byId("antigravityAppStatus").textContent = app.apps?.antigravity?.running ? "运行中" : "未运行";
  byId("guiProxyValue").textContent = text(
    app.guiProxy?.httpProxy || app.guiProxy?.allProxy,
    "未注入"
  );
  byId("appControlNotes").textContent = (app.notes || []).join(" ");
}

function renderLogs() {
  const logsList = byId("logsList");
  logsList.innerHTML = "";
  if (!state.logs.length) {
    logsList.innerHTML = '<div class="log-item">暂无日志</div>';
    return;
  }
  state.logs.forEach((item) => {
    const div = document.createElement("div");
    div.className = "log-item";
    div.innerHTML = `<strong>${text(item.type)}</strong> ${text(item.summary)}<br><span class="muted">${text(item.ts)}</span>`;
    logsList.appendChild(div);
  });
}

function renderConfig() {
  const config = state.config;
  if (!config) return;
  const form = byId("configForm");
  form.studioMiniHost.value = text(config.profiles?.studio?.miniHost, "");
  form.studioProxyHost.value = text(config.profiles?.studio?.proxy?.host, "");
  form.studioProxyPort.value = text(config.profiles?.studio?.proxy?.port, "");
  form.studioProxyType.value = text(config.profiles?.studio?.proxy?.type, "http");
  form.travelMiniHost.value = text(config.profiles?.travel?.miniHost, "");
  form.travelProxyHost.value = text(config.profiles?.travel?.proxy?.host, "");
  form.travelProxyPort.value = text(config.profiles?.travel?.proxy?.port, "");
  form.travelProxyType.value = text(config.profiles?.travel?.proxy?.type, "http");
  form.expectedRegion.value = text(config.expectedRegion, "");
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
    },
    ...options,
  });
  const payload = await response.json();
  if (!response.ok) {
    throw new Error(payload.message || payload.error || "请求失败");
  }
  return payload;
}

async function refreshAll() {
  const [status, logs, config, appControl] = await Promise.all([
    fetchJson("/api/status"),
    fetchJson("/api/logs"),
    fetchJson("/api/config"),
    fetchJson("/api/app-control/status"),
  ]);
  state.status = status;
  state.logs = logs.items || [];
  state.config = config;
  state.appControl = appControl;
  renderStatus();
  renderAppControl();
  renderLogs();
  renderConfig();
}

function setBusy(textValue) {
  byId("busyState").textContent = textValue;
}

function setActionResult(message, isError = false) {
  const node = byId("actionResult");
  node.textContent = message;
  node.style.color = isError ? "#ffb3b3" : "#dce9f7";
}

function setAppActionResult(message, isError = false) {
  const node = byId("appActionResult");
  node.textContent = message;
  node.style.color = isError ? "#ffb3b3" : "#dce9f7";
}

async function switchMode(mode) {
  setBusy("处理中");
  try {
    const payload = await fetchJson(`/api/mode/${mode}`, {
      method: "POST",
      body: JSON.stringify({}),
    });
    setActionResult(`模式已切到 ${modeLabel(mode)}`);
    state.status = payload.status;
    await refreshAll();
  } catch (error) {
    setActionResult(error.message, true);
  } finally {
    setBusy("空闲");
  }
}

async function verifyNow() {
  setBusy("验证中");
  try {
    const payload = await fetchJson("/api/verify", {
      method: "POST",
      body: JSON.stringify({}),
    });
    setActionResult(payload.summary || "验证完成");
    await refreshAll();
  } catch (error) {
    setActionResult(error.message, true);
  } finally {
    setBusy("空闲");
  }
}

async function saveConfig(event) {
  event.preventDefault();
  const form = event.currentTarget;
  setBusy("保存配置");
  try {
    await fetchJson("/api/config", {
      method: "POST",
      body: JSON.stringify({
        profiles: {
          studio: {
            miniHost: form.studioMiniHost.value.trim(),
            proxy: {
              host: form.studioProxyHost.value.trim(),
              port: Number(form.studioProxyPort.value),
              type: form.studioProxyType.value,
            },
          },
          travel: {
            miniHost: form.travelMiniHost.value.trim(),
            proxy: {
              host: form.travelProxyHost.value.trim(),
              port: Number(form.travelProxyPort.value),
              type: form.travelProxyType.value,
            },
          },
        },
        expectedRegion: form.expectedRegion.value.trim().toUpperCase(),
      }),
    });
    setActionResult("配置已保存");
    await refreshAll();
  } catch (error) {
    setActionResult(error.message, true);
  } finally {
    setBusy("空闲");
  }
}

async function appControlAction(action, options = {}) {
  setBusy("处理中");
  try {
    const payload = await fetchJson("/api/app-control/action", {
      method: "POST",
      body: JSON.stringify({
        action,
        ...options,
      }),
    });
    setAppActionResult(payload.message || "动作已执行");
    await refreshAll();
    if (action === "console_stop") {
      window.setTimeout(() => {
        setAppActionResult("控制台服务已停止，如需恢复请双击桌面启动器。");
      }, 1200);
    }
  } catch (error) {
    setAppActionResult(error.message, true);
  } finally {
    setBusy("空闲");
  }
}

function bindEvents() {
  document.querySelectorAll("[data-mode]").forEach((button) => {
    button.addEventListener("click", () => switchMode(button.dataset.mode));
  });
  byId("verifyButton").addEventListener("click", verifyNow);
  byId("configForm").addEventListener("submit", saveConfig);
  byId("enableGuiProxyButton").addEventListener("click", () => {
    const profile = state.status?.connectionProfile || "studio";
    if (!window.confirm("这会重启 Codex 和 Antigravity，当前会话可能中断。继续吗？")) {
      return;
    }
    appControlAction("gui_proxy_enable", { profile });
  });
  byId("disableGuiProxyButton").addEventListener("click", () => {
    if (!window.confirm("这会重启 Codex 和 Antigravity 并清理 GUI 代理环境。继续吗？")) {
      return;
    }
    appControlAction("gui_proxy_disable");
  });
  byId("stopConsoleButton").addEventListener("click", () => {
    if (!window.confirm("这会停止当前 localhost 控制台服务，页面随后会失效。继续吗？")) {
      return;
    }
    appControlAction("console_stop");
  });
}

async function init() {
  bindEvents();
  try {
    await refreshAll();
    setActionResult("状态已刷新");
  } catch (error) {
    setActionResult(error.message, true);
  }
  window.setInterval(() => {
    refreshAll().catch(() => {});
  }, 20000);
}

init();
