"use strict";
// Trang quản trị dùng API cùng origin. Không lưu mật khẩu/token vào localStorage.
(() => {
  const $ = (selector) => document.querySelector(selector);
  const money = (value) => Number.isFinite(value) ? new Intl.NumberFormat("vi-VN", {style:"currency",currency:"VND"}).format(value) : "Chưa xác định";
  const dateTime = (value) => value ? new Intl.DateTimeFormat("vi-VN",{dateStyle:"short",timeStyle:"short",timeZone:"Asia/Ho_Chi_Minh"}).format(new Date(value)) : "—";
  const labels = {pending_confirmation:"Chờ xác nhận",confirmed:"Đã xác nhận",delivering:"Đang giao",completed:"Hoàn tất",cancelled:"Đã hủy"};
  const categories = {cake:"Bánh kem",mini:"Bánh ngọt nhỏ",drink:"Trà & Cà phê"};
  const reasons = {customer_requested:"Khách cần nhân viên",two_unknown_turns:"Cần làm rõ nhu cầu",severe_allergy:"Dị ứng nghiêm trọng",allergen_requires_staff:"Cần xác minh dị ứng",complaint:"Khiếu nại",change_confirmed_order:"Sửa / hủy đơn đã xác nhận"};
  const pageInfo = {
    overview:["Tổng quan","Tổng quan cửa hàng","Những con số và công việc cần bạn quan tâm hôm nay."],
    orders:["Đơn hàng","Quản lý đơn hàng","Theo dõi và xử lý đơn từ website và chatbot trong cùng một danh sách."],
    products:["Sản phẩm","Danh mục sản phẩm","Chăm chút giá bán, số lượng tồn và tình trạng hiển thị."],
    requests:["Tư vấn & hỗ trợ","Lời nhắn từ khách","Xem phiếu hỗ trợ và các yêu cầu tư vấn đã lưu trước đây."]
  };
  const state = {page:"overview",orders:[],products:[],requests:[],status:"",offset:0,total:0,limit:20,editing:null,detail:null};
  let orderSequence=0, pageSequence=0, searchTimer, toastTimer, pendingAction;

  function el(tag, props={}, ...children) {
    const node=document.createElement(tag);
    for (const [key,value] of Object.entries(props)) {
      if (key==="class") node.className=value;
      else if (key==="text") node.textContent=value;
      else node.setAttribute(key,value);
    }
    for (const child of children.flat()) if (child!==null && child!==undefined) node.append(child instanceof Node ? child : document.createTextNode(String(child)));
    return node;
  }
  const badge=(text,kind="neutral")=>el("span",{class:"tag "+kind,text});
  function image(raw,name) {
    if (!raw) return null;
    const url=new URL(raw,location.origin+"/");
    if (url.origin!==location.origin || !/^\/(?:website\/)?images\/[\w.-]+$/.test(url.pathname)) return null;
    const img=el("img",{src:url.pathname,alt:name||"",loading:"lazy",width:"46",height:"46"});
    img.addEventListener("error",()=>{img.hidden=true;},{once:true});
    return img;
  }
  const productImage=(id)=>state.products.find(p=>p.id===id)?.image;
  const productCell=(name,raw,sub)=>el("div",{class:"product-cell"},image(raw,name),el("div",{},el("strong",{text:name||"Sản phẩm"}),sub?el("small",{text:sub}):null));
  const empty=(title,hint)=>el("div",{class:"empty-state"},el("div",{class:"empty-symbol",text:"◇"}),el("strong",{text:title}),el("p",{text:hint}));
  function table(headings,rows) {
    return el("table",{},el("thead",{},el("tr",{},headings.map(h=>el("th",{scope:"col",text:h})))),el("tbody",{},rows));
  }
  function toast(message) {
    clearTimeout(toastTimer);$("#toast").textContent=message;$("#toast").hidden=false;
    toastTimer=setTimeout(()=>{$("#toast").hidden=true;},4000);
  }
  function showError(error) {
    if ($("#workspace").hidden) {$("#login-error").textContent=error.message;return;}
    $("#page-error").textContent=error.message;$("#page-error").hidden=false;
  }
  function loggedOut() {
    ++pageSequence;++orderSequence;
    for (const dialog of document.querySelectorAll("dialog[open]")) dialog.close();
    state.orders=[];state.recent=[];state.products=[];state.requests=[];state.editing=null;state.detail=null;
    for (const selector of ["#recent-orders","#orders-table","#products-table","#requests-table","#detail-body","#product-preview","#attention-list"]) $(selector).replaceChildren();
    $("#workspace").hidden=true;$("#login-screen").hidden=false;$("#password").value="";
    $("#toast").hidden=true;$("#loading").hidden=true;
  }
  async function api(path,options={}) {
    let response;
    try { response=await fetch("/api/admin"+path,{...options,credentials:"same-origin",headers:{"Content-Type":"application/json",...options.headers},signal:options.signal||AbortSignal.timeout(15000)}); }
    catch (error) {throw new Error(error.name==="TimeoutError" ? "Máy chủ phản hồi chậm. Bạn thử làm mới sau ít giây nhé." : "Không kết nối được máy chủ. Kiểm tra website còn đang chạy.");}
    const data=await response.json();
    if (!response.ok) {
      if(response.status===401) loggedOut();
      const messages={
        invalid_password:"Mật khẩu chưa đúng. Bạn kiểm tra và thử lại nhé.",
        admin_login_required:"Phiên đăng nhập đã hết hạn. Bạn đăng nhập lại nhé.",
        product_changed_reload:"Giá hoặc tồn kho vừa thay đổi. Đóng khung này, làm mới danh mục rồi chỉnh lại để tránh ghi đè.",
        delivery_exceeds_hours:"Đơn không kịp giao trước 18:00 hôm nay. Hãy giữ đơn đã xác nhận và giao trong khung 08:00–18:00 ngày tiếp theo.",
        delivery_closed:"Chỉ bắt đầu giao từ 08:00 đến trước 18:00 giờ Việt Nam. Bạn giữ đơn đã xác nhận và giao vào giờ tiếp theo nhé.",
        legacy_delivery_slot:"Đơn cũ chọn giao tối. Hãy liên hệ khách và nhập giờ nhận mới trong 08:00–18:00 trước khi xác nhận.",
        invalid_transition:"Trạng thái đơn đã thay đổi hoặc không cho phép thao tác này. Hãy làm mới.",
        invalid_date_range:"Ngày bắt đầu phải trước hoặc bằng ngày kết thúc.",
        origin_not_allowed:"Yêu cầu không đúng nguồn website.",
        try_again_in_one_minute:"Đăng nhập sai quá nhiều lần. Bạn chờ một phút rồi thử lại.",
        database_busy_or_unavailable:"Database đang bận. Bạn chờ một chút rồi thử lại."
      };
      const failure=new Error(messages[data.detail] || (response.status===404 ? "Máy chủ đang dùng bản cũ. Bạn dừng rồi chạy lại main.py để tải chức năng quản trị mới." : response.status===422 ? (data.fields?.some(field=>field.type==="delivery_hours") ? "Giờ nhận cần nằm trong 08:00–18:00 giờ Việt Nam." : "Thông tin chưa hợp lệ. Kiểm tra các trường vừa nhập.") : "Chưa thực hiện được thao tác. Bạn làm mới rồi thử lại."));
      failure.status=response.status;throw failure;
    }
    return data;
  }
  const run=(task)=>Promise.resolve().then(task).catch(showError);
  async function withButton(button,task) {
    button.disabled=true;try {return await task();} finally {button.disabled=false;}
  }
  function orderRows(orders) {
    return orders.map(order=>el("tr",{},
      el("td",{class:"code"},el("strong",{class:"order-code",text:order.orderId}),el("small",{text:(order.orderSource==="chatbot"?"Chatbot · ":"Website · ")+dateTime(order.createdAt)})),
      el("td",{},el("strong",{text:order.customer?.fullName||"Chưa có tên"}),el("small",{text:order.customer?.phone||"—"})),
      el("td",{},badge(labels[order.status]||order.status,order.status)),
      el("td",{class:"money",text:money(order.subtotal)}),
      el("td",{},el("button",{class:"text-link","data-order":order.orderId,text:"Xem đơn →"}))
    ));
  }
  function renderOverview(data) {
    $("#stat-today").textContent=data.todayOrders;
    $("#stat-pending").textContent=data.orders.pending_confirmation;
    $("#stat-value").textContent=money(data.completedMerchandiseValue);
    $("#stat-products").textContent=data.products.active;
    $("#stat-product-total").textContent="Trên "+data.products.total+" sản phẩm trong danh mục";
    $("#nav-pending").textContent=data.orders.pending_confirmation;$("#nav-pending").hidden=!data.orders.pending_confirmation;
    const max=Math.max(1,...data.trend.map(d=>d.count));
    $("#order-chart").replaceChildren(...data.trend.map(day=>{
      const bar=el("div",{class:"chart-bar"});bar.style.height=Math.max(3,day.count/max*120)+"px";
      return el("div",{class:"chart-column"},el("strong",{text:day.count}),bar,el("span",{text:day.day.slice(8)+"/"+day.day.slice(5,7)}));
    }));
    $("#order-chart").setAttribute("aria-label","Đơn trong 7 ngày: "+data.trend.map(d=>d.day+": "+d.count).join("; "));
    const attention=[
      ["Đơn chờ xác nhận","Sẵn sàng để bạn kiểm tra",data.orders.pending_confirmation,"orders"],
      ["Sản phẩm tồn thấp","Còn tối đa 10 đơn vị",data.products.lowStock.length,"products"],
      ["Yêu cầu tư vấn","Tổng yêu cầu đã được lưu",data.consultationCount,"requests"],
      ["Phiếu hỗ trợ","Xem nội dung cần nhân viên",data.ticketCount,"requests"]
    ];
    $("#attention-list").replaceChildren(...attention.map(([title,sub,count,page])=>el("div",{class:"attention-row"},el("div",{},el("button",{class:"text-link","data-go":page,text:title}),el("small",{text:sub})),el("span",{class:"attention-number",text:count}))));
    state.recent=data.recentOrders;
    $("#recent-orders").replaceChildren(data.recentOrders.length ? table(["MÃ ĐƠN / THỜI GIAN","KHÁCH HÀNG","TRẠNG THÁI","TIỀN HÀNG",""],orderRows(data.recentOrders)) : empty("Chưa có đơn hàng nào","Đơn được gửi từ giỏ hàng sẽ xuất hiện ở đây."));
    $("#last-updated").textContent="Cập nhật lúc "+dateTime(data.updatedAt);
  }
  function orderParams() {
    const params=new URLSearchParams({limit:String(state.limit),offset:String(state.offset),include_requests:"false"});
    for(const [key,value] of [["q",$("#order-search").value.trim()],["status",state.status],["dateFrom",$("#date-from").value],["dateTo",$("#date-to").value]]) if(value) params.set(key,value);
    return params;
  }
  async function loadOrders() {
    $("#page-error").hidden=true;
    const sequence=++orderSequence;
    const data=await api("/orders?"+orderParams());
    if(sequence!==orderSequence) return;
    state.orders=data.orders;state.total=data.total;
    if(state.offset>=data.total && state.offset>0) {state.offset=0;return loadOrders();}
    $("#orders-table").replaceChildren(data.orders.length ? table(["MÃ ĐƠN / THỜI GIAN","KHÁCH HÀNG","TRẠNG THÁI","TIỀN HÀNG",""],orderRows(data.orders)) : empty("Không tìm thấy đơn phù hợp","Bạn thử thay đổi từ khóa hoặc bỏ bớt bộ lọc nhé."));
    $("#order-count").textContent=data.total+" đơn phù hợp";
    $("#page-info").textContent=data.total ? (state.offset+1)+"–"+Math.min(state.offset+state.limit,data.total)+" / "+data.total+" đơn" : "0 đơn";
    $("#previous-page").disabled=state.offset===0;$("#next-page").disabled=state.offset+state.limit>=data.total;
    $("#export-orders").disabled=!data.orders.length;
  }
  const normalize=(text)=>String(text||"").normalize("NFD").replace(/[\u0300-\u036f]/g,"").replace(/đ/g,"d").replace(/Đ/g,"D").toLowerCase();
  function renderProducts() {
    const term=normalize($("#product-search").value.trim()),category=$("#product-category").value,filter=$("#product-state").value;
    const products=state.products.filter(p=>normalize(p.name+" "+p.id).includes(term) && (!category||p.category===category) && (!filter||filter==="active"&&p.active||filter==="inactive"&&!p.active||filter==="low"&&p.active&&p.stock!==null&&p.stock<=10));
    $("#product-count").textContent=products.length+" / "+state.products.length+" sản phẩm";
    $("#products-table").replaceChildren(products.length ? table(["SẢN PHẨM","NHÓM","GIÁ BÁN","TỒN KHO","HIỂN THỊ",""],products.map(p=>el("tr",{},
      el("td",{},productCell(p.name,p.image,p.id)),el("td",{text:categories[p.category]||p.category}),
      el("td",{class:"money",text:money(p.price)}),el("td",{},p.stock===null ? badge("Chưa rõ","neutral") : el("span",{class:"stock-number"+(p.stock<=10?" stock-warning":""),text:p.stock})),
      el("td",{},badge(p.active?"Đang bán":"Tạm ẩn",p.active?"selling":"inactive")),
      el("td",{},el("button",{class:"text-link","data-edit":p.id,text:"Chỉnh sửa"}))
    ))) : empty("Không có sản phẩm phù hợp","Thử tên khác hoặc bỏ bộ lọc nhóm sản phẩm."));
  }
  function requestCustomer(record) {
    return {name:record.checkout_form?.fullName||record.slots?.name||"Chưa cung cấp",phone:record.checkout_form?.phone||record.slots?.phone||"—"};
  }
  function renderRequests() {
    const term=normalize($("#request-search").value.trim()),type=$("#request-type").value;
    const records=state.requests.filter(r=>(!type||r.recordType===type)&&normalize(JSON.stringify([r.id,requestCustomer(r),r.summary,r.checkout_summary?.items])).includes(term));
    $("#request-count").textContent=records.length+" / "+state.requests.length+" bản ghi đã tải";
    $("#requests-table").replaceChildren(records.length ? table(["MÃ / THỜI GIAN","KHÁCH HÀNG / NỘI DUNG","LOẠI","TRẠNG THÁI",""],records.map(r=>{
      const c=requestCustomer(r);
      return el("tr",{},el("td",{class:"code"},el("strong",{class:"order-code",text:r.order_code||r.id}),el("small",{text:dateTime(r.created_at)})),
        el("td",{},el("strong",{text:r.recordType==="ticket" ? reasons[r.reason]||"Cần nhân viên hỗ trợ" : c.name}),el("small",{text:r.recordType==="ticket" ? (r.priority==="high"?"Ưu tiên cao":"Ưu tiên thường") : c.phone})),
        el("td",{},badge(r.recordType==="ticket"?"Phiếu hỗ trợ":"Tư vấn",r.priority==="high"?"priority-high":"neutral")),
        el("td",{},badge(r.recordType==="ticket"?"Chờ hỗ trợ":r.kind==="demo_order"?"Đơn mô phỏng":"Chờ tư vấn","pending_confirmation")),
        el("td",{},el("button",{class:"text-link","data-request":r.id,text:"Xem chi tiết →"})));
    })) : empty("Chưa có yêu cầu phù hợp","Yêu cầu và phiếu hỗ trợ của chatbot sẽ được hiển thị tại đây."));
  }
  async function showPage(page) {
    if(!pageInfo[page]) return;
    state.page=page;const sequence=++pageSequence;
    document.querySelectorAll(".page-section").forEach(section=>{section.hidden=section.id!=="page-"+page;});
    document.querySelectorAll(".nav-item").forEach(button=>{
      button.classList.toggle("active",button.dataset.page===page);
      if(button.dataset.page===page) button.setAttribute("aria-current","page");else button.removeAttribute("aria-current");
    });
    const [short,title,description]=pageInfo[page];$("#breadcrumb-page").textContent=short;$("#page-title").textContent=title;$("#page-description").textContent=description;
    $("#page-kicker").textContent=page==="overview"?"MỘT NGÀY LÀM VIỆC THẬT NGỌT":"QUẢN TRỊ CỬA HÀNG";
    $("#page-error").hidden=true;$("#loading").hidden=false;
    try {
      if(page==="overview") {const data=await api("/overview");if(sequence===pageSequence) renderOverview(data);}
      if(page==="orders") await loadOrders();
      if(page==="products") {const data=await api("/products");if(sequence===pageSequence){state.products=data.products;renderProducts();}}
      if(page==="requests") {const data=await api("/requests");if(sequence===pageSequence){state.requests=data.records;renderRequests();}}
    } finally {if(sequence===pageSequence) $("#loading").hidden=true;}
  }
  function detailSection(title,lines) {
    return el("section",{class:"detail-section"},el("h3",{text:title}),lines.filter(Boolean).map(line=>el("p",{text:line})));
  }
  function detailItems(items) {
    return el("div",{class:"detail-items table-wrap"},table(["SẢN PHẨM","SL","ĐƠN GIÁ","THÀNH TIỀN"],items.map(item=>el("tr",{},
      el("td",{},productCell(item.name||item.product_name,item.image||productImage(item.product_id),"")),
      el("td",{text:item.quantity}),el("td",{class:"money",text:money(item.unit_price??item.unit_price_vnd)}),
      el("td",{class:"money",text:money(item.line_total_vnd??((item.unit_price??item.unit_price_vnd)*item.quantity))})
    ))));
  }
  function openOrder(id) {
    const order=[...state.orders,...(state.recent||[])].find(o=>o.orderId===id);if(!order) return;
    state.detail=order;$("#detail-kicker").textContent=order.orderSource==="chatbot"?"ĐƠN HÀNG TỪ CHATBOT":"ĐƠN HÀNG TỪ WEBSITE";$("#detail-title").textContent=order.orderId;
    const address=order.shippingAddress||{},delivery=order.delivery||{},slots={morning:"Buổi sáng · 08–12h",afternoon:"Buổi chiều · 12–18h",evening:"Khung giờ cũ ngoài giờ giao · cần xác nhận lại"};
    const content=el("div",{class:"dialog-content"},
      el("div",{class:"detail-meta"},badge(labels[order.status],order.status),el("span",{class:"muted",text:"Tạo lúc "+dateTime(order.createdAt)})),
      el("div",{class:"detail-grid"},detailSection("Khách hàng",[order.customer?.fullName,order.customer?.phone,order.customer?.email]),
        detailSection("Thông tin nhận hàng",[[address.addressLine,address.ward,address.province].filter(Boolean).join(", "),"Ngày mong muốn: "+(delivery.requestedDate||"Chưa chọn"),slots[delivery.requestedSlot]||"Khung giờ chờ xác nhận"])),
      detailItems(order.items),
      el("div",{class:"detail-totals"},el("p",{},el("span",{text:"Tiền hàng"}),el("b",{text:money(order.subtotal)})),el("p",{},el("span",{text:"Phí giao hàng"}),el("span",{text:order.shippingFee===null?"Chờ xác nhận":money(order.shippingFee)})),el("p",{},el("span",{text:"Thanh toán COD"}),el("span",{text:"Chưa xác nhận thu tiền"})),el("p",{},el("span",{text:order.total===null?"Tạm tính tiền hàng":"Tổng tiền"}),el("span",{text:money(order.total??order.subtotal)}))),
      el("div",{class:"detail-notes"},el("p",{text:"Lời chúc: "+(order.cakeMessage||"—")}),el("p",{text:"Ghi chú: "+(order.note||"—")})));
    if(address.location){
      const a=el("a",{href:"https://www.openstreetmap.org/?mlat="+address.location.latitude+"&mlon="+address.location.longitude+"#map=17/"+address.location.latitude+"/"+address.location.longitude,target:"_blank",rel:"noopener",text:"Xem vị trí giao trên bản đồ ↗"});
      content.append(a);
    }
    const estimate=order.deliveryTracking?.estimate;
    if(estimate?.available)content.append(el("p",{class:"section-footnote",text:"Dự kiến nhận: "+(estimate.displayWindow?.text||"Cần xác nhận lại lịch giao")+". "+estimate.notice}));
    $("#detail-body").replaceChildren(content);
    const buttons=[el("button",{class:"button secondary",id:"print-order",text:"In đơn"})];
    const transitions=order.status==="pending_confirmation"?["confirmed","cancelled"]:order.status==="confirmed"?["delivering","completed","cancelled"]:order.status==="delivering"?["completed","cancelled"]:[];
    for(const status of transitions) buttons.push(el("button",{class:"button "+(status==="cancelled"?"secondary":"primary"),"data-update-status":status,text:status==="confirmed"?"Xác nhận đơn":status==="delivering"?"Bắt đầu giao":status==="completed"?"Đã giao đến địa chỉ":"Hủy đơn"}));
    if(order.status==="confirmed")buttons.push(el("button",{class:"button secondary","data-update-status":"confirmed",text:"Chỉnh giờ giao"}));
    $("#detail-actions").replaceChildren(...buttons);$("#detail-dialog").showModal();
  }
  function openRequest(id) {
    const r=state.requests.find(record=>record.id===id);if(!r) return;
    $("#detail-kicker").textContent=r.recordType==="ticket"?"PHIẾU HỖ TRỢ":"YÊU CẦU TƯ VẤN";$("#detail-title").textContent=r.order_code||r.id;
    const c=requestCustomer(r),form=r.checkout_form||{},items=r.checkout_summary?.items||r.items||[];
    const content=el("div",{class:"dialog-content"},
      el("div",{class:"detail-meta"},badge(r.recordType==="ticket"?"Chờ hỗ trợ":r.kind==="demo_order"?"Đơn mô phỏng":"Chờ tư vấn","pending_confirmation"),el("span",{class:"muted",text:dateTime(r.created_at)})),
      el("div",{class:"detail-grid"},detailSection("Liên hệ",[c.name,c.phone,form.email]),
        detailSection("Thông tin đã cung cấp",[[form.addressLine,form.ward,form.province].filter(Boolean).join(", "),"Ngày mong muốn: "+(form.deliveryDate||"Chưa chọn")])));
    if(items.length) content.append(detailItems(items));
    if(r.recordType==="ticket") content.append(detailSection("Nội dung hỗ trợ",[reasons[r.reason]||r.reason,r.summary,"Ưu tiên: "+(r.priority==="high"?"Cao":"Thường"),r.note]));
    content.append(el("div",{class:"detail-notes"},el("p",{text:"Lời chúc: "+(form.cakeMessage||"—")}),el("p",{text:"Ghi chú: "+(form.note||"—")})),el("p",{class:"section-footnote",text:"Bản ghi của chatbot, không tự chuyển thành đơn website hoặc xác nhận thu tiền."}));
    $("#detail-body").replaceChildren(content);$("#detail-actions").replaceChildren(el("button",{class:"button secondary","data-close":"detail-dialog",text:"Đóng"}));$("#detail-dialog").showModal();
  }
  function openProduct(id) {
    const product=state.products.find(p=>p.id===id);if(!product)return;
    state.editing=product;$("#product-preview").replaceChildren(productCell(product.name,product.image,product.id+" · "+categories[product.category]));
    $("#edit-price").value=product.price??"";$("#edit-stock").value=product.stock??"";$("#edit-active").checked=product.active;$("#product-error").textContent="";$("#product-dialog").showModal();
  }
  function confirmStatus(status) {
    const order=state.detail;if(!order)return;
    const rescheduling=order.status===status;
    $("#confirm-title").textContent=rescheduling?"Cập nhật lịch giao đơn hàng?":status==="cancelled"?"Hủy đơn hàng này?":status==="completed"?"Xác nhận đã giao đến địa chỉ?":status==="delivering"?"Bắt đầu giao đơn hàng?":"Xác nhận tiếp nhận đơn?";
    $("#confirm-description").textContent=order.orderId+"\n"+(status==="cancelled"?"Hoàn lại số lượng hàng vào tồn kho; đơn đã hủy không thể mở lại.":status==="completed"?"Chỉ đánh dấu khi bạn đã kiểm tra việc giao hàng. Trạng thái đã giao sẽ hiện trong chatbot của khách; không tự xác nhận đã thanh toán.":"Trạng thái và giờ nhận dự kiến sẽ cập nhật trong chatbot của khách. Thời gian nhận chỉ là dự kiến.");
    const old=$("#expected-arrival");if(old)old.closest("label").remove();
    if(["confirmed","delivering"].includes(status)){
      const input=el("input",{id:"expected-arrival",type:"datetime-local"});
      input.required=rescheduling;
      input.addEventListener("input",()=>{
        const clock=input.value.slice(11,16);
        input.setCustomValidity(input.value&&(clock<"08:00"||clock>"18:00")?"Giờ nhận cần trong 08:00–18:00 giờ Việt Nam.":"");
      });
      const label=el("label",{class:"arrival-label",text:"Giờ nhận dự kiến · 08:00–18:00 (giờ Việt Nam)"});label.append(input,el("small",{class:"muted",text:"Chỉ giao 08:00–18:00. Để trống để hệ thống ước tính trong khung giờ này."}));
      $("#confirm-description").after(label);
    }
    $("#confirm-action").classList.toggle("danger",status==="cancelled");$("#confirm-error").textContent="";
    pendingAction=async()=>{
      const body={status},value=$("#expected-arrival")?.value;
      if(value)body.expectedArrival=value+":00+07:00";
      await api("/orders/"+encodeURIComponent(order.orderId),{method:"PATCH",body:JSON.stringify(body)});
      $("#confirm-dialog").close();$("#detail-dialog").close();
      toast("Đã cập nhật đơn: "+labels[status]+".");await showPage(state.page);
    };
    $("#confirm-dialog").showModal();
  }
  function exportOrders() {
    const safe=(value)=>{let s=String(value??"");if(/^[\s]*[=+\-@\t\r\n]/.test(s))s="'"+s;return '"'+s.replace(/"/g,'""')+'"';};
    const header=["Mã đơn","Ngày tạo (giờ VN)","Khách hàng","Điện thoại","Trạng thái","Tiền hàng (VNĐ)","Phí giao hàng","Thanh toán"];
    const rows=state.orders.map(o=>[o.orderId,dateTime(o.createdAt),o.customer?.fullName,o.customer?.phone,labels[o.status],o.subtotal,o.shippingFee??"Chờ xác nhận","Chưa xác nhận thu tiền"]);
    const blob=new Blob(["\ufeff"+[header,...rows].map(row=>row.map(safe).join(",")).join("\r\n")],{type:"text/csv;charset=utf-8"});
    const url=URL.createObjectURL(blob),link=el("a",{href:url,download:"sweet-bakery-don-hang.csv"});link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);toast("Đã xuất "+state.orders.length+" đơn trên trang hiện tại.");
  }

  $("#today-label").textContent=new Intl.DateTimeFormat("vi-VN",{dateStyle:"long",timeZone:"Asia/Ho_Chi_Minh"}).format(new Date());
  $("#login").addEventListener("submit",event=>{
    event.preventDefault();$("#login-error").textContent="";
    run(()=>withButton(event.submitter,async()=>{
      await api("/login",{method:"POST",body:JSON.stringify({password:$("#password").value})});
      $("#password").value="";$("#login-screen").hidden=true;$("#workspace").hidden=false;
      await showPage("overview");
    }));
  });
  $("#toggle-password").addEventListener("click",()=>{
    const visible=$("#password").type==="password";$("#password").type=visible?"text":"password";$("#toggle-password").textContent=visible?"Ẩn":"Hiện";
    $("#toggle-password").setAttribute("aria-pressed",String(visible));$("#toggle-password").setAttribute("aria-label",visible?"Ẩn mật khẩu":"Hiện mật khẩu");
  });
  for(const selector of ["#logout","#mobile-logout"]) $(selector).onclick=()=>run(async()=>{await api("/logout",{method:"POST"});loggedOut();$("#login-error").textContent="";});
  $("#refresh").onclick=()=>run(()=>withButton($("#refresh"),()=>showPage(state.page)));
  document.addEventListener("click",event=>{
    const button=event.target.closest("button");if(!button)return;
    if(button.dataset.close) $( "#"+button.dataset.close).close();
    if(button.dataset.page||button.dataset.go) run(()=>showPage(button.dataset.page||button.dataset.go));
    if(button.dataset.showStatus) {state.status=button.dataset.showStatus;state.offset=0;updateStatusTabs();run(()=>showPage("orders"));}
    if(button.dataset.order) openOrder(button.dataset.order);
    if(button.dataset.request) openRequest(button.dataset.request);
    if(button.dataset.edit) openProduct(button.dataset.edit);
    if(button.dataset.updateStatus) confirmStatus(button.dataset.updateStatus);
    if(button.id==="print-order") window.print();
  });
  function updateStatusTabs() {document.querySelectorAll("[data-status]").forEach(b=>{b.classList.toggle("active",b.dataset.status===state.status);b.setAttribute("aria-pressed",String(b.dataset.status===state.status));});}
  $("#order-status-tabs").onclick=event=>{const button=event.target.closest("[data-status]");if(!button)return;state.status=button.dataset.status;state.offset=0;updateStatusTabs();run(loadOrders);};
  $("#order-filters").onsubmit=event=>{event.preventDefault();clearTimeout(searchTimer);state.offset=0;run(loadOrders);};
  $("#order-search").oninput=()=>{clearTimeout(searchTimer);searchTimer=setTimeout(()=>{state.offset=0;run(loadOrders);},300);};
  $("#clear-filters").onclick=()=>{$("#order-filters").reset();state.status="";state.offset=0;updateStatusTabs();run(loadOrders);};
  $("#previous-page").onclick=()=>{state.offset=Math.max(0,state.offset-state.limit);run(loadOrders);};
  $("#next-page").onclick=()=>{state.offset+=state.limit;run(loadOrders);};
  $("#export-orders").onclick=exportOrders;
  for(const selector of ["#product-search","#product-category","#product-state"]) $(selector).addEventListener(selector.includes("search")?"input":"change",renderProducts);
  for(const selector of ["#request-search","#request-type"]) $(selector).addEventListener(selector.includes("search")?"input":"change",renderRequests);
  $("#product-form").onsubmit=async event=>{
    event.preventDefault();$("#product-error").textContent="";
    await withButton($("#save-product"),async()=>{
      try {
        const p=state.editing;await api("/products/"+encodeURIComponent(p.id),{method:"PATCH",body:JSON.stringify({price:Number($("#edit-price").value),stock:Number($("#edit-stock").value),active:$("#edit-active").checked,expectedRevision:p.revision})});
        $("#product-dialog").close();toast("Đã lưu giá, tồn kho và trạng thái sản phẩm.");await showPage("products");
      } catch(error) {$("#product-error").textContent=error.message;}
    });
  };
  $("#confirm-form").onsubmit=async event=>{
    event.preventDefault();$("#confirm-error").textContent="";
    await withButton($("#confirm-action"),async()=>{try {await pendingAction();} catch(error){$("#confirm-error").textContent=error.message;}});
  };
  // Khôi phục phiên cookie; HTTP 401 lúc mở trang chỉ đưa về màn hình đăng nhập.
  updateStatusTabs();
  api("/session").then(async()=>{$("#login-screen").hidden=true;$("#workspace").hidden=false;await showPage("overview");}).catch(error=>{if(error.status!==401) showError(error);});
})();
