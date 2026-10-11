"use strict";
// Token chỉ ở RAM tab. Reload tạo phiên mới; không cất token trong URL/localStorage.
let session = null;
let busy = false;
const byId = (id) => document.getElementById(id);
const messages = byId("messages");
const input = byId("message-input");
const reviewPanel = byId("review-panel");
const money = (value) => value === null ? "Chưa có giá" : `${new Intl.NumberFormat("vi-VN").format(value)} đ`;

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = String(text);
  if (className) node.className = className;
  return node;
}

function setBusy(value) {
  busy = value;
  document.querySelectorAll("button").forEach((button) => { button.disabled = value || !session; });
  byId("new-conversation").disabled = value;
  input.disabled = value || !session;
  byId("connection-status").textContent = value ? "Đang xử lý…" : session
    ? `${session.chat_mode === "ollama" ? "AI qua Ollama" : "Chế độ rule"} · Phiên riêng đã sẵn sàng`
    : "Chưa có phiên";
}

function showError(message) {
  byId("error-message").textContent = message;
  byId("error-message").hidden = !message;
}

async function api(path, body) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (session) headers.Authorization = `Bearer ${session.session_token}`;
  // Không đặt timeout ngắn hơn các lần retry Ollama phía backend.
  let response;
  try {
    response = await fetch(path, {method: body === undefined ? "GET" : "POST", headers,
      body: body === undefined ? undefined : JSON.stringify(body)});
  } catch {
    throw new Error("Không kết nối được API. Kiểm tra server run_web.py đang chạy, rồi bấm Hội thoại mới. Nếu server đã chạy, kiểm tra kết nối và tải lại trang.");
  }
  let result;
  try { result = await response.json(); } catch { throw new Error("Máy chủ trả dữ liệu không hợp lệ."); }
  if (!response.ok) {
    if (response.status === 401) throw new Error("Phiên hết hạn hoặc máy chủ vừa khởi động lại. Bấm Hội thoại mới.");
    const code = typeof result.detail === "string" ? result.detail : "request_failed";
    throw new Error(`Yêu cầu lỗi (${response.status}): ${code}. Có thể thử lại; xác nhận lại cùng bản nháp không tạo đơn demo trùng.`);
  }
  return result;
}

function showModes(data) {
  const mock = ["mock", "local_demo"].includes(data.data_mode);
  byId("mode-label").textContent = mock ? `MENU MÔ PHỎNG · ${data.data_mode.toUpperCase()}` : "MENU CHƯA KẾT NỐI · EMPTY";
  byId("data-notice").textContent = mock
    ? "Tên bánh, giá và tồn kho là dữ liệu mẫu để học. Chỉ có đơn DEMO."
    : "Chưa có menu để đối chiếu. Có thể ghi nhận nhu cầu và lưu yêu cầu chờ tư vấn; chưa xác nhận đơn.";
  if (["sample", "local_demo"].includes(data.knowledge_mode)) byId("data-notice").textContent += " Chính sách đang dùng tài liệu mô phỏng.";
  else byId("data-notice").textContent += " Chưa có chính sách cửa hàng.";
  if (!["empty", "mock", "local_demo"].includes(data.data_mode)) {
    byId("mode-label").textContent = "NGUỒN CHƯA XÁC ĐỊNH";
    byId("data-notice").textContent = "Không đọc được trạng thái nguồn. Chưa thể xác nhận sản phẩm, giá hoặc còn hàng; xem lỗi trong hội thoại.";
  }
  byId("state-label").textContent = data.state;
}

function addMessage(role, text) {
  const section = element("section", undefined, `message ${role}`);
  section.append(element("div", role === "user" ? "BẠN" : "BẾP BÁNH · TRỢ LÝ THỬ NGHIỆM", "sender"), element("div", text, "bubble"));
  messages.append(section);
  messages.scrollTop = messages.scrollHeight;
  return section;
}

function showProducts(parent, products) {
  if (!products.length) return;
  const grid = element("div", undefined, "product-grid");
  for (const product of products) {
    const card = element("article", undefined, "product-card");
    card.append(element("span", product.is_mock ? "SẢN PHẨM MẪU" : "NGUỒN SẢN PHẨM", "mock-tag"), element("h3", product.name), element("p", product.description), element("p", `Mã: ${product.id}`));
    for (const variant of product.variants) {
      const stock = {in_stock:"Còn hàng trong mẫu", out_of_stock:"Hết hàng trong mẫu", preorder:"Cần đặt trước / xác minh", unknown:"Chưa biết tình trạng"}[variant.stock_status];
      card.append(element("p", `${variant.size ?? "Chưa có size"} · ${money(variant.price_vnd)} · ${variant.servings ?? "Chưa biết số"} người · ${stock}`));
    }
    grid.append(card);
  }
  parent.append(grid);
}

function showSources(parent, sources) {
  for (const source of sources) {
    const card = element("article", undefined, "source");
    card.append(element("h3", `${source.is_mock ? "NGUỒN MÔ PHỎNG" : "Nguồn"} · ${source.source_id} · v${source.version}`), element("p", source.quote));
    parent.append(card);
  }
}

const slotLabels = {cake_need:"Nhu cầu",product_id:"Mã bánh",size:"Size",toppings:"Topping",quantity:"Số lượng",cake_text:"Chữ trên bánh",pickup_at:"Ngày giờ nhận",fulfillment:"Hình thức nhận",name:"Tên giả",phone:"Điện thoại giả",address:"Địa chỉ giả"};

function showReview(data) {
  reviewPanel.replaceChildren();
  reviewPanel.hidden = !data.review;
  if (reviewPanel.hidden) return;
  const review = data.review;
  reviewPanel.append(element("h3", "Xem lại yêu cầu · Chưa xác nhận đơn"));
  if (review.product_name) reviewPanel.append(element("p", `Bánh: ${review.product_name}`));
  const list = element("dl");
  for (const [key, value] of Object.entries(review.slots)) {
    if (value === null) continue;
    let shown = Array.isArray(value) ? (value.join(", ") || "Không") : value;
    if (shown === "") shown = "Không viết chữ";
    if (key === "fulfillment") shown = value === "pickup" ? "Tại cửa hàng (mô phỏng)" : "Giao (mô phỏng)";
    if (key === "pickup_at") shown = new Intl.DateTimeFormat("vi-VN", {timeZone:"Asia/Ho_Chi_Minh", dateStyle:"short", timeStyle:"short"}).format(new Date(value)) + " (giờ Việt Nam)";
    const verification = review.verification[key] ?? "unverified";
    list.append(element("dt", slotLabels[key] ?? key), element("dd", `${shown} [${verification}]`));
  }
  reviewPanel.append(list, element("p", review.quote ? `Tổng MÔ PHỎNG: ${money(review.quote.total_vnd)}` : "Chưa đủ nguồn để báo giá. Gửi chỉ là yêu cầu chờ tư vấn."));
  if (review.issues.length) reviewPanel.append(element("p", `Cần xác minh: ${review.issues.join(", ")}`));
  const actions = element("div", undefined, "review-actions");
  const confirm = element("button", review.quote && review.availability === "available" ? "Xác nhận đơn DEMO" : "Gửi yêu cầu chờ tư vấn", "button primary");
  confirm.type = "button";
  confirm.addEventListener("click", () => send("xác nhận"));
  const cancel = element("button", "Hủy bản nháp", "button secondary");
  cancel.type = "button";
  cancel.addEventListener("click", () => send("hủy"));
  if (data.requires_confirmation) actions.append(confirm);
  else reviewPanel.append(element("p", "Nguồn báo không khả dụng; cần sửa yêu cầu trước khi gửi."));
  actions.append(cancel);
  reviewPanel.append(actions, element("p", "Muốn sửa? Nhập lại trường trong chat, rồi bấm Xem lại yêu cầu. Chỉ dùng liên hệ giả."));
}

async function showSavedRecord(parent, data) {
  const id = data.request_id ?? data.demo_order_id;
  if (!id) return;
  const card = element("article", undefined, "record");
  card.append(element("h3", data.request_id ? "YÊU CẦU CHỜ TƯ VẤN · CHƯA XÁC NHẬN ĐƠN" : "ĐƠN DEMO · MÔ PHỎNG"), element("p", `Mã: ${id}`));
  parent.append(card);
  try {
    const record = await api(`/api/order-requests/${encodeURIComponent(id)}`);
    card.append(element("p", record.confirmed ? "Đã xác nhận trong bài tập mô phỏng; không thanh toán/giao thật." : "Đã lưu yêu cầu. Chưa có nhân viên nhận hoặc xác nhận đơn."));
  } catch (error) { card.append(element("p", `Chưa đọc lại được bản ghi: ${error.message}`)); }
}

async function startConversation() {
  if (busy) return;
  setBusy(true);
  showError("");
  try {
    const created = await api("/api/conversations", {});
    session = created;
    messages.replaceChildren();
    reviewPanel.replaceChildren();
    reviewPanel.hidden = true;
    input.value = "";
    byId("char-count").textContent = "0 / 2000";
    showModes(created);
    addMessage("bot", "Chào bạn! Đây là chatbot thử nghiệm. Bạn có thể hỏi bánh, chính sách hoặc ghi nhận nhu cầu đặt thử. Xem nhãn nguồn bên cạnh trước khi thử nhé.");
  } catch (error) {
    if (!session) {
      byId("mode-label").textContent = "CHƯA TẠO ĐƯỢC PHIÊN";
      byId("data-notice").textContent = "Chưa xác định được nguồn dữ liệu. Xem lỗi và thử tạo lại hội thoại.";
    }
    showError(`Chưa tạo được hội thoại: ${error.message}`);
  }
  finally { setBusy(false); input.focus(); }
}

async function send(text) {
  if (busy || !session || !text.trim()) return;
  setBusy(true);
  showError("");
  addMessage("user", text);
  try {
    const data = await api("/api/chat", {conversation_id:session.conversation_id, message:text});
    const parent = addMessage("bot", data.message);
    showModes(data);
    showProducts(parent, data.products);
    showSources(parent, data.sources);
    parent.append(element("p", `Bộ xử lý: ${data.engine} · Catalog: ${data.catalog_status}${data.errors.length ? ` · Lỗi: ${data.errors.join(", ")}` : ""}`, "diagnostic"));
    showReview(data);
    await showSavedRecord(parent, data);
    input.value = "";
    byId("char-count").textContent = "0 / 2000";
    messages.scrollTop = messages.scrollHeight;
  } catch (error) {
    // Kết nối đứt có thể đã được xử lý ở server. Bỏ nút REVIEW cũ rồi hỏi xem lại.
    reviewPanel.hidden = true;
    showError(`${error.message} Nếu vừa sửa bản nháp, hãy gửi “xem lại” trước khi xác nhận.`);
  } finally { setBusy(false); input.focus(); }
}

byId("chat-form").addEventListener("submit", (event) => { event.preventDefault(); send(input.value); });
input.addEventListener("input", () => { byId("char-count").textContent = `${input.value.length} / 2000`; });
input.addEventListener("keydown", (event) => {
  if (event.key === "Enter" && !event.shiftKey && !event.isComposing) { event.preventDefault(); send(input.value); }
});
byId("new-conversation").addEventListener("click", startConversation);
document.querySelectorAll("[data-message]").forEach((button) => button.addEventListener("click", () => send(button.dataset.message)));
startConversation();
