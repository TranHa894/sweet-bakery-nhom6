"""Vị trí và ETA xấp xỉ; không gọi dịch vụ routing hoặc theo dõi GPS."""
import math
import os
from datetime import datetime, timedelta, timezone, time
from zoneinfo import ZoneInfo
from pydantic import BaseModel, ConfigDict, Field

class DeliveryLocation(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True, allow_inf_nan=False)
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)
    accuracy: float | None = Field(default=None, ge=0, le=100000)

DELIVERY_ZONE=ZoneInfo("Asia/Ho_Chi_Minh")
DELIVERY_OPEN=time(8,0)
DELIVERY_CLOSE=time(18,0)


def delivery_now():
    return datetime.now(timezone.utc)


def in_delivery_hours(value, *, dispatch=False):
    if value.tzinfo is None:
        return False
    clock=value.astimezone(DELIVERY_ZONE).time()
    return DELIVERY_OPEN<=clock<DELIVERY_CLOSE if dispatch else DELIVERY_OPEN<=clock<=DELIVERY_CLOSE


def fit_delivery_window(base, minutes, buffer):
    """Giữ cả khoảng ETA trong một ngày 08–18h; không chạy giao qua đêm."""
    local=base.astimezone(DELIVERY_ZONE)
    opening=datetime.combine(local.date(),DELIVERY_OPEN,tzinfo=DELIVERY_ZONE)
    closing=datetime.combine(local.date(),DELIVERY_CLOSE,tzinfo=DELIVERY_ZONE)
    if minutes+buffer>(closing-opening).total_seconds()/60:
        return None
    start=max(local,opening)
    if start+timedelta(minutes=minutes+buffer)>closing:
        start=opening+timedelta(days=1)
    return start+timedelta(minutes=minutes),start+timedelta(minutes=minutes+buffer),start!=local


def store_settings():
    return {"name":"Sweet Bakery · Đại học Công nghiệp Hà Nội",
        "address":os.getenv("STORE_ADDRESS","Cơ sở 1 · 298 Cầu Diễn, Hà Nội"),
        "latitude":float(os.getenv("STORE_LATITUDE","21.0536")),
        "longitude":float(os.getenv("STORE_LONGITUDE","105.7342")),
        "deliveryHours":{"opensAt":"08:00","closesAt":"18:00","timezone":"Asia/Ho_Chi_Minh"},
        "coordinatesNote":"Điểm tham chiếu khuôn viên; cần kiểm tra đúng cổng giao nhận.",
        "preparationMinutes":int(os.getenv("DELIVERY_PREPARATION_MINUTES","20")),
        "averageSpeedKmh":float(os.getenv("DELIVERY_SPEED_KMH","20")),
        "roadFactor":float(os.getenv("DELIVERY_ROAD_FACTOR","1.35")),
        "bufferMinutes":int(os.getenv("DELIVERY_BUFFER_MINUTES","10")),
        "estimateRadiusKm":float(os.getenv("DELIVERY_ESTIMATE_RADIUS_KM","50"))}

def estimate_delivery(location, *, now=None, preparation=True):
    if not location:
        return {"available":False,"notice":"Chưa có ghim vị trí; cửa hàng cần xác nhận giờ nhận."}
    point=DeliveryLocation.model_validate(location);settings=store_settings()
    lat1,lat2=map(math.radians,(settings["latitude"],point.latitude))
    dlat=lat2-lat1;dlon=math.radians(point.longitude-settings["longitude"])
    distance=6371*2*math.asin(min(1,math.sqrt(math.sin(dlat/2)**2+math.cos(lat1)*math.cos(lat2)*math.sin(dlon/2)**2)))
    if distance>settings["estimateRadiusKm"]:
        return {"available":False,"distanceKm":round(distance,2),"notice":"Vị trí ngoài phạm vi ước tính; cửa hàng sẽ liên hệ xác nhận."}
    road=distance*settings["roadFactor"]
    minutes=max(5,math.ceil(road/max(1,settings["averageSpeedKmh"])*60))
    minutes+=max(0,settings["preparationMinutes"]) if preparation else 0
    spread=max(5,settings["bufferMinutes"]);base=now or delivery_now()
    window=fit_delivery_window(base,minutes,spread)
    if window is None:
        return {"available":False,"notice":"Thời gian ước tính vượt khung giao 08:00–18:00; cửa hàng cần xác nhận lại."}
    start,end,adjusted=window
    result={"available":True,"distanceKm":round(distance,2),"estimatedRoadKm":round(road,2),
        "minutesMin":minutes,"minutesMax":minutes+spread,"earliestAt":start.isoformat(),
        "latestAt":end.isoformat(),"method":"distance_estimate","serviceWindowAdjusted":adjusted,
        "notice":"Chỉ giao 08:00–18:00 giờ Việt Nam. Ngoài giờ hoặc không kịp trước 18:00 sẽ dự kiến sang ngày sau; chưa có dữ liệu giao thông, cửa hàng xác nhận lại."}
    result["displayWindow"]=customer_delivery_window(result)
    return result


def customer_delivery_window(estimate):
    """Chỉ làm tròn bản hiển thị; giữ nguyên ETA gốc để kiểm tra nghiệp vụ."""
    if not estimate or not estimate.get("available"):
        return None
    try:
        start=datetime.fromisoformat(estimate["earliestAt"])
        end=datetime.fromisoformat(estimate["latestAt"])
        if start.tzinfo is None or end.tzinfo is None:
            return None
        start,end=start.astimezone(DELIVERY_ZONE),end.astimezone(DELIVERY_ZONE)
        if end<start or not all(in_delivery_hours(value) for value in (start,end)):
            return None
    except (ValueError,TypeError,KeyError):
        return None
    if start.date()==end.date() and end-start<timedelta(hours=1):
        opening=datetime.combine(start.date(),DELIVERY_OPEN,tzinfo=DELIVERY_ZONE)
        closing=datetime.combine(start.date(),DELIVERY_CLOSE,tzinfo=DELIVERY_ZONE)
        start=max(opening,start.replace(minute=0,second=0,microsecond=0))
        end=min(closing,max(end,start+timedelta(hours=2)))
        if end-start<timedelta(hours=1):
            start=max(opening,closing-timedelta(hours=1))
    weekdays=("Thứ Hai","Thứ Ba","Thứ Tư","Thứ Năm","Thứ Sáu","Thứ Bảy","Chủ Nhật")
    def day(value):
        return weekdays[value.weekday()]+", "+value.strftime("%d/%m/%Y")
    if start.date()==end.date():
        text=day(start)+", khoảng "+start.strftime("%H:%M")+"–"+end.strftime("%H:%M")+" (giờ Việt Nam)"
    else:
        text=day(start)+" "+start.strftime("%H:%M")+" – "+day(end)+" "+end.strftime("%H:%M")+" (giờ Việt Nam)"
    return {"startsAt":start.isoformat(),"endsAt":end.isoformat(),"text":text}


def delivery_dates_changed(previous_estimate,estimate):
    """So ngày Việt Nam của hai lịch hợp lệ, không suy ngày từ text thông báo."""
    old,new=customer_delivery_window(previous_estimate),customer_delivery_window(estimate)
    return bool(old and new and
                tuple(datetime.fromisoformat(old[key]).date() for key in ("startsAt","endsAt")) !=
                tuple(datetime.fromisoformat(new[key]).date() for key in ("startsAt","endsAt")))


def delivery_message(order_id,status,estimate=None,provisional=False,previous_estimate=None):
    texts={
        "pending_confirmation":f"Đơn {order_id} đã gửi tới cửa hàng, đang chờ xác nhận.",
        "confirmed":f"Cửa hàng đã xác nhận đơn {order_id} của bạn.",
        "delivering":f"Đơn {order_id} đang được giao tới vị trí bạn đã chọn.",
        "completed":f"Cửa hàng báo đơn {order_id} đã giao đến địa chỉ. Nếu bạn chưa nhận được hàng, hãy nhờ cửa hàng kiểm tra nhé.",
        "cancelled":f"Đơn {order_id} đã được hủy."
    }
    message=texts[status]
    window=customer_delivery_window(estimate)
    previous=customer_delivery_window(previous_estimate)
    if window:
        if delivery_dates_changed(previous_estimate,estimate):
            message+=" Lịch giao đã cập nhật: cũ "+previous["text"]+"; mới "+window["text"]+"."
        else:
            label="Lịch giao dự kiến đã thông báo: " if status in {"completed","cancelled"} else "Dự kiến nhận "
            message+=" "+label+window["text"]+"."
        if provisional:
            message+=" Đây chưa phải giờ giao đã xác nhận."
    else:
        message+=" Ngày và khung giờ giao chưa xác định; cửa hàng cần xác nhận lại."
    message+=" Giờ giao hàng 08:00–18:00; thời gian có thể thay đổi theo giao thông."
    if status=="pending_confirmation":
        message+=' Trong chatbot, bấm “Hủy đơn” dưới trạng thái đơn rồi xác nhận hủy. Nếu không thấy nút, nhắn “nhờ nhân viên hủy đơn” kèm mã '+order_id+'.'
    elif status!="cancelled":
        message+=' Để yêu cầu hủy, nhắn “nhờ nhân viên hủy đơn” kèm mã '+order_id+'; cửa hàng sẽ kiểm tra khả năng hủy.'
    else:
        message+=" Nếu cần kiểm tra việc hủy, nhắn “nhờ nhân viên” kèm mã "+order_id+"."
    return message
