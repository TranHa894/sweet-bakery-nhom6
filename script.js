document.addEventListener('DOMContentLoaded', () => {
    // 1. Lấy dữ liệu giỏ hàng từ bộ nhớ (localStorage), nếu chưa có thì tạo mảng rỗng []
    let cart = JSON.parse(localStorage.getItem('sweetBakeryCart')) || [];

    // Hàm cập nhật con số màu đỏ trên biểu tượng giỏ hàng ở Header
    function updateCartIcon() {
        // Tính tổng số lượng của tất cả sản phẩm
        const totalItems = cart.reduce((sum, item) => sum + item.quantity, 0);
        document.querySelectorAll('.cart-count').forEach(el => el.textContent = totalItems);
    }

    // ==========================================
    // TÍNH NĂNG 1: THÊM VÀO GIỎ HÀNG
    // ==========================================
    const addButtons = document.querySelectorAll('.btn-add-cart, .btn-add-to-cart-detail');
    
    addButtons.forEach(button => {
        button.addEventListener('click', (e) => {
            e.preventDefault();
            
            // Lấy dữ liệu từ các thuộc tính data- mà bạn vừa gắn vào HTML
            const name = button.getAttribute('data-name');
            const price = parseInt(button.getAttribute('data-price'));
            const image = button.getAttribute('data-image');

            if (!name || !price) {
                alert("Bạn chưa gắn data-name hoặc data-price cho nút này!");
                return;
            }

            // Kiểm tra xem bánh này đã có trong giỏ chưa
            const existingItem = cart.find(item => item.name === name);
            if (existingItem) {
                // Nếu có rồi thì chỉ tăng số lượng
                existingItem.quantity += 1;
            } else {
                // Nếu chưa có thì thêm mới vào mảng
                cart.push({ name: name, price: price, image: image, quantity: 1 });
            }

            // Lưu mảng mới vào bộ nhớ
            localStorage.setItem('sweetBakeryCart', JSON.stringify(cart));
            
            updateCartIcon();
            alert(`Đã thêm ${name} vào giỏ hàng!`);
        });
    });

    // ==========================================
    // TÍNH NĂNG 2: HIỂN THỊ VÀ XÓA Ở TRANG GIỎ HÀNG
    // ==========================================
    const cartBody = document.getElementById('cart-body');
    
    // Chỉ chạy code dưới đây nếu đang đứng ở trang gio-hang.html
    if (cartBody) {
        function renderCart() {
            cartBody.innerHTML = ''; // Xóa trắng bảng cũ
            let totalPrice = 0;

            if (cart.length === 0) {
                cartBody.innerHTML = '<tr><td colspan="5" style="text-align:center; padding: 30px;">Giỏ hàng của bạn đang trống!</td></tr>';
                document.querySelector('.final-total').textContent = '0 ₫';
                return;
            }

            // Duyệt qua từng sản phẩm để tạo HTML
            cart.forEach((item, index) => {
                const itemTotal = item.price * item.quantity;
                totalPrice += itemTotal;

                const tr = document.createElement('tr');
                tr.innerHTML = `
                    <td class="cart-item-info">
                        <img src="${item.image}" alt="${item.name}">
                        <span>${item.name}</span>
                    </td>
                    <td class="cart-price">${item.price.toLocaleString('vi-VN')} ₫</td>
                    <td class="cart-quantity">
                        <input type="number" value="${item.quantity}" min="1" class="qty-input-change" data-index="${index}">
                    </td>
                    <td class="cart-total">${itemTotal.toLocaleString('vi-VN')} ₫</td>
                    <td class="cart-remove"><i class="fas fa-trash btn-delete" data-index="${index}"></i></td>
                `;
                cartBody.appendChild(tr);
            });

            // Cập nhật tổng tiền
            document.querySelector('.final-total').textContent = totalPrice.toLocaleString('vi-VN') + ' ₫';
            
            // Gắn sự kiện cho các nút Xóa và ô nhập Số lượng
            attachCartEvents();
        }

        function attachCartEvents() {
            // Xử lý nút Xóa (thùng rác)
            document.querySelectorAll('.btn-delete').forEach(btn => {
                btn.addEventListener('click', (e) => {
                    const index = e.target.getAttribute('data-index');
                    cart.splice(index, 1); // Xóa 1 phần tử tại vị trí index
                    
                    localStorage.setItem('sweetBakeryCart', JSON.stringify(cart)); // Lưu lại
                    renderCart(); // Vẽ lại bảng
                    updateCartIcon(); // Cập nhật icon trên Header
                });
            });

            // Xử lý khi người dùng gõ/tăng giảm số lượng trực tiếp trong giỏ
            document.querySelectorAll('.qty-input-change').forEach(input => {
                input.addEventListener('change', (e) => {
                    const index = e.target.getAttribute('data-index');
                    let newQty = parseInt(e.target.value);
                    
                    if (newQty < 1) newQty = 1; // Không cho nhập số âm
                    
                    cart[index].quantity = newQty; // Cập nhật số lượng mới
                    localStorage.setItem('sweetBakeryCart', JSON.stringify(cart));
                    renderCart();
                    updateCartIcon();
                });
            });
        }

        // Gọi hàm vẽ giỏ hàng lần đầu tiên khi load trang
        renderCart();
    }

    // Gọi hàm cập nhật icon lần đầu tiên khi load mọi trang
    updateCartIcon();

    // ==========================================
    // TÍNH NĂNG 3: SẮP XẾP SẢN PHẨM TRONG DANH MỤC
    // ==========================================
    const sortSelect = document.getElementById('sort');
    const productGrid = document.querySelector('.collection-grid') || document.querySelector('.product-grid');

    if (sortSelect && productGrid) {
        // Mảng lưu lại thứ tự sản phẩm ban đầu để dùng khi chọn lại "Tùy chọn"
        const originalCards = Array.from(productGrid.querySelectorAll('.product-card'));

        sortSelect.addEventListener('change', (e) => {
            const selectedOption = e.target.value;
            let cards = Array.from(productGrid.querySelectorAll('.product-card'));

            // Hàm hỗ trợ trích xuất giá tiền dạng số từ chuỗi "320.000 ₫" -> 320000
            const getPrice = (card) => {
                const priceText = card.querySelector('.price')?.textContent || '0';
                return parseInt(priceText.replace(/\D/g, ''), 10) || 0;
            };

            // Hàm hỗ trợ lấy tên sản phẩm
            const getName = (card) => {
                return card.querySelector('.product-info h3')?.textContent.trim() || '';
            };

            // Tiến hành sắp xếp theo lựa chọn
            if (selectedOption === 'Tên A-Z') {
                cards.sort((a, b) => getName(a).localeCompare(getName(b), 'vi'));
            } else if (selectedOption === 'Tên Z-A') {
                cards.sort((a, b) => getName(b).localeCompare(getName(a), 'vi'));
            } else if (selectedOption === 'Giá tăng dần') {
                cards.sort((a, b) => getPrice(a) - getPrice(b));
            } else if (selectedOption === 'Giá giảm dần') {
                cards.sort((a, b) => getPrice(b) - getPrice(a));
            } else {
                // Trở về thứ tự mặc định ban đầu
                cards = [...originalCards];
            }

            // Vẽ lại thứ tự sản phẩm lên giao diện
            cards.forEach(card => productGrid.appendChild(card));
        });
    }

}); // <-- Kết thúc khối DOMContentLoaded ở đây mới đúng