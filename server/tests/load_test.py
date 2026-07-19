"""
负载测试脚本
模拟多客户端并发上报
"""

import asyncio
import aiohttp
import time
import statistics
from typing import List


async def make_request(session, url, data=None):
    """发送单个请求"""
    start = time.time()
    try:
        if data:
            async with session.post(url, json=data) as response:
                await response.read()
                return time.time() - start
        else:
            async with session.get(url) as response:
                await response.read()
                return time.time() - start
    except Exception as e:
        print(f"Request failed: {e}")
        return None


async def load_test(url, num_requests, concurrency, data=None):
    """负载测试"""
    connector = aiohttp.TCPConnector(limit=concurrency)
    async with aiohttp.ClientSession(connector=connector) as session:
        tasks = [make_request(session, url, data) for _ in range(num_requests)]
        results = await asyncio.gather(*tasks)
        return [r for r in results if r is not None]


def run_load_test():
    """运行负载测试"""
    url = "http://localhost:5000/api/dashboard"

    print(f"Testing {url}")
    print(f"Concurrent users: 100")
    print(f"Total requests: 1000")

    start_time = time.time()
    results = asyncio.run(load_test(url, 1000, 100))
    total_time = time.time() - start_time

    if results:
        print(f"\nResults:")
        print(f"  Total time: {total_time:.2f}s")
        print(f"  Requests per second: {len(results)/total_time:.2f}")
        print(f"  Average response time: {statistics.mean(results)*1000:.2f}ms")
        print(f"  Median response time: {statistics.median(results)*1000:.2f}ms")
        print(f"  95th percentile: {sorted(results)[int(len(results)*0.95)]*1000:.2f}ms")
        print(f"  99th percentile: {sorted(results)[int(len(results)*0.99)]*1000:.2f}ms")


if __name__ == '__main__':
    run_load_test()
