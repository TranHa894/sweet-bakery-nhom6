"""Tạo bảng và seed phần còn thiếu, không xóa đơn/tồn kho đã thay đổi."""
from database import initialize, DB_PATH
if __name__ == '__main__':
    initialize()
    print(f'Database san sang: {DB_PATH}')
