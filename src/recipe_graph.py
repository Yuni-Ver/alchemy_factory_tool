"""計算で採用された生産工程を Graphviz の関連図にする。"""

import json
import os
import shutil
import subprocess
from pathlib import Path
from number_display import format_display
from collections import defaultdict
from decimal import Decimal


def quote(value):
    return json.dumps(str(value), ensure_ascii=False)


def graphviz_executable():
    executable = shutil.which("dot")
    if executable:
        return executable
    for root in (os.environ.get("ProgramFiles"), os.environ.get("ProgramFiles(x86)"),
                 os.environ.get("LOCALAPPDATA")):
        if root:
            candidate = Path(root) / "Graphviz" / "bin" / "dot.exe"
            if candidate.is_file():
                return str(candidate)
    raise FileNotFoundError("Graphviz が見つかりません。Graphviz をインストールしてください。")


def render_recipe_graph(dot_source):
    """既存の関連図を日本語対応のPNGに変換する。"""
    result = subprocess.run(
        [graphviz_executable(), "-Tpng", "-Gdpi=144", "-Gbgcolor=white",
         "-Nfontname=Meiryo", "-Efontname=Meiryo"],
        input=dot_source.encode("utf-8"), capture_output=True, timeout=30,
        check=True,
        creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
    )
    return result.stdout


def machine_utilization(machine, recipe):
    """設置設備全体に対する理論上の平均稼働率（%）。"""
    capacity_per_minute = (
        Decimal('60') / recipe['craft_time']
        * recipe['output_quantity'] * recipe['probability']
        * machine['machine_count']
    )
    if capacity_per_minute <= 0:
        return Decimal('0')
    return machine['target_rate'] / capacity_per_minute * Decimal('100')

def build_recipe_graph(machines, materials, recipes_by_item, item_names, target_item):
    lines = [
        'digraph production {',
        'graph [rankdir=LR, bgcolor="transparent", nodesep=0.4, ranksep=0.8];',
        'node [fontname="sans-serif", style="filled", color="#94a3b8"];',
        'edge [fontname="sans-serif", color="#64748b"];',
    ]
    rates = dict(materials)
    rates.update({m['item_id']: m['target_rate'] for m in machines})
    for item_id, rate in sorted(rates.items()):
        name = item_names.get(item_id) or item_id
        source = item_id in materials
        label = f"{name}\n{format_display(rate, grouped=True)} 個/分"
        if source:
            label += "\n外部調達"
        if item_id == target_item:
            label += "\n生産目標"
        color = '#bbf7d0' if item_id == target_item else '#fef3c7' if source else '#dbeafe'
        lines.append(f'{quote("item:" + item_id)} [shape=ellipse, fillcolor={quote(color)}, label={quote(label)}];')

    for machine in sorted(machines, key=lambda m: m['recipe_id']):
        item_id = machine['item_id']
        recipe = recipes_by_item[item_id]
        process_id = quote('process:' + item_id)
        device = machine['device_name'] or '設備未設定'
        label = f"{device} × {machine['machine_count']}台\n加工時間 {format_display(recipe['craft_time'])} 秒/回\n稼働率 {format_display(machine_utilization(machine, recipe))}%"
        label = f"{recipe['recipe_name']}\n{label}"
        lines.append(f'{process_id} [shape=box, fillcolor="#ede9fe", label={quote(label)}];')
        cycles = machine['target_rate'] / (recipe['output_quantity'] * recipe['probability'])
        inputs = defaultdict(lambda: Decimal('0'))
        for ingredient, quantity in recipe['inputs']:
            inputs[ingredient] += quantity * cycles
        # 同一素材を2枠へ入れるアセンブラーは、合計需要を等分して表示する。
        split_input = recipe['device_id'] == 'assembler' and len(inputs) == 1
        for ingredient, rate in sorted(inputs.items()):
            if split_input:
                for slot, port in ((1, 'nw'), (2, 'sw')):
                    input_label = f"入力{slot} {format_display(rate / 2, grouped=True)} 個/分"
                    lines.append(f'{quote("item:" + ingredient)} -> {process_id}:{port} [label={quote(input_label)}];')
            else:
                lines.append(f'{quote("item:" + ingredient)} -> {process_id} [label={quote(f"入力 {format_display(rate, grouped=True)} 個/分")}];')
        output_label = f"出力 {format_display(machine['target_rate'], grouped=True)} 個/分"
        if recipe['probability'] != Decimal('1'):
            output_label += f"\n期待値（確率 {format_display(recipe['probability'] * 100)}%）"
        lines.append(f'{process_id} -> {quote("item:" + item_id)} [label={quote(output_label)}];')
    lines.append('}')
    return '\n'.join(lines)
