"""
Benchmarking utilities to track round-trip/network latency and execution time for RPC calls.

This module is part of the NeuroRPC library for low-latency closed-loop experiments
integrating Python and LabVIEW (NI Linux RT). It extends the RPCTracker with the ability
to record request/response samples, compute execution and network latencies, and export
results in multiple formats (JSON, CSV, Excel).

Notes:
    - All time metrics are stored in milliseconds.
    - Timestamps use both wall-clock (time.time) and high-precision counters (time.perf_counter).
"""

import time
import uuid
import pandas as pd
import numpy as np
import json

from python.neuro_rpc.RPCTracker import RPCTracker

class Sample:
    """
    Represents a single request-response pair with timing and size metadata.

    Each sample records request and response timestamps, payload sizes, and computed
    metrics such as execution time (server side), total latency (request→response),
    and estimated network latency.
    """
    def __init__(self):
        """
        Initialize an empty Sample.

        All timestamps are initialized to None and metrics to 0.
        """
        self.request = {
            'timestamp': None,
            'payload_size': None,
            'raw': None
        }
        self.response = {
            'timestamp': None,
            'payload_size': None,
            'raw': None
        }
        self.metrics = {
            'exec_time': 0,
            'total_latency': 0,
            'network_latency': 0
        }

    def to_dict(self):
        """
        Serialize the sample to a plain dictionary.

        Returns:
            dict: A dictionary with ``request``, ``response``, and ``metrics`` fields.
        """
        return {
            'request': self.request,
            'response': self.response,
            'metrics': self.metrics
        }

class BenchmarkRun:
    """
    Represents a full benchmark run containing multiple samples and statistics.

    A BenchmarkRun groups samples under a common identifier and stores timing
    information (start/end/duration) as well as aggregate statistics
    (average execution time, total latency, network latency).
    """
    def __init__(self):
        """
        Initialize an empty BenchmarkRun.

        Timing fields are None until the run is started; stats are initialized to zero.
        """
        self.timing = {
            'start_time': None,
            'end_time': None,
            'duration': None
        }
        self.stats = {
            'samples_count': 0,
            'avg_exec_time': 0,
            'avg_total_latency': 0,
            'avg_network_latency': 0
        }
        self.samples = {}

    def to_dict(self):
        """
        Serialize the benchmark run to a dictionary.

        Includes timing, statistics, and all nested samples.

        Returns:
            dict: A dictionary with ``timing``, ``samples`` (serialized), and ``stats``.
        """
        return {
            'timing': self.timing,
            'samples': {k: v.to_dict() for k, v in self.samples.items()},
            'stats': self.stats
        }

class Benchmark(RPCTracker):
    """
    Benchmark manager for RPC experiments.

    Extends RPCTracker with functionality to record request/response metadata,
    compute latency metrics, and export results. Multiple runs can be stored
    in the same instance.
    """
    def __init__(self, *args, **kwargs):
        """
        Initialize the Benchmark manager.

        Args:
            *args: Positional arguments forwarded to ``RPCTracker``.
            **kwargs: Keyword arguments forwarded to ``RPCTracker``.
        """
        super().__init__(*args, **kwargs)
        self.bid = None
        self.benchmark_active = False
        self.data = {}
        self._current_run = None

    def check_bid(self, benchmark_id=None):
        """
        Ensure that a benchmark ID exists in memory.

        Args:
            benchmark_id (str | None): Optional benchmark ID. If None, use the current active ``bid``.

        Returns:
            str: A valid benchmark ID present in ``self.data``.

        Raises:
            ValueError: If the benchmark ID is not found.
        """
        bid = benchmark_id or self.bid
        if bid not in self.data:
            raise ValueError(f"No benchmark metadata found for ID: {bid}")
        return bid

    def start_benchmark(self, bid=None):
        """
        Start a new benchmark run.

        Args:
            bid (str | None): Optional benchmark ID. If None, a new UUID is generated.

        Returns:
            str: The benchmark ID assigned to this run.

        Notes:
            Resets the current run pointer.
        """
        self.bid = bid or str(uuid.uuid4())
        self.benchmark_active = True

        # Create new run
        run = BenchmarkRun()
        run.timing['start_time'] = time.time()

        self.data[self.bid] = run
        self._current_run = run

        self.logger.info(f"Benchmark started with ID: {self.bid}")
        return self.bid

    def track_outgoing_request(self, request, timeout=60, raw=False):
        """
        Track an outgoing request and create a Sample entry.

        Args:
            request: RPCRequest object being sent (must expose ``id``, ``to_json()``, and ``to_dict()``).
            timeout (int): Timeout in seconds associated with the request.
            raw (bool): If True, store the raw request dict under ``request['raw']``.

        Returns:
            Any: The result of ``RPCTracker.track_outgoing_request``.
        """
        result = super().track_outgoing_request(request, timeout=timeout)

        if self.benchmark_active and request.id is not None:
            # Create new sample
            sample = Sample()
            sample.request['timestamp'] = time.perf_counter() * 1000
            sample.request['payload_size'] = len(request.to_json())
            if raw:
                sample.request['raw'] = request.to_dict()

            self._current_run.samples[request.id] = sample

        return result

    def track_incoming_response(self, response, raw=False):
        """
        Track an incoming response and update the corresponding Sample.

        Args:
            response: RPCResponse object being received (must expose ``id``, ``to_json()``,
                ``to_dict()``, and ``exec_time`` in microseconds).
            raw (bool): If True, store the raw response dict under ``response['raw']``.

        Returns:
            Any: The result of ``RPCTracker.track_incoming_response``.
        """
        result = super().track_incoming_response(response)

        if self.benchmark_active and response.id is not None and response.id in self._current_run.samples:
            sample = self._current_run.samples[response.id]
            sample.response['timestamp'] = time.perf_counter() * 1000
            sample.response['payload_size'] = len(response.to_json())
            if raw:
                sample.response['raw'] = response.to_dict()

            sample.metrics['exec_time'] = response.exec_time / 1000  # Convert μs → ms
            # Calculate latencies
            sample.metrics['total_latency'] = sample.response['timestamp'] - sample.request['timestamp']
            sample.metrics['network_latency'] = abs(
                sample.metrics['total_latency'] - sample.metrics['exec_time']
            )

        return result

    def set_exec_time(self, response_id, exec_time):
        """
        Manually set execution time for a response sample.

        Args:
            response_id (str): ID of the response sample.
            exec_time (float): Execution time in microseconds (μs). Internally converted to milliseconds (ms).
        """
        if self.benchmark_active and response_id in self._current_run.samples:
            sample = self._current_run.samples[response_id]
            sample.metrics['exec_time'] = exec_time / 1000
            sample.metrics['network_latency'] = abs(
                sample.metrics['total_latency'] - sample.metrics['exec_time']
            )

    def stop_benchmark(self, benchmark_id=None):
        """
        Stop the current benchmark run and compute statistics.

        Args:
            benchmark_id (str | None): Optional benchmark ID. If None, uses the active run.

        Returns:
            None
        """
        bid = self.check_bid(benchmark_id)
        run = self.data[bid]

        run.timing['end_time'] = time.time()
        run.timing['duration'] = run.timing['end_time'] - run.timing['start_time']

        # Calculate statistics
        samples = run.samples.values()
        run.stats.update({
            'samples_count': len(samples),
            'avg_exec_time': np.mean([s.metrics['exec_time'] for s in samples]),
            'avg_total_latency': np.mean([s.metrics['total_latency'] for s in samples]),
            'avg_network_latency': np.mean([s.metrics['network_latency'] for s in samples])
        })

        self.benchmark_active = False
        self._current_run = None
        self.logger.info(f"Benchmark stopped with ID: {bid}")

    def data_to_dataframe(self):
        """
        Convert all benchmark data into a Pandas DataFrame.

        Each row corresponds to a sample with benchmark ID, timing, request/response,
        metrics, and run statistics.

        Returns:
            pandas.DataFrame: A flattened (normalized) table of benchmark data.
        """
        data_rows = []

        for bid, run in self.data.items():
            for sample_id, sample in run.samples.items():
                row = {
                    'benchmark_id': bid,
                    'sample_id': sample_id,
                    'timing': run.timing,
                    'request': sample.request,
                    'response': sample.response,
                    'metrics': sample.metrics,
                    'stats': run.stats
                }
                data_rows.append(row)

        # Convert to DataFrame
        df = pd.json_normalize(data_rows, sep='_')
        return df

    def export(self, format='json', filename=None):
        """
        Export benchmark results to disk.

        Args:
            format (str): File format. One of ``'json'``, ``'csv'``, or ``'excel'``.
            filename (str | None): Optional base filename. Defaults to ``'benchmark_<id>'``.

        Returns:
            bool: True if export succeeded.
        """
        if not filename:
            filename = f"benchmark_{self.bid}"

        if format.lower() == 'json':
            # Convert metadata to serializable format
            serializable_data = {
                bid: run.to_dict()
                for bid, run in self.data.items()
            }
            with open(f"{filename}.json", 'w') as f:
                json.dump(serializable_data, f, indent=2)
        else:
            df = self.data_to_dataframe()
            if format.lower() == 'csv':
                df.to_csv(f"{filename}.csv", index=False)
            elif format.lower() == 'excel':
                df.to_excel(f"{filename}.xlsx", index=False)

        self.logger.info(f"Benchmark metadata exported to {filename}.{format}")
        return True

    def load(self, file_path: str):
        """
        Load benchmark data from a JSON file.

        Args:
            file_path (str): Path to the JSON file.

        Returns:
            bool: True if loaded successfully.

        Notes:
            Overwrites current in-memory data and sets ``self.bid`` to the first run found.
        """
        with open(file_path, 'r') as f:
            raw_data = json.load(f)

        # Convert raw metadata into BenchmarkRun objects
        self.data = {}
        for bid, run_data in raw_data.items():
            run = BenchmarkRun()

            # Load timing metadata
            run.timing.update(run_data['timing'])

            # Load stats
            run.stats.update(run_data['stats'])

            # Load samples
            for sample_id, sample_data in run_data['samples'].items():
                sample = Sample()
                sample.request.update(sample_data['request'])
                sample.response.update(sample_data['response'])
                sample.metrics.update(sample_data['metrics'])
                run.samples[sample_id] = sample

            self.data[bid] = run

        self.bid = next(iter(self.data))
        return True
