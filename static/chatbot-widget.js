/* Widget dùng lại giao diện chatbot; không chứa NLU hoặc logic đặt hàng. */
(() => {
  "use strict";
  const entry = new URL(document.currentScript.src);
  const assets = new URL(".", entry);
  const pageVersion = window.SWEET_CONFIG?.pageVersion || entry.searchParams.get("v");
  function pageURL(value) {
    const url = new URL(value, location.href);
    if (pageVersion && url.origin === location.origin && url.pathname.startsWith(assets.pathname)
        && (url.pathname.endsWith(".html") || url.pathname === assets.pathname)) {
      url.searchParams.set("site_v", pageVersion);
    }
    return url;
  }
  function prepareLink(link) {
    if (link && !link.hasAttribute("download") && !link.getAttribute("href")?.startsWith("#")) {
      link.href = pageURL(link.href).href;
    }
  }
  // URL phiên bản cố định tránh danh mục HTML cũ mà browser không gửi lại tới server.
  // Không dùng timestamp mỗi lần bấm, không đổi id/q/page hoặc gọi model.
  document.addEventListener("click", (event) => prepareLink(event.target.closest?.("a[href]")), true);
  function mount() {
    document.querySelectorAll("a[href]").forEach(prepareLink);
    document.querySelectorAll('form[role="search"]').forEach((form) => {
      const target = pageURL(form.action);
      if (!target.searchParams.has("site_v")) return;
      form.action = target.href;
      // Form GET thay query của action bằng dữ liệu form, nên giữ version bằng input.
      let field = form.querySelector('input[name="site_v"]');
      if (!field) {
        field = document.createElement("input");
        field.type = "hidden";
        field.name = "site_v";
        form.append(field);
      }
      field.value = pageVersion;
    });
    if (document.getElementById("sweet-chat-widget")) return;
    const configured = window.SWEET_CONFIG?.chatbotUrl;
    const backend = new URL(location.origin);
    if (assets.pathname !== "/website/") backend.port = "8000";
    let chatURL;
    try {
      chatURL = configured ? new URL(configured, location.href) : new URL("/chatbot/", backend);
      if (!["http:", "https:"].includes(chatURL.protocol)) return;
    } catch { return; }
    chatURL.searchParams.set("embed", "1");
    const css = document.createElement("link");
    css.rel = "stylesheet";
    css.href = new URL("chatbot-widget.css", assets).href;
    document.head.append(css);
    const key = "sweetBakeryChatWidget.v1";
    const icons = {
      chat: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2h-8l-5 3v-3H5a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2Z"/><path d="M8 10h.01M12 10h.01M16 10h.01" stroke-linecap="round" stroke-width="3"/></svg>',
      expand: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M9 3H3v6m12-6h6v6M3 15v6h6m12-6v6h-6"/></svg>',
      restore: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="7" y="7" width="14" height="14" rx="1"/><path d="M17 7V3H3v14h4"/></svg>',
      minimize: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M5 17h14"/></svg>'
    };
    function node(tag, className, text) {
      const el = document.createElement(tag);
      if (className) el.className = className;
      if (text) el.textContent = text;
      return el;
    }
    function button(label, icon) {
      const el = node("button", "sweet-chat-control");
      el.type = "button";
      el.title = label;
      el.setAttribute("aria-label", label);
      el.innerHTML = icons[icon]; // Chỉ SVG cố định của ứng dụng, không dùng dữ liệu chat.
      return el;
    }
    const root = node("aside", "sweet-chat-widget");
    root.id = "sweet-chat-widget";
    root.setAttribute("aria-label", "Trợ lý Sweet Bakery");
    const launcher = button("Mở chat với Sweet Bakery", "chat");
    launcher.className = "sweet-chat-launcher";
    launcher.setAttribute("aria-controls", "sweet-chat-window");
    const panel = node("section", "sweet-chat-window");
    panel.id = "sweet-chat-window";
    panel.setAttribute("aria-label", "Cửa sổ trò chuyện");
    const toolbar = node("header", "sweet-chat-toolbar");
    const heading = node("div", "sweet-chat-heading");
    heading.append(node("strong", "", "Sweet Bakery"), node("span", "", "Cùng chọn một chút ngọt ngào"));
    const controls = node("div", "sweet-chat-controls");
    const expand = button("Phóng to toàn màn hình", "expand");
    const minimize = button("Thu về nút chat", "minimize");
    controls.append(expand, minimize);
    toolbar.append(heading, controls);
    const status = node("div", "sweet-chat-loading");
    const notice = node("p", "", "Đang kết nối trợ lý…");
    const retry = node("button", "sweet-chat-retry", "Kết nối lại");
    retry.type = "button";
    retry.hidden = true;
    status.append(notice, retry);
    panel.append(toolbar, status);
    root.append(panel, launcher);
    document.body.append(root);
    let frame = null, loadingTimer = null, mode = "closed";
    function loadFrame() {
      clearTimeout(loadingTimer);
      if (frame) frame.remove();
      status.hidden = false;
      retry.hidden = true;
      notice.textContent = "Đang kết nối trợ lý…";
      frame = node("iframe", "sweet-chat-frame");
      frame.title = "Trò chuyện với trợ lý Sweet Bakery";
      frame.allow = "geolocation";
      frame.referrerPolicy = "strict-origin-when-cross-origin";
      frame.src = chatURL.href;
      panel.append(frame);
      loadingTimer = setTimeout(() => {
        notice.textContent = "Chưa kết nối được trợ lý. Bạn có thể thử lại.";
        retry.hidden = false;
      }, 12000);
    }
    function changeMode(next, focus = true) {
      mode = next;
      root.dataset.mode = mode;
      panel.hidden = mode === "closed";
      launcher.hidden = mode !== "closed";
      launcher.setAttribute("aria-expanded", String(mode !== "closed"));
      document.documentElement.classList.toggle("sweet-chat-fullscreen", mode === "full");
      const label = mode === "full" ? "Thu về cửa sổ nhỏ" : "Phóng to toàn màn hình";
      expand.title = label;
      expand.setAttribute("aria-label", label);
      expand.setAttribute("aria-pressed", String(mode === "full"));
      expand.innerHTML = icons[mode === "full" ? "restore" : "expand"];
      try { sessionStorage.setItem(key, mode); } catch { /* Vẫn dùng được trong trang hiện tại. */ }
      if (mode !== "closed" && !frame) loadFrame();
      if (focus) (mode === "closed" ? launcher : expand).focus({preventScroll: true});
    }
    launcher.addEventListener("click", () => changeMode("window"));
    expand.addEventListener("click", () => changeMode(mode === "full" ? "window" : "full"));
    minimize.addEventListener("click", () => changeMode("closed"));
    retry.addEventListener("click", loadFrame);
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && mode !== "closed" &&
          (mode === "full" || root.contains(document.activeElement))) changeMode("closed");
    });
    window.addEventListener("message", (event) => {
      if (!frame || event.source !== frame.contentWindow || event.origin !== chatURL.origin ||
          event.data?.channel !== "sweet-bakery-chat") return;
      if (event.data.action === "ready") {
        clearTimeout(loadingTimer);
        status.hidden = true;
      } else if (event.data.action === "minimize") {
        changeMode("closed");
      } else if (event.data.action === "product" && /^SP\d{4}$/.test(event.data.productId)) {
        const target = new URL("chi-tiet-san-pham-demo.html", assets);
        target.searchParams.set("id", event.data.productId);
        location.assign(pageURL(target.href).href);
      }
    });
    let saved = "closed";
    try { saved = sessionStorage.getItem(key) || saved; } catch { /* Không bắt buộc storage. */ }
    changeMode(["closed", "window", "full"].includes(saved) ? saved : "closed", false);
  }
  window.addEventListener("pageshow", mount); // BFCache không phát DOMContentLoaded lần nữa.
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", mount, {once: true});
  else mount();
})();
