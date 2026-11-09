"use strict";
window.SweetDelivery=(()=>{
  const forms=new WeakMap();let configuration,leaflet;
  const node=(tag,text)=>{const n=document.createElement(tag);if(text)n.textContent=text;return n;};
  const getConfig=()=>configuration ||= fetch("/api/store").then(r=>{if(!r.ok)throw Error();return r.json();});
  function loadLeaflet(){
    if(window.L)return Promise.resolve(window.L);
    if(!leaflet)leaflet=new Promise((resolve,reject)=>{
      const css=node("link");css.rel="stylesheet";css.href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css";css.integrity="sha256-p4NxAoJBhIIN+hmNHrzRCf9tD/miZyoHS5obTRR9BMY=";css.crossOrigin="anonymous";document.head.append(css);
      const script=node("script");script.src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js";script.crossOrigin="anonymous";script.integrity="sha256-20nQCchB9co0qIjJZRGuk2/Z9VM+kNiyxNV1lvTlZBo=";
      script.onload=()=>resolve(window.L);script.onerror=()=>{leaflet=null;reject(Error("Không tải được bản đồ. Bạn vẫn có thể dùng vị trí hiện tại hoặc nhập địa chỉ."));};document.head.append(script);
    });return leaflet;
  }
  function mount(parent,form,initial=null){
    let point=initial?{...initial}:null,map,marker,store,mapping=false,drawMarker=()=>{};
    forms.set(form,{get:()=>point,dispose:()=>{if(map){map.remove();map=null;}forms.delete(form);}});
    const box=node("section");box.className="delivery-picker";
    const title=node("strong","Vị trí giao hàng"),intro=node("p","Bấm Vị trí hiện tại để lấy ghim giao hàng, hoặc mở bản đồ và chọn điểm. Bạn có thể nhập địa chỉ thay thế.");
    const actions=node("div");actions.className="delivery-map-actions";
    const locate=node("button","◎ Vị trí hiện tại"),open=node("button","Mở bản đồ"),clear=node("button","Bỏ vị trí");
    for(const b of [locate,open,clear]){b.type="button";b.className="delivery-map-button";actions.append(b);}
    const status=node("p");status.setAttribute("role","status");status.className="delivery-location-status";
    const canvas=node("div");canvas.className="delivery-map-canvas";canvas.hidden=true;canvas.setAttribute("aria-label","Bản đồ chọn địa chỉ giao hàng");
    const privacy=node("p","Điểm ghim xanh là vị trí tham chiếu cửa hàng. Chỉ lấy vị trí khi bạn bấm và cấp quyền. Bản đồ OpenStreetMap tải từ dịch vụ ngoài; không theo dõi vị trí liên tục.");privacy.className="delivery-map-note";
    box.append(title,intro,actions,status,canvas,privacy);parent.append(box);
    function requirements(){
      for(const name of ["province","ward","addressLine"]){
        const input=form.elements.namedItem(name);if(!input)continue;
        input.required=!point;input.setCustomValidity("");
        if(name==="addressLine")input.minLength=point?0:5;
        const label=input.closest("label");
        if(label?.firstChild?.nodeType===Node.TEXT_NODE)label.firstChild.textContent=label.firstChild.textContent.replace(/\s*\*\s*$/,"")+(point?"":" *");
      }
    }
    async function update(value){
      point=value;requirements();clear.hidden=!point;
      if(!point){status.textContent="Chưa chọn vị trí. Bạn nhập địa chỉ đầy đủ hoặc chọn ghim nhé.";return;}
      const accuracy=point.accuracy?" · Sai số khoảng "+Math.round(point.accuracy)+" m":"";
      status.textContent="Ghim giao: "+point.latitude.toFixed(5)+", "+point.longitude.toFixed(5)+accuracy+". Bạn kiểm tra đúng nơi nhận và bổ sung tầng/căn hộ nếu cần.";
      if(marker)marker.setLatLng([point.latitude,point.longitude]);
      if(map){drawMarker();map.panTo([point.latitude,point.longitude]);}
      try{
        const r=await fetch("/api/delivery/estimate",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(point)});
        const estimate=await r.json();if(value!==point)return;
        if(r.ok&&estimate.displayWindow){
          status.textContent+=" Dự kiến "+estimate.displayWindow.text+". Giờ giao hàng 08:00–18:00; thời gian có thể thay đổi theo giao thông.";
        }
      }catch{}
    }
    async function showMap(){
      canvas.hidden=false;if(map){map.invalidateSize();return;}
      if(mapping)return;mapping=true;
      try{
        const [L,config]=await Promise.all([loadLeaflet(),getConfig()]);store=config.store;if(!canvas.isConnected)return;
        map=L.map(canvas).setView(point?[point.latitude,point.longitude]:[store.latitude,store.longitude],14);
        L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png",{maxZoom:19,attribution:'&copy; <a href="https://www.openstreetmap.org/copyright" target="_blank" rel="noopener">OpenStreetMap</a>'}).addTo(map);
        L.circleMarker([store.latitude,store.longitude],{radius:9,color:"#17634b",fillOpacity:1}).addTo(map).bindTooltip(node("span",store.name));
        const icon=L.divIcon({className:"delivery-pin",html:"<span></span>",iconSize:[24,30],iconAnchor:[12,27]});
        function draw(){
          if(!point)return;
          if(!marker){marker=L.marker([point.latitude,point.longitude],{icon,draggable:true}).addTo(map);marker.on("dragend",()=>{const p=marker.getLatLng();update({latitude:p.lat,longitude:p.lng,accuracy:null});});}
          else marker.setLatLng([point.latitude,point.longitude]);
        }
        drawMarker=draw;
        map.on("click",e=>{update({latitude:e.latlng.lat,longitude:e.latlng.lng,accuracy:null});draw();});
        draw();map.invalidateSize();
      }catch(error){status.textContent=error.message||"Không tải được bản đồ; bạn vẫn nhập địa chỉ hoặc dùng GPS được.";}finally{mapping=false;}
    }
    locate.onclick=()=>{
      if(!window.isSecureContext){status.textContent="Lấy vị trí cần HTTPS hoặc localhost. Trên điện thoại hãy mở link HTTPS, hoặc nhập địa chỉ.";return;}
      if(!navigator.geolocation){status.textContent="Thiết bị chưa hỗ trợ định vị; bạn chọn trên bản đồ hoặc nhập địa chỉ nhé.";return;}
      locate.disabled=true;status.textContent="Đang lấy vị trí hiện tại…";
      navigator.geolocation.getCurrentPosition(position=>{
        locate.disabled=false;update({latitude:position.coords.latitude,longitude:position.coords.longitude,accuracy:position.coords.accuracy});showMap();
      },error=>{
        locate.disabled=false;status.textContent=error.code===1?"Bạn chưa cho phép vị trí. Có thể mở bản đồ để chọn điểm hoặc nhập địa chỉ.":"Chưa lấy được vị trí. Bạn thử lại, chọn điểm trên bản đồ hoặc nhập địa chỉ nhé.";
      },{enableHighAccuracy:true,timeout:12000,maximumAge:60000});
    };
    open.onclick=showMap;clear.onclick=()=>{if(marker){marker.remove();marker=null;}update(null);};
    update(point);
    getConfig().then(config=>{store=config.store;intro.textContent="Giao từ "+store.address+". Chọn ghim hoặc nhập địa chỉ; không tự suy ra số nhà/phòng từ GPS.";}).catch(()=>{box.hidden=true;});
    return box;
  }
  function summary(parent,point){
    if(!point)return;
    const p=node("p","Vị trí giao: "),a=node("a","Xem ghim trên bản đồ ↗");
    a.href="https://www.openstreetmap.org/?mlat="+encodeURIComponent(point.latitude)+"&mlon="+encodeURIComponent(point.longitude)+"#map=17/"+point.latitude+"/"+point.longitude;
    a.target="_blank";a.rel="noopener";p.append(a);parent.append(p);
  }
  return {mount,value:form=>forms.get(form)?.get()||null,dispose:form=>forms.get(form)?.dispose(),summary};
})();
