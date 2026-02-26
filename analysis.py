# -*- coding: utf-8 -*-
"""
FPS反応速度実験 - 統計分析スクリプト
EMS刺激トレーニング前後での反応速度変化を検証する

実験デザイン:
  1. EMS応答速度測定 (×10)
  2. ベースライン測定 (EMS OFF, ×30, StimulusOffset=0)
  3. フェーズ1トレーニング (EMS ON, ×30)
  4. フェーズ1後測定 (EMS OFF, ×30)
  5. フェーズ2トレーニング (EMS ON, ×30)
  6. フェーズ2後測定 (EMS OFF, ×30)
"""

import os
import re
import warnings
import numpy as np
import pandas as pd
from scipy import stats
import matplotlib.pyplot as plt
import matplotlib

# 日本語フォント設定（Windows）
matplotlib.rcParams['font.family'] = 'MS Gothic'
matplotlib.rcParams['axes.unicode_minus'] = False
warnings.filterwarnings('ignore', category=UserWarning)

# ============================================================
# データ読み込み
# ============================================================
DATA_DIR = os.path.join(os.path.dirname(__file__), "ExperimentData")


def parse_csv(filepath):
    """カスタムCSV形式をパースし、設定辞書とトライアルDataFrameを返す"""
    settings = {}
    trials = []
    in_settings = False
    in_trials = False

    with open(filepath, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line.startswith('--- Settings ---'):
                in_settings = True
                in_trials = False
                continue
            if line.startswith('--- Summary ---'):
                break
            if line.startswith('Trial,Direction,'):
                in_trials = True
                in_settings = False
                continue
            if in_settings and ',' in line:
                key, val = line.split(',', 1)
                settings[key.strip()] = val.strip()
            if in_trials and line:
                parts = line.split(',')
                if len(parts) >= 3:
                    trials.append({
                        'Trial': int(parts[0]),
                        'Direction': parts[1],
                        'ReactionTime_ms': float(parts[2]),
                    })

    df = pd.DataFrame(trials)
    return settings, df


def load_all_data():
    """全被験者のデータを構造化して読み込む"""
    files = sorted(os.listdir(DATA_DIR))

    # 被験者ごとにグループ化
    subjects = {}
    for f in files:
        if not f.endswith('.csv'):
            continue
        match = re.match(r'Data_(\w+)_(EMS_\w+)_(\d{8}_\d{6})\.csv', f)
        if not match:
            continue
        name, ems_status, timestamp = match.groups()
        if name not in subjects:
            subjects[name] = []
        settings, df = parse_csv(os.path.join(DATA_DIR, f))
        subjects[name].append({
            'filename': f,
            'ems_status': ems_status,
            'timestamp': timestamp,
            'settings': settings,
            'data': df,
        })

    # 時系列順にソート
    for name in subjects:
        subjects[name].sort(key=lambda x: x['timestamp'])

    return subjects


def classify_phases(subject_files):
    """
    各被験者のファイルをフェーズに分類する
    順序: 応答速度(×10) → ベースライン(OFF,Offset=0) → Train1(ON) → Meas1(OFF) → Train2(ON) → Meas2(OFF)
    """
    phases = {}
    off_files = [f for f in subject_files if f['ems_status'] == 'EMS_OFF']
    on_files = [f for f in subject_files if f['ems_status'] == 'EMS_ON']

    # EMS ON: 最初のものが応答速度測定(×10), 残りがトレーニング
    if len(on_files) >= 1:
        phases['ems_response'] = on_files[0]
    if len(on_files) >= 2:
        phases['train_phase1'] = on_files[1]
    if len(on_files) >= 3:
        phases['train_phase2'] = on_files[2]

    # EMS OFF: 最初がベースライン(Offset=0), 残りが測定
    if len(off_files) >= 1:
        phases['baseline'] = off_files[0]
    if len(off_files) >= 2:
        phases['measure_phase1'] = off_files[1]
    if len(off_files) >= 3:
        phases['measure_phase2'] = off_files[2]

    return phases


# ============================================================
# 外れ値除去
# ============================================================
def remove_outliers(series, label=""):
    """IQR法 + 生理的制約による外れ値除去"""
    original_n = len(series)

    # 生理的制約: 100ms未満（予測的反応）、1000ms超（注意散漫）を除外
    mask_physio = (series >= 100) & (series <= 1000)
    cleaned = series[mask_physio]

    # IQR法
    q1 = cleaned.quantile(0.25)
    q3 = cleaned.quantile(0.75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    mask_iqr = (cleaned >= lower) & (cleaned <= upper)
    cleaned = cleaned[mask_iqr]

    removed = original_n - len(cleaned)
    if removed > 0 and label:
        print(f"    [{label}] 外れ値除去: {original_n} → {len(cleaned)} ({removed}件除外)")

    return cleaned


# ============================================================
# 被験者ごとの分析
# ============================================================
def analyze_subject(name, phases):
    """被験者ごとの記述統計と検定"""
    print(f"\n{'='*60}")
    print(f"  被験者: {name}")
    print(f"{'='*60}")

    bl_raw = phases['baseline']['data']['ReactionTime_ms']
    p1_raw = phases['measure_phase1']['data']['ReactionTime_ms']
    p2_raw = phases['measure_phase2']['data']['ReactionTime_ms']

    bl = remove_outliers(bl_raw, f"{name} ベースライン")
    p1 = remove_outliers(p1_raw, f"{name} フェーズ1後")
    p2 = remove_outliers(p2_raw, f"{name} フェーズ2後")

    # 記述統計
    print(f"\n  [記述統計]")
    print(f"  {'フェーズ':<16} {'平均(ms)':>10} {'SD':>10} {'中央値':>10} {'n':>5}")
    print(f"  {'-'*55}")
    for label, data in [("ベースライン", bl), ("フェーズ1後", p1), ("フェーズ2後", p2)]:
        print(f"  {label:<14} {data.mean():>10.2f} {data.std():>10.2f} {data.median():>10.2f} {len(data):>5}")

    # 変化量
    change_p1 = bl.mean() - p1.mean()
    change_p2 = bl.mean() - p2.mean()
    print(f"\n  [変化量（ベースラインからの短縮）]")
    print(f"  ベースライン → フェーズ1後: {change_p1:+.2f} ms")
    print(f"  ベースライン → フェーズ2後: {change_p2:+.2f} ms")

    # Mann-Whitney U検定（1試行ごとの独立サンプル比較）
    # 帰無仮説: ベースラインと測定後の反応速度に差がない
    # 対立仮説: 測定後の方が反応速度が速い（片側検定）
    print(f"\n  [Mann-Whitney U検定（片側: ベースライン > 測定後）]")

    u1, p_val1 = stats.mannwhitneyu(bl, p1, alternative='greater')
    d1 = (bl.mean() - p1.mean()) / np.sqrt((bl.std()**2 + p1.std()**2) / 2)
    print(f"  BL vs フェーズ1後: U={u1:.1f}, p={p_val1:.4f}, Cohen's d={d1:.3f}")

    u2, p_val2 = stats.mannwhitneyu(bl, p2, alternative='greater')
    d2 = (bl.mean() - p2.mean()) / np.sqrt((bl.std()**2 + p2.std()**2) / 2)
    print(f"  BL vs フェーズ2後: U={u2:.1f}, p={p_val2:.4f}, Cohen's d={d2:.3f}")

    # フェーズ1後 vs フェーズ2後
    u3, p_val3 = stats.mannwhitneyu(p1, p2, alternative='greater')
    d3 = (p1.mean() - p2.mean()) / np.sqrt((p1.std()**2 + p2.std()**2) / 2)
    print(f"  フェーズ1後 vs フェーズ2後: U={u3:.1f}, p={p_val3:.4f}, Cohen's d={d3:.3f}")

    return {
        'subject': name,
        'bl_mean': bl.mean(), 'bl_sd': bl.std(), 'bl_median': bl.median(), 'bl_n': len(bl),
        'p1_mean': p1.mean(), 'p1_sd': p1.std(), 'p1_median': p1.median(), 'p1_n': len(p1),
        'p2_mean': p2.mean(), 'p2_sd': p2.std(), 'p2_median': p2.median(), 'p2_n': len(p2),
        'change_p1': change_p1,
        'change_p2': change_p2,
        'd_p1': d1, 'p_p1': p_val1,
        'd_p2': d2, 'p_p2': p_val2,
        'bl_data': bl.values,
        'p1_data': p1.values,
        'p2_data': p2.values,
    }


# ============================================================
# グループ分析
# ============================================================
def group_analysis(results_list):
    """グループレベルの分析（n=3）"""
    df = pd.DataFrame(results_list)

    print(f"\n{'='*60}")
    print(f"  グループ分析 (n={len(df)})")
    print(f"{'='*60}")

    # 記述統計
    print(f"\n  [グループ平均]")
    print(f"  ベースライン平均: {df['bl_mean'].mean():.2f} ± {df['bl_mean'].std():.2f} ms")
    print(f"  フェーズ1後平均:  {df['p1_mean'].mean():.2f} ± {df['p1_mean'].std():.2f} ms")
    print(f"  フェーズ2後平均:  {df['p2_mean'].mean():.2f} ± {df['p2_mean'].std():.2f} ms")

    print(f"\n  [グループ変化量]")
    print(f"  BL→フェーズ1後: {df['change_p1'].mean():+.2f} ± {df['change_p1'].std():.2f} ms")
    print(f"  BL→フェーズ2後: {df['change_p2'].mean():+.2f} ± {df['change_p2'].std():.2f} ms")

    print(f"\n  [グループ効果量 (Cohen's d)]")
    print(f"  BL vs フェーズ1後: d={df['d_p1'].mean():.3f}")
    print(f"  BL vs フェーズ2後: d={df['d_p2'].mean():.3f}")

    # 対応ありt検定（参考値）
    print(f"\n  [対応ありt検定（参考 - n={len(df)}では検出力不足）]")
    if len(df) >= 2:
        t1, pt1 = stats.ttest_rel(df['bl_mean'], df['p1_mean'])
        t2, pt2 = stats.ttest_rel(df['bl_mean'], df['p2_mean'])
        print(f"  BL vs フェーズ1後: t={t1:.3f}, p={pt1:.4f}")
        print(f"  BL vs フェーズ2後: t={t2:.3f}, p={pt2:.4f}")

    # ウィルコクソン符号順位検定（参考値）
    print(f"\n  [ウィルコクソン符号順位検定（参考 - n={len(df)}では最小p≈0.25）]")
    try:
        w1, pw1 = stats.wilcoxon(df['change_p1'], alternative='greater')
        print(f"  BL vs フェーズ1後: W={w1}, p={pw1:.4f}")
    except Exception as e:
        print(f"  BL vs フェーズ1後: 実行不可 ({e})")
    try:
        w2, pw2 = stats.wilcoxon(df['change_p2'], alternative='greater')
        print(f"  BL vs フェーズ2後: W={w2}, p={pw2:.4f}")
    except Exception as e:
        print(f"  BL vs フェーズ2後: 実行不可 ({e})")

    # 全試行を統合した混合効果的な分析（被験者をブロック因子として）
    print(f"\n  [全試行統合分析（被験者をブロック因子としたKruskal-Wallis検定）]")
    all_bl = np.concatenate([r['bl_data'] for r in results_list])
    all_p1 = np.concatenate([r['p1_data'] for r in results_list])
    all_p2 = np.concatenate([r['p2_data'] for r in results_list])

    h_stat, h_p = stats.kruskal(all_bl, all_p1, all_p2)
    print(f"  Kruskal-Wallis H={h_stat:.3f}, p={h_p:.4f}")

    if h_p < 0.05:
        print(f"  → 有意差あり。事後検定（Mann-Whitney + Bonferroni補正）:")
        pairs = [("BL vs P1後", all_bl, all_p1),
                 ("BL vs P2後", all_bl, all_p2),
                 ("P1後 vs P2後", all_p1, all_p2)]
        for label, g1, g2 in pairs:
            u, p_val = stats.mannwhitneyu(g1, g2, alternative='two-sided')
            p_corrected = min(p_val * 3, 1.0)  # Bonferroni
            d = (g1.mean() - g2.mean()) / np.sqrt((g1.std()**2 + g2.std()**2) / 2)
            print(f"    {label}: U={u:.1f}, p(corrected)={p_corrected:.4f}, d={d:.3f}")
    else:
        # 片側検定も参考表示
        print(f"  → 有意差なし (p={h_p:.4f})")
        print(f"  [参考: 全試行統合 Mann-Whitney U（片側）]")
        u1, pu1 = stats.mannwhitneyu(all_bl, all_p1, alternative='greater')
        d1 = (all_bl.mean() - all_p1.mean()) / np.sqrt((all_bl.std()**2 + all_p1.std()**2) / 2)
        print(f"    BL vs P1後: U={u1:.1f}, p={pu1:.4f}, d={d1:.3f}")

        u2, pu2 = stats.mannwhitneyu(all_bl, all_p2, alternative='greater')
        d2 = (all_bl.mean() - all_p2.mean()) / np.sqrt((all_bl.std()**2 + all_p2.std()**2) / 2)
        print(f"    BL vs P2後: U={u2:.1f}, p={pu2:.4f}, d={d2:.3f}")

    return df


# ============================================================
# 可視化
# ============================================================
def _anon_label(index):
    """被験者の匿名ラベルを返す"""
    return f'被験者{index + 1}'


def plot_results(results_list, output_dir="."):
    """分析結果の可視化"""
    df = pd.DataFrame(results_list)
    subjects = [_anon_label(i) for i in range(len(df))]

    fig, axes = plt.subplots(1, 3, figsize=(18, 6))
    fig.suptitle('FPS反応速度実験 - EMS刺激トレーニング効果の検証', fontsize=14, fontweight='bold')

    # --- (1) 被験者ごとの平均反応速度推移 ---
    ax = axes[0]
    phases = ['ベースライン', 'フェーズ1後', 'フェーズ2後']
    colors = ['#e74c3c', '#3498db', '#2ecc71']
    markers = ['o', 's', '^']
    for i, row in df.iterrows():
        vals = [row['bl_mean'], row['p1_mean'], row['p2_mean']]
        ax.plot(phases, vals, marker=markers[i], markersize=10,
                linewidth=2, label=_anon_label(i), color=colors[i])
    ax.set_ylabel('平均反応速度 (ms)')
    ax.set_title('(a) 被験者別 平均反応速度の推移')
    ax.legend()
    ax.grid(True, alpha=0.3)

    # --- (2) グループ平均の変化量（エラーバー付き） ---
    ax = axes[1]
    change_means = [0, df['change_p1'].mean(), df['change_p2'].mean()]
    change_sds = [0, df['change_p1'].std(), df['change_p2'].std()]
    bar_colors = ['#95a5a6', '#3498db', '#2ecc71']
    bars = ax.bar(phases, change_means, yerr=change_sds, capsize=8,
                  color=bar_colors, alpha=0.8, edgecolor='black', linewidth=0.5)
    ax.set_ylabel('ベースラインからの短縮量 (ms)')
    ax.set_title('(b) グループ平均 反応速度短縮量')
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
    ax.grid(True, alpha=0.3, axis='y')
    # 値を表示
    for bar, mean_val in zip(bars, change_means):
        if mean_val != 0:
            ax.text(bar.get_x() + bar.get_width() / 2., bar.get_height() + 1,
                    f'{mean_val:+.1f}ms', ha='center', va='bottom', fontweight='bold')

    # --- (3) 被験者ごとの個別変化量 ---
    ax = axes[2]
    x = np.arange(len(subjects))
    width = 0.35
    bars1 = ax.bar(x - width/2, df['change_p1'], width, label='フェーズ1後',
                   color='#3498db', alpha=0.8, edgecolor='black', linewidth=0.5)
    bars2 = ax.bar(x + width/2, df['change_p2'], width, label='フェーズ2後',
                   color='#2ecc71', alpha=0.8, edgecolor='black', linewidth=0.5)
    ax.set_xticks(x)
    ax.set_xticklabels(subjects)
    ax.set_ylabel('ベースラインからの短縮量 (ms)')
    ax.set_title('(c) 被験者別 反応速度短縮量')
    ax.legend()
    ax.axhline(y=0, color='black', linestyle='-', linewidth=0.8)
    ax.grid(True, alpha=0.3, axis='y')
    # 先行研究の参考線
    ax.axhline(y=8, color='red', linestyle='--', linewidth=1, alpha=0.6, label='先行研究 (8ms)')
    ax.legend()

    plt.tight_layout()
    output_path = os.path.join(output_dir, 'reaction_time_analysis.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"\nグラフを保存: {output_path}")
    plt.close()


def plot_individual_trials(results_list, output_dir="."):
    """被験者ごとの全トライアル散布図"""
    fig, axes = plt.subplots(1, len(results_list), figsize=(6 * len(results_list), 5))
    if len(results_list) == 1:
        axes = [axes]

    for i, r in enumerate(results_list):
        ax = axes[i]
        for j, (data, label, color) in enumerate([
            (r['bl_data'], 'ベースライン', '#e74c3c'),
            (r['p1_data'], 'フェーズ1後', '#3498db'),
            (r['p2_data'], 'フェーズ2後', '#2ecc71'),
        ]):
            x = np.arange(len(data)) + 1
            ax.scatter(x, data, label=label, color=color, alpha=0.7, s=40)
            ax.axhline(y=np.mean(data), color=color, linestyle='--', alpha=0.5)

        ax.set_xlabel('トライアル番号')
        ax.set_ylabel('反応速度 (ms)')
        ax.set_title(f'{_anon_label(i)}')
        ax.legend(fontsize=8)
        ax.grid(True, alpha=0.3)

    fig.suptitle('被験者別 全トライアルの反応速度', fontsize=13, fontweight='bold')
    plt.tight_layout()
    output_path = os.path.join(output_dir, 'individual_trials.png')
    plt.savefig(output_path, dpi=150, bbox_inches='tight')
    print(f"グラフを保存: {output_path}")
    plt.close()


# ============================================================
# サマリーテーブル出力
# ============================================================
def export_summary(results_list, output_dir="."):
    """結果をCSVで出力"""
    rows = []
    for r in results_list:
        rows.append({
            '被験者': r['subject'],
            'BL_平均(ms)': round(r['bl_mean'], 2),
            'BL_SD': round(r['bl_sd'], 2),
            'BL_n': r['bl_n'],
            'P1後_平均(ms)': round(r['p1_mean'], 2),
            'P1後_SD': round(r['p1_sd'], 2),
            'P1後_n': r['p1_n'],
            'P2後_平均(ms)': round(r['p2_mean'], 2),
            'P2後_SD': round(r['p2_sd'], 2),
            'P2後_n': r['p2_n'],
            '変化量_P1(ms)': round(r['change_p1'], 2),
            '変化量_P2(ms)': round(r['change_p2'], 2),
            '効果量d_P1': round(r['d_p1'], 3),
            '効果量d_P2': round(r['d_p2'], 3),
            'p値_BLvsP1': round(r['p_p1'], 4),
            'p値_BLvsP2': round(r['p_p2'], 4),
        })
    df_out = pd.DataFrame(rows)
    output_path = os.path.join(output_dir, 'analysis_summary.csv')
    df_out.to_csv(output_path, index=False, encoding='utf-8-sig')
    print(f"サマリーCSVを保存: {output_path}")
    return df_out


# ============================================================
# メイン
# ============================================================
def main():
    print("=" * 60)
    print("  FPS反応速度実験 - EMS刺激トレーニング効果の統計分析")
    print("=" * 60)

    subjects = load_all_data()
    print(f"\n被験者数: {len(subjects)}")
    for name, files in subjects.items():
        print(f"  {name}: {len(files)} ファイル")

    results_list = []
    for name, files in subjects.items():
        phases = classify_phases(files)
        result = analyze_subject(name, phases)
        results_list.append(result)

    df_group = group_analysis(results_list)

    # 可視化
    script_dir = os.path.dirname(os.path.abspath(__file__))
    plot_results(results_list, output_dir=script_dir)
    plot_individual_trials(results_list, output_dir=script_dir)

    # CSV出力
    df_summary = export_summary(results_list, output_dir=script_dir)
    print(f"\n{'='*60}")
    print("  分析完了")
    print(f"{'='*60}")
    print("\n[結果サマリー]")
    print(df_summary.to_string(index=False))

    # 考察
    print(f"\n[考察]")
    mean_change_p2 = df_group['change_p2'].mean()
    if mean_change_p2 > 0:
        print(f"  グループ平均で {mean_change_p2:.1f}ms の反応速度短縮が観察されました。")
        print(f"  先行研究の8ms短縮と比較して、方向性は{'一致' if mean_change_p2 > 0 else '不一致'}しています。")
    else:
        print(f"  グループ平均で反応速度の短縮は観察されませんでした（{mean_change_p2:+.1f}ms）。")
    print(f"  ※ n={len(df_group)}のため統計的有意性の主張は困難です。効果量を重視した解釈を推奨します。")


if __name__ == '__main__':
    main()
