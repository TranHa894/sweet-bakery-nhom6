"use strict";
// Phiên theo tab: sessionStorage giữ token qua chuyển trang; không dùng URL/localStorage.
const SESSION_KEY = "sweetBakeryChatSession.v1";
const embedded = window.parent !== window && new URLSearchParams(location.search).get("embed") === "1";
if (embedded) document.documentElement.classList.add("embedded");
let parentOrigin = null;
try { if (embedded && document.referrer) parentOrigin = new URL(document.referrer).origin; } catch { /* Không gửi sang origin chưa biết. */ }
function notifyParent(action, extra = {}) {
  if (parentOrigin) window.parent.postMessage({channel: "sweet-bakery-chat", action, ...extra}, parentOrigin);
}
function rememberSession() {
  try { sessionStorage.setItem(SESSION_KEY, JSON.stringify(session)); }
  catch { showError("Trình duyệt không cho lưu phiên tạm. Lịch sử có thể không khôi phục khi chuyển trang."); }
}
function forgetSession() {
  try { sessionStorage.removeItem(SESSION_KEY); } catch { /* Storage có thể bị chặn. */ }
}
function readSession() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(SESSION_KEY) || "null");
    if (saved && typeof saved.conversation_id === "string" && typeof saved.session_token === "string"
        && saved.session_token.length >= 32 && saved.session_token.length <= 128) return saved;
  } catch { /* Dữ liệu hỏng không được dùng làm phiên. */ }
  forgetSession();
  return null;
}
let session = null;
let busy = false;
const byId = (id) => document.getElementById(id);
const messages = byId("messages");
const input = byId("message-input");
const reviewPanel = byId("review-panel");
const welcome = byId("welcome");
const formatMoney = (value) => Number.isInteger(value) && value >= 0
  ? new Intl.NumberFormat("vi-VN").format(value) + " đ" : null;
const stateLabels = {
  BROWSING: "Bạn có thể hỏi về bánh",
  COLLECTING: "Đang ghi nhận yêu cầu của bạn",
  REVIEW: "Xem lại yêu cầu trước khi gửi",
  DEMO_CONFIRMED: "Đã lưu đơn mô phỏng",
  CANCELLED: "Đã hủy bản nháp",
  HANDOFF: "Đã ghi nhận yêu cầu hỗ trợ"
};

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

function updateInput() {
  const count = input.value.length;
  byId("char-count").textContent = count + " / 2000";
  byId("char-count").hidden = count < 1800;
  byId("send-button").disabled = busy || !session || !input.value.trim();
  input.style.height = "auto";
  input.style.height = Math.min(120, Math.max(44, input.scrollHeight)) + "px";
}

function setBusy(value) {
  busy = value;
  document.querySelectorAll("button").forEach((button) => {
    button.disabled = value || !session;
  });
  byId("new-conversation").disabled = value;
  input.disabled = value || !session;
  messages.setAttribute("aria-busy", String(value));
  document.querySelector(".chat-panel").classList.toggle("is-busy", value);
  byId("connection-status").textContent = value ? "Đang trả lời…"
    : session ? (stateLabels[session.state] || "Sẵn sàng trò chuyện") : "Chưa kết nối";
  updateInput();
}

function showError(message) {
  byId("error-message").textContent = message;
  byId("error-message").hidden = !message;
}

async function api(path, body) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (session) headers.Authorization = "Bearer " + session.session_token;
  let response;
  try {
    // Chờ timeout/retry của backend; không tự gửi lại tin nhắn hoặc xác nhận.
    response = await fetch(path, {
      method: body === undefined ? "GET" : "POST", headers,
      body: body === undefined ? undefined : JSON.stringify(body)
    });
  } catch {
    throw new Error("Mất kết nối. Kiểm tra chatbot đang chạy rồi thử lại.");
  }
  let result;
  try { result = await response.json(); }
  catch { throw new Error("Chưa đọc được phản hồi. Bạn có thể thử lại."); }
  if (!response.ok) {
    const errors = {
      401: "Phiên đã hết hạn. Bấm Chat mới để tiếp tục.",
      404: "Không tìm thấy hội thoại. Bấm Chat mới để tiếp tục.",
      422: "Tin nhắn chưa hợp lệ. Vui lòng nhập từ 1 đến 2.000 ký tự.",
      503: "Chatbot tạm thời chưa sẵn sàng. Bạn có thể thử lại."
    };
    let detail = errors[response.status] || "Chưa xử lý được yêu cầu. Bạn có thể thử lại.";
    if (path === "/api/checkout") {
      if (response.status === 409 && typeof result.detail === "string") detail = result.detail;
      if (response.status === 422) detail = "Bạn kiểm tra các trường bắt buộc, số điện thoại, email, ngày nhận và số lượng nhé.";
    }
    const error = new Error(detail);
    error.status = response.status;
    throw error;
  }
  return result;
}

function showModes(data) {
  const source = data.catalog_source || session?.catalog_source;
  let label, notice;
  if (data.catalog_status === "error") {
    label = "Menu chưa đọc được";
    notice = "Chưa thể xác nhận sản phẩm hoặc giá. Bạn có thể thử lại.";
  } else if (data.data_mode === "empty" || data.catalog_status === "unconfigured") {
    label = "Chưa kết nối menu";
    notice = "Có thể ghi nhận nhu cầu; chưa đủ dữ liệu để chọn bánh hoặc xác nhận đơn.";
  } else if (source === "group_files") {
    label = "Danh mục tham khảo";
    notice = "Chỉ lưu yêu cầu chờ tư vấn, chưa xác nhận đơn.";
  } else if (["mock", "local_demo"].includes(data.data_mode)) {
    label = "Dữ liệu mô phỏng";
    notice = "Bánh và đơn chỉ dùng để thử, không thanh toán hoặc giao hàng thật.";
  } else {
    label = "Chưa xác định nguồn";
    notice = "Chưa đủ thông tin để xác nhận sản phẩm, giá hoặc tình trạng bán.";
  }
  if (["sample", "local_demo"].includes(data.knowledge_mode)) notice += " Chính sách mẫu.";
  byId("mode-label").textContent = label;
  byId("data-notice").textContent = notice;
  session.state = data.state;
  if (data.catalog_source) session.catalog_source = data.catalog_source;
}

function displayMessage(text) {
  // Nhãn nguồn đã có ở đầu khung chat. Chỉ bỏ tiền tố do backend tạo,
  // giữ nguyên nội dung, cảnh báo nghiệp vụ và nguồn trích dẫn trong câu trả lời.
  return String(text ?? "")
    .replace(/^\[Nguồn:[^\]\r\n]*\][ \t]*/u, "")
    .replace(/^\[MÔ PHỎNG[^\]\r\n]*\][ \t]*/u, "")
    .trim();
}

function addMessage(role, text) {
  const section = element("section", undefined, "message " + role);
  section.append(
    element("div", role === "user" ? "Bạn" : "Sweet Bakery", "sender"),
    element("div", role === "user" ? text : displayMessage(text), "bubble")
  );
  messages.append(section);
  messages.scrollTop = messages.scrollHeight;
  return section;
}


function addPendingReply() {
  // Hiện trạng thái ngay khi gửi; thời gian này là đã chờ, không dự đoán model.
  const section = addMessage("bot", "Đang xử lý yêu cầu…");
  section.classList.add("pending");
  const bubble = section.querySelector(".bubble");
  const elapsed = element("span", "", "waiting-elapsed");
  elapsed.setAttribute("aria-hidden", "true"); // Không đọc lại từng giây qua screen reader.
  bubble.append(elapsed);
  const started = performance.now();
  const timer = setInterval(() => {
    const seconds = Math.floor((performance.now() - started) / 1000);
    if (seconds >= 3) elapsed.textContent = "Đã chờ " + seconds + " giây";
  }, 1000);
  return {
    section,
    complete(text) {
      clearInterval(timer);
      section.classList.remove("pending");
      bubble.textContent = displayMessage(text);
      return section;
    },
    remove() { section.remove(); },
    stop() { clearInterval(timer); }
  };
}

function showProducts(parent, products = []) {
  if (!products.length) return;
  const grid = element("div", undefined, "product-grid");
  const ids = new Set();
  for (const product of products) {
    if (ids.has(product.id)) continue;
    ids.add(product.id);
    const card = element("article", undefined, "product-card");
    if (typeof product.image_url === "string" && /^\/website\/images\/[A-Za-z0-9_.-]+$/.test(product.image_url)) {
      const image = document.createElement("img");
      image.src = product.image_url;
      image.alt = product.name;
      image.className = "product-image";
      image.loading = "lazy";
      image.decoding = "async";
      image.addEventListener("error", () => image.remove(), {once: true});
      card.append(image);
    }
    card.append(element("h3", product.name));
    const shown = new Set();
    for (const variant of product.variants || []) {
      const details = [];
      if (variant.size) details.push(variant.size);
      const price = formatMoney(variant.price_vnd);
      if (price) details.push(price);
      if (Number.isInteger(variant.servings) && variant.servings > 0) details.push("Khoảng " + variant.servings + " người");
      if (details.length && !shown.has(details.join(" · "))) {
        card.append(element("p", details.join(" · "), "price"));
        shown.add(details.join(" · "));
      }
      const stock = {in_stock: "Còn hàng", out_of_stock: "Hết hàng", preorder: "Cần đặt trước"}[variant.stock_status];
      if (stock) {
        const note = stock + (product.is_mock ? " (mẫu)" : "");
        if (!shown.has(note)) card.append(element("p", note, "product-note"));
        shown.add(note);
      }
    }
    // Không hiển thị các trường null/unknown hay mô tả chung lặp lại của menu nhóm.
    if (product.source === "group_files" && product.id) {
      const link = element("a", "Xem bánh →");
      link.href = "/website/chi-tiet-san-pham-demo.html?id=" + encodeURIComponent(product.id);
      if (embedded) {
        link.target = "_blank";
        link.rel = "noopener";
        if (parentOrigin) link.addEventListener("click", (event) => {
          event.preventDefault();
          notifyParent("product", {productId: product.id});
        });
      }
      card.append(link);
    }
    grid.append(card);
  }
  parent.append(grid);
}

function showQuickReplies(parent, replies = []) {
  document.querySelectorAll(".reply-actions").forEach((node) => node.remove());
  if (!replies.length) return;
  const group = element("div", undefined, "quick-actions reply-actions");
  group.setAttribute("aria-label", "Lựa chọn tư vấn");
  for (const label of replies.slice(0, 6)) {
    const button = element("button", label);
    button.type = "button";
    button.addEventListener("click", () => send(label));
    group.append(button);
  }
  parent.append(group);
}

function showSources(parent, sources = []) {
  if (!sources.length) return;
  const details = element("details", undefined, "source");
  details.append(element("summary", "Nguồn tham khảo" + (sources.some((source) => source.is_mock) ? " · tài liệu mẫu" : "")));
  const seen = new Set();
  for (const source of sources) {
    const key = JSON.stringify([source.source_id, source.version, source.quote]);
    if (seen.has(key)) continue;
    seen.add(key);
    const card = element("article");
    card.append(element("h3", source.source_id + " · v" + source.version), element("p", source.quote));
    details.append(card);
  }
  parent.append(details);
}

let checkoutCatalog = null;
let activeCheckout = null;
let checkoutPresented = false;
const checkoutLabels = {
  fullName: "Họ và tên", phone: "Số điện thoại", email: "Email",
  province: "Tỉnh / Thành phố", ward: "Phường / Xã", addressLine: "Số nhà, tên đường, tòa nhà",
  deliveryDate: "Ngày nhận mong muốn", deliverySlot: "Khung giờ mong muốn",
  cakeMessage: "Lời chúc viết trên bánh", note: "Ghi chú"
};
const slotLabels = {"": "Cửa hàng liên hệ xác nhận", morning: "08:00 – 12:00",
  afternoon: "12:00 – 17:00", evening: "17:00 – 20:00"};

function checkoutButton(label, callback, primary = false) {
  const button = element("button", label, "button " + (primary ? "primary" : "secondary"));
  button.type = "button";
  button.addEventListener("click", callback);
  return button;
}

async function checkoutAction(action, form) {
  if (busy || !activeCheckout) return;
  const snapshot = activeCheckout;
  const body = {conversation_id: session.conversation_id, draft_id: snapshot.draft_id,
    revision: snapshot.revision, action};
  if (form) body.form = form;
  if (action === "confirm") body.confirmation_token = snapshot.confirmation_token;
  setBusy(true);
  showError("");
  try {
    const data = await api("/api/checkout", body);
    welcome.hidden = true;
    addMessage("bot", data.message);
    showModes(data);
    rememberSession();
    showReview(data);
    if (!reviewPanel.hidden && data.checkout && data.checkout.stage !== "cancelled") reviewPanel.scrollIntoView({block: "start"});
    else messages.scrollTop = messages.scrollHeight;
  } catch (error) {
    showError(error.message);
  } finally {
    setBusy(false);
  }
}

function orderThumbnail(name, path) {
  const box = element("span", undefined, "checkout-thumbnail");
  if (typeof path === "string" && /^\/website\/images\/[A-Za-z0-9_.-]+$/.test(path)) {
    const img = document.createElement("img");
    img.src = path; img.alt = name || "Ảnh sản phẩm";
    img.width = 48; img.height = 48; img.loading = "lazy"; img.decoding = "async";
    img.addEventListener("error", () => { box.replaceChildren(element("span", "Ảnh")); }, {once: true});
    box.append(img);
  } else box.textContent = "Ảnh";
  return box;
}

function checkoutSummary(view) {
  const summary = view.summary;
  if (!summary) return;
  const list = element("div", undefined, "checkout-lines");
  for (const line of summary.items) {
    const row = element("div", undefined, "checkout-line");
    const heading = element("div", undefined, "checkout-product-heading");
    const product = (checkoutCatalog || []).find(item => item.id === line.product_id);
    heading.append(orderThumbnail(line.name, line.image_url || product?.image_url), element("strong", line.name));
    row.append(heading,
      element("span", line.quantity + " × " + formatMoney(line.unit_price_vnd)),
      element("strong", formatMoney(line.line_total_vnd)));
    list.append(row);
  }
  reviewPanel.append(list, element("p", "Tổng tiền hàng: " + formatMoney(summary.subtotal_vnd), "checkout-total"),
    element("p", summary.notice));
  const details = element("dl", undefined, "checkout-details");
  for (const [key, label] of Object.entries(checkoutLabels)) {
    const value = view.form[key];
    if (!value) continue;
    details.append(element("dt", label), element("dd", key === "deliverySlot" ? slotLabels[value] : value));
  }
  reviewPanel.append(details);
}

function renderCheckoutForm(view) {
  const form = element("form", undefined, "checkout-form");
  form.id = "order-information-form";
  const productsBox = element("div", undefined, "checkout-items");
  const rows = [];
  const menu = checkoutCatalog || [];
  function addItem(item = {product_id: "", quantity: 1}) {
    const row = element("div", undefined, "checkout-item");
    const productLabel = element("label", "Sản phẩm *");
    const select = element("select");
    select.required = true;
    select.append(new Option("Chọn sản phẩm", ""));
    for (const product of menu) select.append(new Option(product.name, product.id));
    select.value = item.product_id;
    productLabel.append(select);
    const productCell = element("div", undefined, "checkout-product");
    const selected = menu.find(product => product.id === select.value);
    let thumbnail = orderThumbnail(selected?.name, selected?.image_url);
    productCell.append(thumbnail, productLabel);
    select.addEventListener("change", () => {
      const product = menu.find(item => item.id === select.value);
      const next = orderThumbnail(product?.name, product?.image_url);
      thumbnail.replaceWith(next); thumbnail = next;
    });
    const qtyLabel = element("label", "Số lượng *");
    const qty = element("input");
    qty.type = "number"; qty.min = "1"; qty.max = "99"; qty.step = "1";
    qty.required = true; qty.value = item.quantity;
    qtyLabel.append(qty);
    const remove = checkoutButton("Bỏ món", () => {
      row.remove(); rows.splice(rows.indexOf(entry), 1);
    });
    const entry = {select, qty};
    rows.push(entry);
    row.append(productCell, qtyLabel, remove);
    productsBox.append(row);
  }
  view.items.forEach(addItem);
  const add = checkoutButton("Thêm món", () => { if (rows.length < 20) addItem(); });
  form.append(element("p", "Các trường có dấu * là bắt buộc. Số điện thoại cần 10 số hoặc bắt đầu bằng +84."),
    productsBox, add);
  const grid = element("div", undefined, "checkout-grid");
  const limits = {fullName: 100, phone: 20, email: 254, province: 100, ward: 100,
    addressLine: 250, cakeMessage: 100, note: 500};
  for (const [key, label] of Object.entries(checkoutLabels)) {
    const required = ["fullName", "phone", "province", "ward", "addressLine"].includes(key);
    const wrapper = element("label", label + (required ? " *" : ""));
    const control = element(key === "note" ? "textarea" : key === "deliverySlot" ? "select" : "input");
    control.name = key;
    control.required = required;
    if (key === "deliverySlot") {
      for (const [value, name] of Object.entries(slotLabels)) control.append(new Option(name, value));
    } else if (key !== "note") {
      control.type = key === "phone" ? "tel" : key === "email" ? "email" : key === "deliveryDate" ? "date" : "text";
    }
    if (limits[key]) control.maxLength = limits[key];
    if (key === "phone") {
      control.placeholder = "09xxxxxxxx";
      control.addEventListener("input", () => control.setCustomValidity(""));
    }
    if (key === "fullName") control.minLength = 2;
    if (key === "addressLine") control.minLength = 5;
    if (key === "deliveryDate") {
      const parts = new Intl.DateTimeFormat("en-CA", {timeZone: "Asia/Ho_Chi_Minh",
        year: "numeric", month: "2-digit", day: "2-digit"}).formatToParts(new Date());
      const date = Object.fromEntries(parts.map(part => [part.type, part.value]));
      control.min = date.year + "-" + date.month + "-" + date.day;
    }
    control.value = view.form[key] || "";
    wrapper.append(control);
    if (["addressLine", "cakeMessage", "note"].includes(key)) wrapper.className = "checkout-wide";
    grid.append(wrapper);
  }
  const consentLabel = element("label", undefined, "checkout-consent");
  const consent = element("input"); consent.type = "checkbox"; consent.name = "consent";
  consent.required = true; consent.checked = Boolean(view.form.consent);
  consentLabel.append(consent, element("span", "Tôi đồng ý cung cấp thông tin để xử lý yêu cầu đặt hàng. *"));
  const actions = element("div", undefined, "review-actions");
  const submit = element("button", "Xem lại yêu cầu", "button primary"); submit.type = "submit";
  actions.append(submit, checkoutButton("Hủy", () => checkoutAction("cancel")));
  form.append(grid, element("p", "Ngày/giờ nhận và lời chúc là mong muốn cần cửa hàng xác nhận; chưa tính phí giao hàng."),
    consentLabel, actions);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const phone = form.elements.namedItem("phone");
    const digits = phone.value.replace(/[ .-]/g, "");
    phone.setCustomValidity(/^(?:0[35789]\d{8}|\+84[35789]\d{8})$/.test(digits)
      ? "" : "Nhập số di động Việt Nam 10 số hoặc bắt đầu bằng +84.");
    if (!form.reportValidity()) return;
    if (!rows.length) { showError("Bạn cần chọn ít nhất một sản phẩm."); return; }
    const values = Object.fromEntries(new FormData(form));
    values.consent = consent.checked;
    values.items = rows.map(row => ({product_id: row.select.value, quantity: Number(row.qty.value)}));
    checkoutAction("review", values);
  });
  reviewPanel.append(form);
}

function showReview(data, skipCatalog = false) {
  const view = data.checkout;
  if ((view && data.show_checkout === false) || data.errors?.length) {
    // Ẩn phần đơn khi đang tư vấn/lượt lỗi, giữ DOM để không mất form chưa gửi.
    checkoutPresented = false;
    reviewPanel.hidden = true;
    return;
  }
  checkoutPresented = Boolean(view);
  const existing = document.getElementById("order-information-form");
  // Câu hỏi thông tin không làm mất phần khách đang gõ trong form cùng revision.
  if (existing && view?.stage === "form" && activeCheckout?.stage === "form"
      && view.draft_id === activeCheckout.draft_id && view.revision === activeCheckout.revision) {
    view.form = Object.fromEntries(new FormData(existing));
    view.form.consent = existing.elements.namedItem("consent").checked;
    view.items = [...existing.querySelectorAll(".checkout-item")].map(row => ({
      product_id: row.querySelector("select").value, quantity: Number(row.querySelector("input").value)
    }));
  }
  activeCheckout = view || null;
  reviewPanel.replaceChildren();
  reviewPanel.hidden = !view || view.stage === "cancelled";
  if (!view) {
    // Giữ tương thích API phiên cũ; không gửi xác nhận chỉ bằng ID.
    if (data.review && data.requires_confirmation && !data.errors?.length) {
      reviewPanel.hidden = false;
      reviewPanel.append(checkoutButton("Gửi yêu cầu", () => send("xác nhận gửi yêu cầu"), true));
    }
    return;
  }
  if (reviewPanel.hidden) return;
  messages.append(reviewPanel); // Cùng vùng cuộn: form không chiếm hết widget.
  reviewPanel.append(element("h2", view.stage === "form" ? "Thông tin đặt hàng"
    : view.stage === "review" ? "Xem lại yêu cầu" : "Yêu cầu đã lưu"));
  if (!checkoutCatalog && !skipCatalog) {
    reviewPanel.append(element("p", "Đang tải danh mục…"));
    api("/api/catalog").then(result => {
      checkoutCatalog = result.products.filter(product => product.active !== false);
      if (activeCheckout === view && checkoutPresented) showReview(data);
    }).catch(error => {
      if (activeCheckout === view && checkoutPresented) {
        // Bản xem lại vẫn có snapshot giá/tên ngay cả khi nguồn ảnh đang lỗi.
        if (view.stage !== "form") showReview(data, true);
        else {
          reviewPanel.append(element("p", error.message));
          reviewPanel.append(checkoutButton("Thử tải lại", () => showReview(data)));
        }
      }
    });
    return;
  }
  if (view.stage === "form") {
    renderCheckoutForm(view);
  } else {
    checkoutSummary(view);
    if (view.stage === "review") {
      reviewPanel.append(element("p", "Xác nhận sẽ lưu yêu cầu chờ cửa hàng tư vấn, chưa thanh toán."));
      const actions = element("div", undefined, "review-actions");
      actions.append(checkoutButton("Xác nhận gửi yêu cầu", () => checkoutAction("confirm"), true),
        checkoutButton("Quay lại chỉnh sửa", () => checkoutAction("edit")),
        checkoutButton("Hủy", () => checkoutAction("cancel")));
      reviewPanel.append(actions);
    } else {
      reviewPanel.append(element("p", "Mã yêu cầu: " + view.record_id),
        element("p", "Bạn có thể đặt thêm món trong cuộc trò chuyện này."));
    }
  }
}

async function startConversation() {
  if (busy) return;
  setBusy(true);
  showError("");
  try {
    const created = await api("/api/conversations", {});
    session = created;
    rememberSession();
    welcome.hidden = false;
    messages.replaceChildren(welcome);
    reviewPanel.replaceChildren();
    reviewPanel.hidden = true;
    activeCheckout = null;
    checkoutPresented = false;
    input.value = "";
    showModes(created);
  } catch (error) {
    if (!session) {
      byId("mode-label").textContent = "Chưa kết nối";
      byId("data-notice").textContent = "Bấm Chat mới để thử kết nối lại.";
    }
    showError(error.message);
  } finally {
    setBusy(false);
    if (session) input.focus();
  }
}

async function restoreConversation() {
  session = readSession();
  if (!session) return startConversation();
  setBusy(true);
  showError("");
  byId("connection-status").textContent = "Đang khôi phục cuộc trò chuyện…";
  try {
    const data = await api("/api/conversations/" + encodeURIComponent(session.conversation_id));
    messages.replaceChildren(welcome);
    welcome.hidden = data.messages.length > 0;
    if (data.truncated) messages.append(element("p", "Hiển thị 100 tin nhắn gần nhất của cuộc trò chuyện.", "history-note"));
    let lastAssistant = null;
    for (const message of data.messages) {
      const section = addMessage(message.role === "user" ? "user" : "bot", message.content);
      lastAssistant = message.role === "assistant" ? section : null;
    }
    if (lastAssistant) {
      showProducts(lastAssistant, data.snapshot.products);
      showSources(lastAssistant, data.snapshot.sources);
      showQuickReplies(lastAssistant, data.snapshot.quick_replies);
    }
    showModes(data.snapshot);
    showReview(data.snapshot);
    rememberSession();
    messages.scrollTop = messages.scrollHeight;
  } catch (error) {
    if ([401, 404].includes(error.status)) {
      forgetSession();
      session = null;
    }
    showError(error.message);
  } finally {
    setBusy(false);
  }
}

async function send(text) {
  if (busy || !session || !text.trim()) return;
  setBusy(true);
  showError("");
  welcome.hidden = true;
  reviewPanel.hidden = true;
  document.querySelectorAll(".reply-actions").forEach((node) => node.remove());
  addMessage("user", text);
  const pending = addPendingReply();
  try {
    const data = await api("/api/chat", {conversation_id: session.conversation_id, message: text});
    const parent = pending.complete(data.message);
    showModes(data);
    rememberSession();
    showProducts(parent, data.products);
    showSources(parent, data.sources);
    showQuickReplies(parent, data.quick_replies);
    showReview(data);
    input.value = "";
    if (!reviewPanel.hidden && ["form", "review"].includes(data.checkout?.stage)) reviewPanel.scrollIntoView({block: "start"});
    else messages.scrollTop = messages.scrollHeight;
  } catch (error) {
    // Không tự retry: server có thể đã nhận tin nhắn trước khi mất kết nối.
    pending.remove();
    checkoutPresented = false; // Lỗi mạng không tự mở lại đơn cũ.
    reviewPanel.hidden = true;
    showError(error.message + " Nếu vừa sửa yêu cầu, hãy tải lại thông tin trước khi xác nhận.");
  } finally {
    pending.stop();
    setBusy(false);
    input.focus();
  }
}

byId("chat-form").addEventListener("submit", (event) => { event.preventDefault(); send(input.value); });
input.addEventListener("input", updateInput);
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); send(input.value); }
});
byId("new-conversation").addEventListener("click", startConversation);
document.querySelectorAll("[data-message]").forEach((button) => {
  button.addEventListener("click", () => send(button.dataset.message));
});
if (embedded) document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") notifyParent("minimize");
});
notifyParent("ready");
restoreConversation();
