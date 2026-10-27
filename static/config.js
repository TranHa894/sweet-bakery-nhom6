// Bật API khi server đã sẵn sàng. Mặc định chỉ tạo đơn mẫu trong bộ nhớ trang.
window.SWEET_CONFIG = {
  // Để trống: /website/ dùng cùng server run_web; Live Server/Flask dùng cổng 8000.
  // Nếu chạy chatbot ở cổng khác, nhập URL trang chat, ví dụ http://127.0.0.1:8001/chatbot/.
  chatbotUrl: "",
  pageVersion: "20261024-3", // Phiên bản URL trang, tránh HTML danh mục cũ trong cache.
  mode: "demo", // 'demo' hoặc 'api'
  ordersEndpoint: "/api/orders",
  requestTimeoutMs: 15000,
};
