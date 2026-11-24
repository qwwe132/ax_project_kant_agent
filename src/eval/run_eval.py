#하네스
#평가질문을 사람이 하나씩 입력하지 않고 프로그램이 대신 돌려서 결과를 파일에 남기게 하려함. 
# 모든 질문을 똑같은 조건으로 돌려 공정한 비교를 위함. 

import argparse
import json
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

#TO-DO 검색 코드 바꿈
def retrieve(question: str) -> list[dict]:
    """Search step. Returns a list of chunks, best first."""
    path = ROOT / "data" / "fixtures" / "sample-chunks.json"
    return json.loads(path.read_text(encoding="utf-8"))

#TO-DO 답변 코드로 바꿈
def answer(question: str, chunks: list[dict]) -> dict:
    """Answer step. Returns the answer text, citations, and a status."""
    return {"answer": "", "citations": [], "status": "no_evidence"}

#본체
def run(run_id: str, config: str, eval_file: str) -> Path:
    questions = json.loads((ROOT / eval_file).read_text(encoding="utf-8"))

    out_dir = ROOT / "results"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"{run_id}.jsonl"

    with out_path.open("w", encoding="utf-8") as f:
        for item in questions:
            record = {
                "run_id": run_id,
                "question_id": item["id"],
                "config": config,
                "candidates": [],
                "answer": "",
                "citations": [],
                "status": "error",
            }

            start = time.perf_counter()
            try:
                chunks = retrieve(item["question"])
                record["candidates"] = [
                    {
                        "rank": rank,
                        "document_id": c["document_id"],
                        "chunk_id": c["chunk_id"],
                        "source_location": c["source_location"],
                    }
                    for rank, c in enumerate(chunks, start=1)
                ]

                result = answer(item["question"], chunks)
                record["answer"] = result["answer"]
                record["citations"] = result["citations"]
                record["status"] = result["status"]
            except Exception as e:
                record["status"] = "error"
                record["error"] = repr(e)

            record["latency_sec"] = round(time.perf_counter() - start, 3)
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
            print(f"{item['id']}: {record['status']} ({record['latency_sec']}s)")

    print("saved:", out_path)
    return out_path


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("run_id")
    parser.add_argument("config")
    parser.add_argument("eval_file")
    args = parser.parse_args()
    run(args.run_id, args.config, args.eval_file)