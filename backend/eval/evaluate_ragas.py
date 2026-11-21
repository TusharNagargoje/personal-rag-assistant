"""Optional RAGAS adapter; reports a clear skip when no evaluation set is configured."""
import json
from pathlib import Path


def main() -> None:
    dataset_path = Path(__file__).parent / "test_dataset.json"
    dataset = json.loads(dataset_path.read_text(encoding="utf-8"))
    try:
        import ragas  # noqa: F401
    except ImportError:
        print(f"Loaded {len(dataset)} reference examples. Install ragas and supply generated answers/contexts to score the benchmark.")
        return
    print("RAGAS is installed. This starter dataset has references only; run the application evaluation adapter to collect answer and context columns before scoring.")


if __name__ == "__main__":
    main()
