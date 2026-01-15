import threading
from collections import defaultdict


class Metrics:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._http_requests_total: dict[tuple[str, str], int] = defaultdict(int)
        self._webhook_requests_total: dict[str, int] = defaultdict(int)
        self._latency_buckets_ms = [100.0, 500.0, float("inf")]
        self._latency_bucket_counts = [0, 0, 0]
        self._latency_count = 0
        self._latency_sum = 0.0

    def observe_http(self, path: str, status: int, latency_ms: float) -> None:
        with self._lock:
            self._http_requests_total[(path, str(status))] += 1
            self._latency_count += 1
            self._latency_sum += float(latency_ms)
            for i, le in enumerate(self._latency_buckets_ms):
                if latency_ms <= le:
                    self._latency_bucket_counts[i] += 1

    def inc_webhook(self, result: str) -> None:
        with self._lock:
            self._webhook_requests_total[result] += 1

    def render_prometheus(self) -> str:
        lines: list[str] = []
        with self._lock:
            for (path, status), value in sorted(self._http_requests_total.items()):
                lines.append(f'http_requests_total{{path="{path}",status="{status}"}} {value}')
            for result, value in sorted(self._webhook_requests_total.items()):
                lines.append(f'webhook_requests_total{{result="{result}"}} {value}')

            for le, count in zip(self._latency_buckets_ms, self._latency_bucket_counts):
                le_label = "+Inf" if le == float("inf") else str(int(le))
                lines.append(f'request_latency_ms_bucket{{le="{le_label}"}} {count}')

            lines.append(f"request_latency_ms_count {self._latency_count}")
            lines.append(f"request_latency_ms_sum {self._latency_sum}")

        return "\n".join(lines) + "\n"
