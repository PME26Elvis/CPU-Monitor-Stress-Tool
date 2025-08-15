# stress_test.py
import multiprocessing
import time
import math
import os

try:
    import psutil  # 用於可選的 CPU affinity
except Exception:
    psutil = None


def _pin_to_core(core_id: int):
    """可選：把本行程綁到指定邏輯核心（Linux）。"""
    if psutil is None:
        return
    try:
        p = psutil.Process(os.getpid())
        # 安全檢查：避免 core_id 超出範圍
        cores = psutil.cpu_count(logical=True) or 1
        core = max(0, min(core_id, cores - 1))
        p.cpu_affinity([core])
    except Exception:
        pass


def cpu_stress_worker(shared_load_ratio, core_id: int = -1, pin_affinity: bool = True):
    """
    以 50ms 週期（busy + sleep）產生可調強度的 CPU 負載。
    讀 shared_load_ratio.value（0.0~1.0）來動態調整。

    Args:
        shared_load_ratio (multiprocessing.Value): 主行程共享的 double。
        core_id (int): 可選，指定要綁定的邏輯核心 ID。
        pin_affinity (bool): 是否綁定 CPU affinity（Linux）。
    """
    if pin_affinity and core_id >= 0:
        _pin_to_core(core_id)

    # 50 毫秒為一個控制週期（可視需要調整）
    PERIOD = 0.05

    # 用 perf_counter 做高解析度、單調時間
    x = 1.000001
    while True:
        # 讀取目前目標負載（並夾到 0~1）
        ratio = shared_load_ratio.value
        if ratio < 0.0:
            ratio = 0.0
        elif ratio > 1.0:
            ratio = 1.0

        work_time = PERIOD * ratio
        sleep_time = PERIOD - work_time

        start = time.perf_counter()

        # Busy-wait：做一點點「不會被 Python 最佳化掉」的連續運算
        # 讓核心維持忙碌直到 work_time 結束
        if work_time > 0:
            while (time.perf_counter() - start) < work_time:
                # 這段運算成本小、但可持續佔用 CPU
                x = x * 1.000001 + 1.0
                if x > 1e6:
                    x = math.fmod(x, 1.0)

        # 休息到本週期結束
        if sleep_time > 0:
            # 精準睡到 period 結束點，避免累積誤差
            remain = PERIOD - (time.perf_counter() - start)
            if remain > 0:
                time.sleep(remain)
