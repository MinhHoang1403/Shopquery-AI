"""Bounded synthetic CPU/CUDA smoke; never calls generation or embedding providers."""

import argparse
import json
import math
import resource
import statistics
import threading
from concurrent.futures import ThreadPoolExecutor
from time import perf_counter
from typing import Any

from app.core.config import Settings
from app.rag.repository import RetrievedChunk
from app.rag.reranker import build_reranker

CASES = (
    (
        "delivery",
        "How long does standard delivery take?",
        "Standard delivery takes two working days after the parcel is dispatched.",
    ),
    (
        "warranty",
        "Thời hạn bảo hành pin là bao lâu?",
        "Chính sách pin: thời hạn bảo hành là 12 tháng kể từ ngày mua.",
    ),
    (
        "tuition",
        "Học viên phải đóng học phí trước ngày nào?",
        "Học viên cần hoàn thành đóng học phí trước ngày 15 tháng 9.",
    ),
)
DISTRACTORS = (
    "Oranges and lemons are citrus fruit.",
    "A triangle has three sides.",
    "The office walls are painted blue.",
    "The database table has an integer primary key.",
    "The train travels north through the mountains.",
    "Chúng tôi trồng cây trong sân trường.",
    "Nhân viên họp vào thứ hai hàng tuần.",
    "Sách được xếp trên giá theo bảng chữ cái.",
    "Thực đơn có món rau và cơm.",
    "The laboratory measures air pressure.",
    "A keyboard is an input device.",
)


def candidates(positive: str, long_input: bool) -> list[RetrievedChunk]:
    texts = list(DISTRACTORS)
    texts.insert(8, positive)
    padding = (
        " This neutral synthetic paragraph tests bounded longer inputs." * 70 if long_input else ""
    )
    return [
        RetrievedChunk(i + 1, "synthetic.md", "Smoke", text + padding, i / 100)
        for i, text in enumerate(texts)
    ]


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--device", choices=("cpu", "cuda:0"), required=True)
    parser.add_argument("--repeats", type=int, choices=range(1, 4), default=2)
    parser.add_argument("--model-path", default="/models/bge")
    args = parser.parse_args()
    import torch

    settings = Settings(
        _env_file=None,
        rag_reranker_path=args.model_path,
        rag_reranker_device=args.device,
        rag_reranker_batch_size=2,
        rag_reranker_max_length=512,
    )
    ranker = build_reranker(settings)
    assert ranker is not None
    started = perf_counter()
    warmup = candidates(CASES[0][2], False)
    assert ranker.rerank(CASES[0][1], warmup, 3)[0] is warmup[8]
    assert not ranker._unavailable and ranker._model is not None
    model = ranker._model
    assert str(model.device) == args.device and not model.model.training
    load_seconds = perf_counter() - started
    forwards = {"calls": 0, "devices": set(), "max_batch": 0, "max_tokens": 0}

    forward_model = model.model
    original_forward = forward_model.forward

    def observe_forward(*arguments: Any, **kwargs: Any) -> Any:
        inputs = kwargs["input_ids"]
        forwards["calls"] += 1
        forwards["devices"].add(str(inputs.device))
        forwards["max_batch"] = max(forwards["max_batch"], inputs.shape[0])
        forwards["max_tokens"] = max(forwards["max_tokens"], inputs.shape[1])
        return original_forward(*arguments, **kwargs)

    # Sentence Transformers 5.7 invokes the bound forward method directly, bypassing hooks.
    forward_model.forward = observe_forward
    original_predict = model.predict
    predictions = []
    cuda_events_ms = []
    counters = {"active": 0, "max_active": 0, "calls": 0}
    counter_lock = threading.Lock()

    def predict(*arguments: Any, **kwargs: Any) -> Any:
        with counter_lock:
            counters["active"] += 1
            counters["calls"] += 1
            counters["max_active"] = max(counters["max_active"], counters["active"])
        try:
            if args.device.startswith("cuda"):
                start_event = torch.cuda.Event(enable_timing=True)
                end_event = torch.cuda.Event(enable_timing=True)
                start_event.record()
            scores = original_predict(*arguments, **kwargs)
            if args.device.startswith("cuda"):
                end_event.record()
                end_event.synchronize()
                cuda_events_ms.append(start_event.elapsed_time(end_event))
            predictions.append([float(value) for value in scores])
            return scores
        finally:
            with counter_lock:
                counters["active"] -= 1

    model.predict = predict
    if args.device.startswith("cuda"):
        torch.cuda.reset_peak_memory_stats()
    scenarios = []
    for long_input in (False, True):
        for label, question, positive in CASES:
            chunks = candidates(positive, long_input)
            latencies = []
            orders = []
            for _ in range(args.repeats):
                started = perf_counter()
                ranked = ranker.rerank(question, chunks, 3)
                if args.device.startswith("cuda"):
                    torch.cuda.synchronize()
                latencies.append((perf_counter() - started) * 1000)
                assert not ranker._unavailable and ranked[0] is chunks[8]
                assert all(any(item is original for original in chunks) for item in ranked)
                orders.append([item.chunk_id for item in ranked])
            assert all(order == orders[0] for order in orders)
            scores = predictions[-1]
            assert len(scores) == 12 and all(math.isfinite(value) for value in scores)
            scenarios.append(
                {
                    "case": label,
                    "input": "long_512" if long_input else "short",
                    "order": orders[0],
                    "scores": scores,
                    "samples_ms": latencies,
                    "p50_ms": statistics.median(latencies),
                    "p95_ms": sorted(latencies)[math.ceil(len(latencies) * 0.95) - 1],
                }
            )
            print(
                json.dumps(
                    {
                        "completed": label,
                        "input": scenarios[-1]["input"],
                        "p50_ms": scenarios[-1]["p50_ms"],
                    }
                ),
                flush=True,
            )
    concurrent = None
    if args.device.startswith("cuda"):
        chunks = candidates(CASES[0][2], False)
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: ranker.rerank(CASES[0][1], chunks, 3), range(2)))
        assert all(result[0] is chunks[8] for result in results)
        assert counters["max_active"] == 1 and ranker._model is model
        concurrent = {
            "requests": 2,
            "max_active_predict": counters["max_active"],
            "same_model": True,
        }
    forward_model.forward = original_forward
    assert forwards["devices"] == {args.device}
    assert forwards["max_tokens"] == 512 and forwards["max_batch"] <= 2
    forwards["devices"] = sorted(forwards["devices"])
    report = {
        "device": str(model.device),
        "dtype": str(next(model.model.parameters()).dtype),
        "torch": torch.__version__,
        "cuda_build": torch.version.cuda,
        "gpu": torch.cuda.get_device_name(0) if args.device.startswith("cuda") else None,
        "load_seconds": load_seconds,
        "scenarios": scenarios,
        "concurrent": concurrent,
        "singleton": build_reranker(settings) is ranker,
        "peak_rss_mib": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024,
        "allocated_mib": torch.cuda.memory_allocated() / 2**20 if concurrent else 0,
        "reserved_mib": torch.cuda.memory_reserved() / 2**20 if concurrent else 0,
        "peak_allocated_mib": torch.cuda.max_memory_allocated() / 2**20 if concurrent else 0,
        "peak_reserved_mib": torch.cuda.max_memory_reserved() / 2**20 if concurrent else 0,
        "provider_calls": 0,
        "cuda_events_ms": cuda_events_ms,
        "forward": forwards,
    }
    print("SMOKE_RESULT " + json.dumps(report), flush=True)


if __name__ == "__main__":
    main()
