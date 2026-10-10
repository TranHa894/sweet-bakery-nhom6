// Bật API khi server đã sẵn sàng. Mặc định chỉ tạo đơn mẫu trong bộ nhớ trang.
window.SWEET_CONFIG = {
  mode: "demo", // 'demo' hoặc 'api'
  ordersEndpoint: "/api/orders",
  requestTimeoutMs: 15000,
};
