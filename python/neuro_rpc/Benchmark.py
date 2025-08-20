import time
import uuid
import pandas as pd
import numpy as np
import json

from python.neuro_rpc.RPCTracker import RPCTracker

class Sample:
    """Represents a single request-response sample"""
    def __init__(self):
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
        """Convert Sample to dictionary for JSON serialization"""
        return {
            'request': self.request,
            'response': self.response,
            'metrics': self.metrics
        }

class BenchmarkRun:
    """Represents a single benchmark run with its samples and statistics"""
    def __init__(self):
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
        """Convert BenchmarkRun to dictionary for JSON serialization"""
        return {
            'timing': self.timing,
            'samples': {k: v.to_dict() for k, v in self.samples.items()},
            'stats': self.stats
        }

class Benchmark(RPCTracker):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.bid = None
        self.benchmark_active = False
        self.data = {}
        self._current_run = None

    def check_bid(self, benchmark_id=None):
        bid = benchmark_id or self.bid
        if bid not in self.data:
            raise ValueError(f"No benchmark metadata found for ID: {bid}")
        return bid

    def start_benchmark(self, bid=None):
        """Start collecting benchmark metadata"""
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
        result = super().track_incoming_response(response)

        if self.benchmark_active and response.id is not None and response.id in self._current_run.samples:
            sample = self._current_run.samples[response.id]
            sample.response['timestamp'] = time.perf_counter() * 1000
            sample.response['payload_size'] = len(response.to_json())
            if raw:
                sample.response['raw'] = response.to_dict()

            sample.metrics['exec_time'] = response.exec_time / 1000  # Convert to ms
            # Calculate latencies
            sample.metrics['total_latency'] = sample.response['timestamp'] - sample.request['timestamp']
            sample.metrics['network_latency'] = abs(
                sample.metrics['total_latency'] - sample.metrics['exec_time']
            )

        return result

    def set_exec_time(self, response_id, exec_time):
        if self.benchmark_active and response_id in self._current_run.samples:
            sample = self._current_run.samples[response_id]
            sample.metrics['exec_time'] = exec_time / 1000
            sample.metrics['network_latency'] = abs(
                sample.metrics['total_latency'] - sample.metrics['exec_time']
            )

    def stop_benchmark(self, benchmark_id=None):
        """Stop collecting benchmark metadata"""
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
        """Convert all benchmarks metadata into a single DataFrame"""
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
        """Export benchmark results"""
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
        """Load benchmark metadata from file"""
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
