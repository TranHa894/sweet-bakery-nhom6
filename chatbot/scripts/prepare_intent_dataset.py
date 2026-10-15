"""Kiểm tra bộ nhãn hiện có; không ghi đè các chỉnh sửa thủ công."""
from app.schemas import LLMTurn
from scripts.evaluate_intent_context import load_dataset


def main():
    identifiers = set()
    for split in ("dev", "test"):
        data, digest = load_dataset(split)
        for dialogue in data["dialogues"]:
            for item in dialogue["turns"]:
                LLMTurn.model_validate(item["label"])
                if item["id"] in identifiers:
                    raise ValueError("ID trùng giữa các split: " + item["id"])
                identifiers.add(item["id"])
        print(split, data["sample_count"], "lượt; schema hợp lệ; SHA256", digest)
    print("Chỉ kiểm tra nhãn, chưa gọi Qwen hoặc chấm chất lượng.")


if __name__ == "__main__":
    main()
