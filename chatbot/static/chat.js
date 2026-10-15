"use strict";
// Token chỉ nằm trong RAM của tab; không ghi vào URL hoặc localStorage.
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
    throw new Error(errors[response.status] || "Chưa xử lý được yêu cầu. Bạn có thể thử lại.");
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
    label = "Menu nhóm · dữ liệu mẫu";
    notice = "Chỉ lưu yêu cầu chờ tư vấn, chưa xác nhận đơn.";
  } else if (["mock", "local_demo"].includes(data.data_mode)) {
    label = "Dữ liệu mô phỏng";
    notice = "Bánh và đơn chỉ dùng để thử, không thanh toán hoặc giao hàng thật.";
  } else {
    label = "Chưa xác định nguồn";
    notice = "Chưa đủ thông tin để xác nhận sản phẩm, giá hoặc tình trạng bán.";
  }
  if (["sample", "local_demo"].includes(data.knowledge_mode)) notice += " Chính sách mẫu.";
  if (["COLLECTING", "REVIEW"].includes(data.state)) notice += " Chỉ dùng liên hệ giả DEMO/TEST.";
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

function showProducts(parent, products = []) {
  if (!products.length) return;
  const grid = element("div", undefined, "product-grid");
  const ids = new Set();
  for (const product of products) {
    if (ids.has(product.id)) continue;
    ids.add(product.id);
    const card = element("article", undefined, "product-card");
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
      card.append(link);
    }
    grid.append(card);
  }
  parent.append(grid);
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

function showReview(data) {
  reviewPanel.replaceChildren();
  // Nội dung REVIEW đầy đủ đã có trong tin nhắn bot, không dựng bản sao.
  reviewPanel.hidden = !data.review || !data.requires_confirmation || Boolean(data.errors?.length);
  if (reviewPanel.hidden) return;
  const demo = Boolean(data.review.quote && data.review.availability === "available"
    && ["mock", "local_demo"].includes(data.review.data_mode) && (data.review.items?.length || 1) === 1);
  reviewPanel.append(element("p", demo ? "Đây là đơn mô phỏng, không thanh toán thật."
    : "Gửi chỉ lưu yêu cầu chờ tư vấn, chưa xác nhận đơn."));
  const actions = element("div", undefined, "review-actions");
  const confirm = element("button", demo ? "Xác nhận đơn mô phỏng" : "Gửi yêu cầu", "button primary");
  confirm.type = "button";
  confirm.addEventListener("click", () => send("xác nhận gửi yêu cầu"));
  const cancel = element("button", "Hủy bản nháp", "button secondary");
  cancel.type = "button";
  cancel.addEventListener("click", () => send("hủy bản nháp"));
  actions.append(confirm, cancel);
  reviewPanel.append(actions);
}

async function startConversation() {
  if (busy) return;
  setBusy(true);
  showError("");
  try {
    const created = await api("/api/conversations", {});
    session = created;
    welcome.hidden = false;
    messages.replaceChildren(welcome);
    reviewPanel.replaceChildren();
    reviewPanel.hidden = true;
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

async function send(text) {
  if (busy || !session || !text.trim()) return;
  setBusy(true);
  showError("");
  welcome.hidden = true;
  reviewPanel.hidden = true;
  addMessage("user", text);
  try {
    const data = await api("/api/chat", {conversation_id: session.conversation_id, message: text});
    const parent = addMessage("bot", data.message);
    showModes(data);
    showProducts(parent, data.products);
    showSources(parent, data.sources);
    showReview(data);
    input.value = "";
    messages.scrollTop = messages.scrollHeight;
  } catch (error) {
    // Không tự retry: server có thể đã nhận tin nhắn trước khi mất kết nối.
    showError(error.message + " Nếu vừa sửa yêu cầu, hãy gửi “xem lại” trước khi xác nhận.");
  } finally {
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
startConversation();
