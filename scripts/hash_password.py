"""Sinh chuỗi băm mật khẩu cho AUTH_USERS (không lưu mật khẩu thường trong .env).

    python scripts/hash_password.py              # nhập mật khẩu (không hiện ra màn hình)
    AUTH_USERS=demo:<chuỗi in ra>                 # dán vào .env
"""

import getpass
import sys

from vessel_chat.api.auth import hash_password


def main() -> None:
    password = getpass.getpass("Mật khẩu: ")
    if not password:
        sys.exit("Mật khẩu không được trống")
    if getpass.getpass("Nhập lại: ") != password:
        sys.exit("Hai lần nhập không khớp")
    print(hash_password(password))


if __name__ == "__main__":
    main()
