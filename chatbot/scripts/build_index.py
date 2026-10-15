"""Xây chỉ mục chính sách bằng embedding local đã cài; không tải model."""

import argparse
from app import config
from app.knowledge_loader import create_knowledge_repository
from app.retrieval import build_vector_index


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--force", action="store_true", help="Tính lại vector cả khi hash chưa đổi.")
    args = parser.parse_args()
    repository = create_knowledge_repository(config.KNOWLEDGE_MODE,
        config.DATABASE_PATH if config.KNOWLEDGE_MODE == "local_demo" else None)
    try:
        result = build_vector_index(repository, force=args.force)
    except (OSError, ValueError, KeyError, TypeError) as error:
        raise SystemExit("Chưa xây được vector index: " + str(error) + ". Keyword RAG vẫn dùng được; không tải model.")
    print(f"{result['status']}: {result['chunks']} điều khoản; {result['model']}; {result['version']}")


if __name__ == "__main__":
    main()
