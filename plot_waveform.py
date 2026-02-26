# -*- coding: utf-8 -*-
"""
EMS刺激の電圧波形を可視化するスクリプト

波形パラメータ（実験設定値）:
  - PulseWidth: 50μs（各相の幅）
  - BurstCount: 3（2相性サイクルの連続回数）
  - PulseCount: 1（バースト繰り返し回数）
  - PulseInterval: 40,000μs = 40ms

1サイクル構成（2相性パルス, biphasic）:
  [正相 +V] → [休止 0V] → [逆相 -V] → [休止 0V]
   50μs       50μs        50μs        50μs  = 200μs/サイクル

1回の刺激 = 3サイクル連続 = 600μs
"""

import numpy as np
import matplotlib.pyplot as plt
import matplotlib
import os

matplotlib.rcParams['font.family'] = 'MS Gothic'
matplotlib.rcParams['axes.unicode_minus'] = False

# ============================================================
# パラメータ
# ============================================================
PULSE_WIDTH_US = 50       # 各相のパルス幅 (μs)
BURST_COUNT = 3           # 2相性サイクル数
PULSE_COUNT = 1           # 繰り返し回数
PULSE_INTERVAL_US = 40000 # インターバル (μs)

# 時間分解能
DT = 1  # 1μs刻み

# ============================================================
# 波形生成
# ============================================================
def generate_biphasic_waveform():
    """2相性パルス波形を生成"""
    waveform = []
    time = []
    t = 0

    for rep in range(PULSE_COUNT):
        for burst in range(BURST_COUNT):
            # 1. 正相 (+1)
            for _ in range(PULSE_WIDTH_US):
                time.append(t)
                waveform.append(1.0)
                t += DT

            # 2. 休止 (0)
            for _ in range(PULSE_WIDTH_US):
                time.append(t)
                waveform.append(0.0)
                t += DT

            # 3. 逆相 (-1)
            for _ in range(PULSE_WIDTH_US):
                time.append(t)
                waveform.append(-1.0)
                t += DT

            # 4. 休止 (0)
            for _ in range(PULSE_WIDTH_US):
                time.append(t)
                waveform.append(0.0)
                t += DT

        # インターバル（最後の繰り返し以外）
        if rep < PULSE_COUNT - 1:
            for _ in range(PULSE_INTERVAL_US):
                time.append(t)
                waveform.append(0.0)
                t += DT

    return np.array(time), np.array(waveform)


def plot_waveform():
    """波形を2段構成（全体 + 拡大）で描画"""
    time_us, waveform = generate_biphasic_waveform()

    fig, axes = plt.subplots(2, 1, figsize=(14, 8), gridspec_kw={'height_ratios': [1, 1]})
    fig.suptitle('EMS刺激 電圧波形（2相性パルス, Biphasic）', fontsize=14, fontweight='bold')

    # ========== (a) 全体波形 ==========
    ax = axes[0]
    ax.plot(time_us, waveform, color='#2c3e50', linewidth=1.5)
    ax.fill_between(time_us, waveform, 0, where=(waveform > 0),
                    color='#e74c3c', alpha=0.3, label='正相 (+)')
    ax.fill_between(time_us, waveform, 0, where=(waveform < 0),
                    color='#3498db', alpha=0.3, label='逆相 (−)')

    ax.set_xlabel('時間 (μs)')
    ax.set_ylabel('電圧（正規化）')
    ax.set_title(f'(a) 1回の刺激全体（{BURST_COUNT}サイクル = {BURST_COUNT * 4 * PULSE_WIDTH_US}μs）')
    ax.set_ylim(-1.5, 1.5)
    ax.set_xlim(-20, time_us[-1] + 50)
    ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)
    ax.legend(loc='upper right')
    ax.grid(True, alpha=0.3)

    # サイクル区切り線
    for i in range(BURST_COUNT + 1):
        x = i * 4 * PULSE_WIDTH_US
        ax.axvline(x=x, color='gray', linestyle=':', linewidth=0.8, alpha=0.5)
        if i < BURST_COUNT:
            ax.text(x + 2 * PULSE_WIDTH_US, 1.3, f'サイクル{i+1}',
                    ha='center', va='center', fontsize=9, color='#7f8c8d')

    # ========== (b) 1サイクル拡大 ==========
    ax = axes[1]
    # 1サイクル分だけ切り出し
    one_cycle_len = 4 * PULSE_WIDTH_US
    mask = time_us < one_cycle_len
    t_cycle = time_us[mask]
    w_cycle = waveform[mask]

    ax.plot(t_cycle, w_cycle, color='#2c3e50', linewidth=2)
    ax.fill_between(t_cycle, w_cycle, 0, where=(w_cycle > 0),
                    color='#e74c3c', alpha=0.3)
    ax.fill_between(t_cycle, w_cycle, 0, where=(w_cycle < 0),
                    color='#3498db', alpha=0.3)

    ax.set_xlabel('時間 (μs)')
    ax.set_ylabel('電圧（正規化）')
    ax.set_title(f'(b) 1サイクル拡大（2相性パルス, 1サイクル = {one_cycle_len}μs）')
    ax.set_ylim(-1.5, 1.5)
    ax.set_xlim(-10, one_cycle_len + 10)
    ax.axhline(y=0, color='gray', linestyle='-', linewidth=0.5)
    ax.grid(True, alpha=0.3)

    # 各フェーズのアノテーション
    phases = [
        (0, PULSE_WIDTH_US, '正相\n(+V)', '#e74c3c'),
        (PULSE_WIDTH_US, 2 * PULSE_WIDTH_US, '休止\n(0V)', '#95a5a6'),
        (2 * PULSE_WIDTH_US, 3 * PULSE_WIDTH_US, '逆相\n(−V)', '#3498db'),
        (3 * PULSE_WIDTH_US, 4 * PULSE_WIDTH_US, '休止\n(0V)', '#95a5a6'),
    ]
    for start, end, label, color in phases:
        mid = (start + end) / 2
        y_pos = 1.3 if '正' in label or '休' in label else -1.3
        if '逆' in label:
            y_pos = -1.3
        ax.annotate('', xy=(start, -1.25), xytext=(end, -1.25) if '逆' not in label else (end, -1.25),
                    arrowprops=dict(arrowstyle='<->', color=color, lw=1.5))
        ax.text(mid, -1.4, f'{PULSE_WIDTH_US}μs', ha='center', va='top', fontsize=9, color=color)
        # ラベルはパルスの上/下に配置
        if '正' in label:
            ax.text(mid, 0.6, label, ha='center', va='center', fontsize=9,
                    fontweight='bold', color=color,
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor=color, alpha=0.8))
        elif '逆' in label:
            ax.text(mid, -0.6, label, ha='center', va='center', fontsize=9,
                    fontweight='bold', color=color,
                    bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor=color, alpha=0.8))
        elif start == PULSE_WIDTH_US:  # 最初の休止
            ax.text(mid, 0.6, label, ha='center', va='center', fontsize=8,
                    color=color,
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor=color, alpha=0.6))
        else:  # 2番目の休止
            ax.text(mid, 0.6, label, ha='center', va='center', fontsize=8,
                    color=color,
                    bbox=dict(boxstyle='round,pad=0.2', facecolor='white', edgecolor=color, alpha=0.6))

    plt.tight_layout()

    output_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'ems_waveform.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"波形図を保存: {output_path}")
    plt.close()


if __name__ == '__main__':
    plot_waveform()
