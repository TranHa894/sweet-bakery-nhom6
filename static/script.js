/* Sweet Bakery — giao diện HTML/CSS/JS thuần, không yêu cầu framework. */
"use strict";
document.addEventListener("DOMContentLoaded", () => {
  const products = window.SWEET_PRODUCTS || [];
  const config = window.SWEET_CONFIG || { mode: "demo" };
  const byId = new Map(products.map((p) => [p.id, p]));
  const KEY = "sweetBakeryCart";
  const $ = (s) => document.querySelector(s);
  const esc = (s) =>
    String(s ?? "").replace(
      /[&<>"']/g,
      (c) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#39;",
        })[c],
    );
  const money = (n) =>
    new Intl.NumberFormat("vi-VN", {
      style: "currency",
      currency: "VND",
    }).format(n);
  const fold = (s) =>
    String(s)
      .normalize("NFD")
      .replace(/[\u0300-\u036f]/g, "")
      .replace(/đ/g, "d")
      .replace(/Đ/g, "D")
      .toLowerCase()
      .trim();
  const quantity = (n) =>
    Number.isInteger(Number(n)) && Number(n) >= 1 && Number(n) <= 99;
  let toastTimer,
    cart = [],
    busy = false,
    resultOrder = null,
    retryKey = "",
    retryBody = "";
  function toast(message) {
    const el = $("#toast");
    el.textContent = message;
    el.hidden = false;
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => {
      el.hidden = true;
    }, 4500);
  }
  function readCart() {
    try {
      const raw = JSON.parse(localStorage.getItem(KEY) || "[]");
      if (!Array.isArray(raw)) throw new Error();
      const cleaned = [];
      for (const item of raw) {
        if (!item || typeof item !== "object") continue;
        // Chuyển dữ liệu giỏ cũ theo tên sang mã SP ổn định.
        const product =
          byId.get(item.productId || item.id) ||
          products.find((p) => fold(p.name) === fold(item.name));
        if (!product || !quantity(item.quantity)) continue;
        const existing = cleaned.find((i) => i.productId === product.id);
        if (existing)
          existing.quantity = Math.min(
            99,
            existing.quantity + Number(item.quantity),
          );
        else
          cleaned.push({
            productId: product.id,
            quantity: Number(item.quantity),
          });
      }
      return cleaned;
    } catch {
      toast("Không đọc được giỏ đã lưu. Bạn có thể chọn lại sản phẩm.");
      return [];
    }
  }
  function saveCart(next) {
    try {
      localStorage.setItem(KEY, JSON.stringify(next));
    } catch {
      toast(
        "Trình duyệt không cho lưu giỏ hàng. Hãy cho phép dữ liệu trang web rồi thử lại.",
      );
      return false;
    }
    cart = next;
    renderCart();
    return true;
  }
  const subtotal = () =>
    cart.reduce((n, i) => n + byId.get(i.productId).price * i.quantity, 0);
  const detailURL = (id) =>
    `chi-tiet-san-pham-demo.html?id=${encodeURIComponent(id)}`;
  function card(p) {
    return `<article class="product-card"><div class="img-wrap"><a href="${detailURL(p.id)}"><img src="${esc(p.image)}" alt="${esc(p.name)}" loading="lazy" width="400" height="400"></a><button class="btn-add-cart" data-add="${p.id}" type="button">+ Thêm vào giỏ</button></div><div class="product-info"><h3><a href="${detailURL(p.id)}">${esc(p.name)}</a></h3><p class="price">${money(p.price)}</p></div></article>`;
  }
  function add(id, qty = 1) {
    if (!byId.has(id) || !quantity(qty)) {
      toast("Số lượng phải là số nguyên từ 1 đến 99.");
      return false;
    }
    cart = readCart();
    const next = cart.map((i) => ({ ...i }));
    const item = next.find((i) => i.productId === id);
    if ((item?.quantity || 0) + Number(qty) > 99) {
      toast("Mỗi sản phẩm được chọn tối đa 99 chiếc.");
      return false;
    }
    if (item) item.quantity += Number(qty);
    else next.push({ productId: id, quantity: Number(qty) });
    if (!saveCart(next)) return false;
    toast(`Đã thêm ${qty} × ${byId.get(id).name} vào giỏ.`);
    return true;
  }
  function renderCart() {
    const count = cart.reduce((n, i) => n + i.quantity, 0);
    document
      .querySelectorAll(".cart-count")
      .forEach((el) => (el.textContent = count));
    document
      .querySelectorAll(".final-total")
      .forEach((el) => (el.textContent = money(subtotal())));
    if ($("#cart-body")) {
      $("#cart-body").innerHTML = cart.length
        ? cart
            .map((i) => {
              const p = byId.get(i.productId);
              return `<tr><td><div class="cart-item-info"><img src="${esc(p.image)}" alt="${esc(p.name)}"><a href="${detailURL(p.id)}">${esc(p.name)}<small>${p.id}</small></a></div></td><td>${money(p.price)}</td><td><div class="stepper"><button type="button" data-step="-1" data-id="${p.id}" aria-label="Giảm số lượng ${esc(p.name)}" ${i.quantity === 1 ? "disabled" : ""}>−</button><input class="qty-input-change" data-id="${p.id}" type="number" min="1" max="99" step="1" value="${i.quantity}" aria-label="Số lượng ${esc(p.name)}"><button type="button" data-step="1" data-id="${p.id}" aria-label="Tăng số lượng ${esc(p.name)}" ${i.quantity === 99 ? "disabled" : ""}>+</button></div></td><td class="cart-total">${money(p.price * i.quantity)}</td><td><button class="remove-button" data-remove="${p.id}" type="button" aria-label="Xóa ${esc(p.name)}">Xóa</button></td></tr>`;
            })
            .join("")
        : '<tr><td colspan="5"><div class="empty-state"><h2>Giỏ hàng của bạn đang trống</h2><p>Chọn một chút ngọt ngào cho hôm nay nhé.</p><a class="btn-view-all" href="banh-kem-p1.html">Khám phá bánh kem →</a></div></td></tr>';
      $("#checkout-link").hidden = !cart.length;
      $("#clear-cart").hidden = !cart.length;
    }
    if ($("#checkout-items") && !resultOrder) {
      $("#checkout-empty").hidden = !!cart.length;
      $("#checkout-content").hidden = !cart.length;
      $("#checkout-items").innerHTML = cart
        .map((i) => {
          const p = byId.get(i.productId);
          return `<div class="summary-item"><img src="${esc(p.image)}" alt="${esc(p.name)}"><div><a href="${detailURL(p.id)}">${esc(p.name)}</a><small>Số lượng: ${i.quantity}</small></div><strong>${money(p.price * i.quantity)}</strong></div>`;
        })
        .join("");
    }
  }
  cart = readCart();
  renderCart();
  window.addEventListener("storage", (e) => {
    if (e.key === KEY || e.key === null) {
      cart = readCart();
      renderCart();
    }
  });
  document.addEventListener("click", (e) => {
    const addButton = e.target.closest("[data-add]");
    if (addButton)
      add(
        addButton.dataset.add,
        addButton.hasAttribute("data-detail") ? $("#detail-quantity").value : 1,
      );
    const buy = e.target.closest("[data-buy]");
    if (buy && add(buy.dataset.buy, $("#detail-quantity").value))
      location.href = "thanh-toan.html";
    const remove = e.target.closest("[data-remove]");
    if (remove) {
      cart = readCart();
      saveCart(cart.filter((i) => i.productId !== remove.dataset.remove));
    }
    const step = e.target.closest("[data-step]");
    if (step) {
      cart = readCart();
      const next = cart.map((i) => ({ ...i }));
      const item = next.find((i) => i.productId === step.dataset.id);
      if (item && quantity(item.quantity + Number(step.dataset.step))) {
        item.quantity += Number(step.dataset.step);
        saveCart(next);
      }
    }
  });
  document.addEventListener("change", (e) => {
    if (!e.target.matches(".qty-input-change")) return;
    const val = Number(e.target.value);
    if (!quantity(val)) {
      toast("Nhập số lượng nguyên từ 1 đến 99.");
      renderCart();
      return;
    }
    cart = readCart();
    saveCart(
      cart.map((i) =>
        i.productId === e.target.dataset.id ? { ...i, quantity: val } : i,
      ),
    );
  });
  $("#clear-cart")?.addEventListener("click", () => {
    if (confirm("Xóa tất cả sản phẩm khỏi giỏ hàng?")) saveCart([]);
  });
  if ($("#home-products"))
    $("#home-products").innerHTML = products.slice(0, 4).map(card).join("");
  const params = new URLSearchParams(location.search);
  if ($("#catalog-products")) {
    const category = $("#main").dataset.category;
    const query = (params.get("q") || "").slice(0, 100);
    const pageSize = 6;
    let page = Number(params.get("page") || $("#main").dataset.page) || 1;
    const filtered = products.filter(
      (p) =>
        (category === "all" || p.category === category) &&
        (category !== "all" || fold(p.name).includes(fold(query))),
    );
    $("#search").value = query;
    const sort = $("#sort");
    if ([...sort.options].some((o) => o.value === params.get("sort")))
      sort.value = params.get("sort");
    function renderCatalog() {
      let list = [...filtered];
      if (sort.value === "name-asc")
        list.sort((a, b) => a.name.localeCompare(b.name, "vi"));
      if (sort.value === "name-desc")
        list.sort((a, b) => b.name.localeCompare(a.name, "vi"));
      if (sort.value === "price-asc") list.sort((a, b) => a.price - b.price);
      if (sort.value === "price-desc") list.sort((a, b) => b.price - a.price);
      const pages = Math.max(1, Math.ceil(list.length / pageSize));
      page = Math.max(1, Math.min(pages, Math.floor(page)));
      $("#result-count").textContent =
        `${list.length} sản phẩm${query ? " cho “" + query + "”" : ""} · Trang ${page}/${pages}`;
      $("#catalog-products").innerHTML = list.length
        ? list
            .slice((page - 1) * pageSize, page * pageSize)
            .map(card)
            .join("")
        : '<div class="empty-state"><h2>Chưa tìm thấy sản phẩm</h2><p>Thử từ khóa khác như “mousse”, “trà” hoặc “bánh”.</p><a href="tim-kiem.html">Xem tất cả sản phẩm</a></div>';
      $("#pagination").innerHTML =
        pages > 1
          ? Array.from({ length: pages }, (_, i) => {
              const n = i + 1;
              const qp = new URLSearchParams({ sort: sort.value });
              if (query) qp.set("q", query);
              let path = location.pathname.split("/").pop();
              if (category === "cake") path = `banh-kem-p${n}.html`;
              else qp.set("page", n);
              return `<a href="${path}?${esc(qp.toString())}" ${n === page ? 'class="active" aria-current="page"' : ""} aria-label="Trang ${n}">${n}</a>`;
            }).join("")
          : "";
    }
    sort.addEventListener("change", () => {
      page = 1;
      renderCatalog();
    });
    renderCatalog();
  }
  if ($("#product-detail")) {
    const id = params.get("id") || "SP0024";
    const p = byId.get(id);
    if (!p)
      $("#product-detail").innerHTML =
        '<div class="empty-state"><h1>Không tìm thấy sản phẩm</h1><a href="banh-kem-p1.html">Quay lại danh mục</a></div>';
    else {
      document.title = p.name + " - Sweet Bakery";
      const desc =
        p.id === "SP0024"
          ? "Bánh mousse chanh leo với lớp kem mềm mịn và vị chua ngọt thanh mát."
          : "Một lựa chọn ngọt ngào từ bộ sưu tập Sweet Bakery. Vui lòng ghi yêu cầu riêng ở bước thông tin giao hàng để cửa hàng xác nhận.";
      $("#product-detail").innerHTML =
        `<div class="product-detail-layout"><div class="product-gallery"><div class="main-image"><img src="${esc(p.image)}" alt="${esc(p.name)}"></div></div><div class="product-info-detail"><p class="eyebrow">SWEET BAKERY COLLECTION</p><h1 class="detail-title">${esc(p.name)}</h1><div class="detail-meta">Mã sản phẩm: <strong>${p.id}</strong></div><div class="detail-price-box"><span class="detail-price">${money(p.price)}</span></div><p class="detail-short-desc">${desc}</p><p class="muted">Giá tham khảo trong bản giao diện. Tình trạng hàng và yêu cầu riêng cần được xác nhận.</p><div class="purchase-action"><div class="quantity-box"><label for="detail-quantity">Số lượng</label><input id="detail-quantity" class="qty-input" type="number" value="1" min="1" max="99" step="1"></div><div class="button-group"><button class="btn-add-to-cart-detail" data-add="${p.id}" data-detail type="button">Thêm vào giỏ</button><button class="btn-buy-now" data-buy="${p.id}" type="button">Mua ngay</button></div></div><a href="gio-hang.html" class="text-link">Xem giỏ hàng →</a></div></div><section class="product-description-section"><h2 class="desc-title">Thông tin thêm</h2><div class="desc-content"><p>${desc}</p><p>Hình ảnh mang tính minh họa. Nếu có dị ứng thực phẩm, hãy hỏi cửa hàng về thành phần trước khi đặt.</p></div></section>`;
    }
  }
  // Một ảnh hỏng không làm vỡ bố cục; không tạo vòng lặp tải ảnh.
  document.addEventListener(
    "error",
    (e) => {
      if (e.target.tagName === "IMG") {
        e.target.classList.add("image-unavailable");
        e.target.alt = "Ảnh sản phẩm chưa sẵn có";
      }
    },
    true,
  );
  const form = $("#checkout-form");
  if (form) {
    const field = (n) => form.elements.namedItem(n);
    const today = () => {
      const d = new Date();
      return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;
    };
    field("deliveryDate").min = today();
    const apiMode = config.mode === "api";
    if (apiMode) {
      $("#mode-note").textContent =
        "Kiểm tra thông tin trước khi gửi yêu cầu đặt hàng. Phí giao hàng và thời gian nhận sẽ được xác nhận.";
      $("#submit-order").textContent = "Gửi yêu cầu đặt hàng";
    }
    function validateField(el) {
      el.setCustomValidity("");
      if (el.type === "checkbox" || el.type === "radio") return;
      const value = el.value.trim();
      if (el.required && !value)
        el.setCustomValidity("Vui lòng điền thông tin này.");
      else if (el.name === "fullName" && value.length < 2)
        el.setCustomValidity("Vui lòng nhập họ và tên từ 2 ký tự.");
      else if (el.name === "addressLine" && value.length < 5)
        el.setCustomValidity("Vui lòng nhập địa chỉ cụ thể từ 5 ký tự.");
      else if (
        el.name === "phone" &&
        !/^(0[35789]\d{8}|\+84[35789]\d{8})$/.test(
          value.replace(/[\s.()-]/g, ""),
        )
      )
        el.setCustomValidity(
          "Nhập số di động Việt Nam gồm 10 số hoặc bắt đầu bằng +84.",
        );
      else if (el.name === "deliveryDate" && value && value < today())
        el.setCustomValidity("Ngày nhận không được nằm trong quá khứ.");
    }
    form.addEventListener("input", (e) => {
      if (e.target.setCustomValidity) validateField(e.target);
      $("#form-error").textContent = "";
    });
    form.addEventListener("submit", async (e) => {
      e.preventDefault();
      if (busy) return;
      [...form.elements].forEach((el) => {
        if (el.setCustomValidity) validateField(el);
      });
      if (!form.reportValidity()) return;
      cart = readCart();
      renderCart();
      if (!cart.length) return;
      const value = (n) => field(n).value.trim();
      const payload = {
        customer: {
          fullName: value("fullName"),
          phone: value("phone").replace(/[\s.()-]/g, ""),
          email: value("email") || null,
        },
        shippingAddress: {
          province: value("province"),
          ward: value("ward"),
          addressLine: value("addressLine"),
        },
        delivery: {
          requestedDate: value("deliveryDate") || null,
          requestedSlot: value("deliverySlot") || null,
        },
        cakeMessage: value("cakeMessage"),
        note: value("note"),
        paymentMethod: "cod",
        consent: true,
        items: cart.map((i) => ({ ...i })),
      };
      const serialized = JSON.stringify(payload);
      if (serialized !== retryBody) {
        retryBody = serialized;
        retryKey =
          globalThis.crypto?.randomUUID?.() ||
          `sb-${Date.now()}-${Math.random().toString(36).slice(2)}`;
      }
      busy = true;
      $("#submit-order").disabled = true;
      $("#submit-order").textContent = "Đang xử lý…";
      $("#form-error").textContent = "";
      // Khóa form trong lúc gửi; không lưu thông tin khách hàng vào localStorage.
      [...form.elements].forEach((el) => (el.disabled = true));
      try {
        if (apiMode) {
          const controller = new AbortController();
          const timer = setTimeout(
            () => controller.abort(),
            config.requestTimeoutMs || 15000,
          );
          let response, data;
          try {
            response = await fetch(config.ordersEndpoint, {
              method: "POST",
              headers: {
                "Content-Type": "application/json",
                "Idempotency-Key": retryKey,
              },
              body: serialized,
              signal: controller.signal,
            });
            data = await response.json();
          } finally {
            clearTimeout(timer);
          }
          if (!response.ok)
            throw new Error(
              response.status === 409
                ? "Sản phẩm hoặc giá đã thay đổi. Vui lòng kiểm tra lại với cửa hàng."
                : "Chưa gửi được đơn hàng. Hãy kiểm tra kết nối hoặc liên hệ cửa hàng trước khi thử lại.",
            );
          if (!data || typeof data.orderId !== "string" || !data.orderId)
            throw new Error(
              "Phản hồi server thiếu mã đơn hàng. Hãy liên hệ cửa hàng trước khi gửi lại.",
            );
          resultOrder = {
            ...payload,
            orderId: data.orderId,
            status: data.status || "pending",
            serverSummary: data,
          };
          // Chỉ trừ lượng đã gửi, giữ các sản phẩm được thêm ở tab khác khi chờ API.
          const current = readCart();
          const remaining = current
            .map((i) => ({
              ...i,
              quantity:
                i.quantity -
                (payload.items.find((j) => j.productId === i.productId)
                  ?.quantity || 0),
            }))
            .filter((i) => i.quantity > 0);
          saveCart(remaining);
          $("#result-title").textContent = "Đã gửi yêu cầu đặt hàng";
          $("#result-message").textContent =
            "Cửa hàng sẽ xác nhận thông tin, tổng tiền và thời gian giao hàng.";
        } else {
          resultOrder = {
            ...payload,
            orderId: "DEMO-" + Date.now(),
            status: "demo_not_sent",
            createdAt: new Date().toISOString(),
            currency: "VND",
            estimatedSubtotal: subtotal(),
            shippingFee: null,
            productSnapshot: payload.items.map((i) => {
              const p = byId.get(i.productId);
              return {
                productId: p.id,
                name: p.name,
                unitPrice: p.price,
                quantity: i.quantity,
              };
            }),
          };
          $("#result-title").textContent = "Đã tạo đơn hàng mẫu";
          $("#result-message").textContent =
            "Đơn này chưa gửi đến cửa hàng và chưa có thanh toán. Bạn có thể tải file JSON để kiểm thử. Giỏ hàng được giữ lại.";
        }
        $("#result-reference").textContent =
          "Mã tham chiếu: " + resultOrder.orderId;
        $("#checkout-content").hidden = true;
        $("#checkout-empty").hidden = true;
        $("#order-result").hidden = false;
        $("#order-result").focus();
      } catch (error) {
        $("#form-error").textContent =
          error.name === "AbortError"
            ? "Kết nối hết thời gian chờ; chưa xác định server đã nhận đơn hay chưa. Thử lại giữ nguyên thông tin sẽ dùng cùng mã chống trùng."
            : error instanceof TypeError || error instanceof SyntaxError
              ? "Không nhận được phản hồi hợp lệ. Kiểm tra kết nối server rồi thử lại."
              : error.message;
      } finally {
        busy = false;
        [...form.elements].forEach((el) => (el.disabled = false));
        $("#submit-order").textContent = apiMode
          ? "Gửi yêu cầu đặt hàng"
          : "Tạo đơn hàng mẫu";
      }
    });
    $("#download-order").addEventListener("click", () => {
      if (!resultOrder) return;
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(resultOrder, null, 2)], {
          type: "application/json",
        }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = "sweet-bakery-order.json";
      a.click();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
    });
  }
});
