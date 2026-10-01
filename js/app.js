/* GPT IP Guard — frontend bridge */
(function () {
  "use strict";

  const $ = (id) => document.getElementById(id);

  const els = {
    statusBanner: $("status-banner"),
    statusIcon: $("status-icon"),
    statusTitle: $("status-title"),
    statusDesc: $("status-desc"),
    statusPill: $("status-pill"),
    ipDomestic: $("ip-domestic"),
    metaDomestic: $("meta-domestic"),
    ipForeign: $("ip-foreign"),
    metaForeign: $("meta-foreign"),
    ipCurrent: $("ip-current"),
    metaCurrent: $("meta-current"),
    countryValue: $("country-value"),
    usFlag: $("us-flag"),
    launchHint: $("launch-hint"),
    btnLaunchClient: $("btn-launch-client"),
    btnLaunchWeb: $("btn-launch-web"),
    toggleGuard: $("toggle-guard"),
    toggleBlock: $("toggle-block"),
    logBox: $("log-box"),
    btnRefresh: $("btn-refresh"),
    btnClearLog: $("btn-clear-log"),
    footerStatus: $("footer-status"),
    cardDomestic: $("card-domestic"),
    cardForeign: $("card-foreign"),
    cardCurrent: $("card-current"),
  };

  function api() {
    return window.pywebview && window.pywebview.api;
  }

  function log(msg, level = "info") {
    const line = document.createElement("div");
    line.className = `log-line ${level}`;
    const ts = new Date().toLocaleTimeString("zh-CN", { hour12: false });
    line.textContent = `[${ts}] ${msg}`;
    els.logBox.appendChild(line);
    els.logBox.scrollTop = els.logBox.scrollHeight;
  }

  function setBanner(state, title, desc, pill, icon) {
    els.statusBanner.className = `status-banner ${state}`;
    els.statusTitle.textContent = title;
    els.statusDesc.textContent = desc;
    els.statusPill.textContent = pill;
    els.statusIcon.textContent = icon;
  }

  function render(data) {
    if (!data) return;

    els.ipDomestic.textContent = data.domestic_ip || "--";
    els.ipForeign.textContent = data.foreign_ip || "--";
    els.ipCurrent.textContent = data.current_ip || "--";

    els.metaDomestic.textContent = data.domestic_meta || "";
    els.metaForeign.textContent = data.foreign_meta || "";
    els.metaCurrent.textContent = data.current_meta || "";

    els.countryValue.textContent = data.country || "未知";

    const isUS = !!data.is_us;
    els.usFlag.textContent = isUS ? "✔ 是 · 可安全启动" : "✘ 否 · 已拦截";
    els.usFlag.className = `country-flag ${isUS ? "yes" : "no"}`;

    els.btnLaunchClient.disabled = !isUS;
    els.btnLaunchWeb.disabled = !isUS;

    els.cardForeign.className = `ip-card ${isUS ? "highlight-safe" : "highlight-danger"}`;
    els.cardCurrent.className = `ip-card ${isUS ? "highlight-safe" : ""}`;

    if (data.checking) {
      setBanner("pending", "正在检测出口 IP…", "请稍候，正在查询国内外出口地址", "检测中", "…");
    } else if (isUS) {
      setBanner(
        "safe",
        "海外出口为美国 · 可安全启动 GPT",
        `出口地区：${data.country || "美国"} · 已允许访问 chatgpt.com / openai.com`,
        "安全",
        "✓"
      );
      els.launchHint.textContent = "海外出口为美国，可以启动 ChatGPT（客户端 / 网页）";
    } else {
      setBanner(
        "blocked",
        "海外出口不是美国 · 已禁止访问 GPT",
        `当前出口：${data.country || "未知"} · 请先打开代理（如 Clash Verge）并切换到美国节点`,
        "已拦截",
        "⛔"
      );
      els.launchHint.textContent = "海外出口不是美国，已禁用启动按钮并拦截网站";
    }

    els.toggleGuard.checked = !!data.guard_enabled;
    els.toggleBlock.checked = !!data.block_enabled;

    if (data.footer) els.footerStatus.textContent = data.footer;
  }

  async function refresh(silent = false) {
    const a = api();
    if (!a) {
      if (!silent) log("Python 后端未连接（浏览器预览模式）", "warn");
      return;
    }
    try {
      if (!silent) log("正在刷新出口 IP…", "info");
      const data = await a.refresh_ips();
      render(data);
      if (!silent) {
        log(
          data.is_us
            ? `海外出口 ${data.foreign_ip || "-"} 属于 ${data.country || "美国"}，允许启动`
            : `海外出口 ${data.foreign_ip || "-"} 属于 ${data.country || "未知"}，已拦截`,
          data.is_us ? "ok" : "warn"
        );
      }
    } catch (e) {
      log(`刷新失败: ${e}`, "error");
    }
  }

  async function toggleGuard() {
    const a = api();
    if (!a) return;
    try {
      const data = await a.set_guard(els.toggleGuard.checked);
      render(data);
      log(
        els.toggleGuard.checked
          ? "已开启强制守护：非美国出口时将强制结束 ChatGPT"
          : "已关闭强制守护",
        els.toggleGuard.checked ? "warn" : "info"
      );
    } catch (e) {
      log(`设置守护失败: ${e}`, "error");
    }
  }

  async function toggleBlock() {
    const a = api();
    if (!a) return;
    try {
      const data = await a.set_block(els.toggleBlock.checked);
      render(data);
      log(
        els.toggleBlock.checked
          ? "已开启网站拦截（hosts）"
          : "已关闭网站拦截",
        "info"
      );
    } catch (e) {
      log(`设置拦截失败: ${e}`, "error");
    }
  }

  async function launchClient() {
    const a = api();
    if (!a) return;
    log("正在启动 ChatGPT 客户端…", "info");
    try {
      const r = await a.launch_client();
      log(r.message || r, r.ok ? "ok" : "error");
    } catch (e) {
      log(`启动客户端失败: ${e}`, "error");
    }
  }

  async function launchWeb() {
    const a = api();
    if (!a) return;
    log("正在打开 chatgpt.com…", "info");
    try {
      const r = await a.launch_web();
      log(r.message || r, r.ok ? "ok" : "error");
    } catch (e) {
      log(`打开网页失败: ${e}`, "error");
    }
  }

  // Backend → frontend event hook
  window.gptGuardPush = function (event, payload) {
    if (event === "log") {
      log(payload.msg, payload.level || "info");
    } else if (event === "state") {
      render(payload);
    } else if (event === "killed") {
      log(payload, "error");
    }
  };

  els.btnRefresh.addEventListener("click", () => refresh(false));
  els.btnClearLog.addEventListener("click", () => {
    els.logBox.innerHTML = "";
    log("日志已清空", "info");
  });
  els.toggleGuard.addEventListener("change", toggleGuard);
  els.toggleBlock.addEventListener("change", toggleBlock);
  els.btnLaunchClient.addEventListener("click", launchClient);
  els.btnLaunchWeb.addEventListener("click", launchWeb);

  // Browser preview fallback
  if (!window.pywebview) {
    const demo = {
      domestic_ip: "183.14.132.100",
      foreign_ip: "104.28.0.1",
      current_ip: "192.168.1.20",
      domestic_meta: "中国 · 广东 · 深圳（示例）",
      foreign_meta: "United States · California（示例）",
      current_meta: "本机局域网地址（示例）",
      country: "United States",
      is_us: true,
      guard_enabled: false,
      block_enabled: true,
      footer: "浏览器预览模式 · 示例数据",
    };
    render(demo);
    log("浏览器预览模式：已加载示例数据", "warn");
    log("打包为 EXE 后将接入真实出口 IP 检测", "info");
    return;
  }

  // Wait for pywebview API
  window.addEventListener("pywebviewready", () => {
    log("Python 后端已连接", "ok");
    refresh(true);
    // poll every 30s
    setInterval(() => refresh(true), 30000);
  });
})();
