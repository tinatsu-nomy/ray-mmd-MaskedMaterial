#!/usr/bin/env python3
"""
ray-mmd material_2.0.fx → MaskedMaterial レイヤー変換スクリプト

使い方:
    python convert_material.py <入力.fx> [--layer N] [--shading-model ID]

例:
    python convert_material.py material_skin.fx --layer 1 --shading-model 1
    python convert_material.py material_body.fx --layer 0
    python convert_material.py material_metal.fx -l 2 -s 0

オプション:
    --layer, -l        出力レイヤー番号 (0-7, デフォルト: 0)
    --shading-model, -s  シェーディングモデルID (デフォルト: 自動検出)
                         0=Default, 1=Skin, 2=Emissive, 3=Anisotropy,
                         4=Glass, 5=Cloth, 6=ClearCoat, 7=Subsurface
    --output, -o       出力ファイルパス (デフォルト: 標準出力)
"""

import re
import sys
import math
import argparse
from pathlib import Path


# ============================================================
# パーサー
# ============================================================

def parse_material_fx(text: str) -> dict:
    """material_2.0.fx 形式のテキストを解析し、パラメータ辞書を返す。"""
    params = {}

    # #define マクロ を解析
    for m in re.finditer(
        r'^\s*#define\s+(\w+)\s+(.+?)(?:\s*//.*)?$', text, re.MULTILINE
    ):
        key, val = m.group(1), m.group(2).strip()
        # 文字列リテラル
        if val.startswith('"'):
            params[key] = val
        else:
            params[key] = val

    # const 変数を解析
    for m in re.finditer(
        r'^\s*(?:static\s+)?const\s+(\w+)\s+(\w+)\s*=\s*(.+?)\s*;',
        text, re.MULTILINE
    ):
        ctype, name, val = m.group(1), m.group(2), m.group(3).strip()
        params[f'_const_{name}'] = (ctype, val)

    # SSS_SKIN_TRANSMITTANCE マクロ定義を検出
    m = re.search(
        r'#define\s+SSS_SKIN_TRANSMITTANCE\((\w+)\)\s+(.+?)$',
        text, re.MULTILINE
    )
    if m:
        params['_has_sss_macro'] = True

    # #include パスを検出 (shading model の手がかり)
    m = re.search(r'#include\s+"([^"]+)"', text)
    if m:
        params['_include_path'] = m.group(1)

    return params


# ============================================================
# SSS_SKIN_TRANSMITTANCE 事前計算
# ============================================================

def eval_sss_transmittance(expr: str) -> str:
    """SSS_SKIN_TRANSMITTANCE(x) を事前計算して float3(...) 文字列を返す。"""
    m = re.match(r'SSS_SKIN_TRANSMITTANCE\(\s*([\d.]+)\s*\)', expr)
    if not m:
        return None
    x = float(m.group(1))
    t = 1.0 - min(max(x, 0.0), 1.0)  # saturate
    r = math.exp(t * -8.0)
    g = math.exp(t * -40.0)
    b = math.exp(t * -64.0)
    return f'float3({r:.6g}, {g:.6g}, {b:.6g})'


# ============================================================
# 値の正規化
# ============================================================

def normalize_float3(ctype: str, val: str) -> str:
    """const float3 の値を float3(x, y, z) 形式に正規化。"""
    val = val.strip()
    if val.startswith('float3(') or val.startswith('float2('):
        return val
    # SSS マクロ
    sss = eval_sss_transmittance(val)
    if sss:
        return sss
    # スカラー値 → float3(v, v, v)
    try:
        v = float(val)
        return f'float3({v}, {v}, {v})'
    except ValueError:
        return f'float3({val}, {val}, {val})'


def normalize_float(val: str) -> str:
    """const float の値をそのまま返す。"""
    return val.strip()


# ============================================================
# シェーディングモデル自動検出
# ============================================================

SHADING_MODEL_NAMES = {
    0: 'Default', 1: 'Skin', 2: 'Emissive', 3: 'Anisotropy',
    4: 'Glass', 5: 'Cloth', 6: 'ClearCoat', 7: 'Subsurface'
}

def detect_shading_model(params: dict) -> int:
    """ファイル内容からシェーディングモデルを推測する。

    ray-mmd では CUSTOM_ENABLE の値がシェーディングモデルIDに直接対応:
      0=Default, 1=Skin, 3=Anisotropy, 5=Cloth, 7=Subsurface
    EMISSIVE_ENABLE=1 の場合は Emissive (2)。
    """
    custom_enable = int(params.get('CUSTOM_ENABLE', '0'))
    emissive_enable = int(params.get('EMISSIVE_ENABLE', '0'))

    # CUSTOM_ENABLE が既知のシェーディングモデルIDに直接対応
    if custom_enable in (1, 3, 4, 5, 6, 7):
        return custom_enable

    # EMISSIVE_ENABLE=1 で Emissive
    if emissive_enable == 1 and custom_enable == 0:
        return 2

    if custom_enable == 0:
        return 0

    # include パスから推測 (フォールバック)
    inc = params.get('_include_path', '').lower()
    if 'skin' in inc:
        return 1
    if 'cloth' in inc:
        return 5
    if 'glass' in inc:
        return 4
    if 'clearcoat' in inc:
        return 6
    if 'subsurface' in inc:
        return 7
    if 'anisotrop' in inc:
        return 3

    # 判定不能
    return -1


# ============================================================
# 変換
# ============================================================

def get_const(params: dict, name: str, default: str = '0') -> tuple:
    """const 変数を取得。(type, value) を返す。"""
    key = f'_const_{name}'
    if key in params:
        return params[key]
    return ('float', default)


def convert_map_from(val: int) -> int:
    """MAP_FROM の値を MaskedMaterial 互換に変換。
    0=無効, 1=外部ファイル → そのまま
    2-9 (モデルテクスチャ等) → 0 (非対応)
    """
    if val in (0, 1):
        return val
    return 0


def convert(params: dict, layer: int, shading_model: int) -> list:
    """パラメータ辞書を MaskedMaterial L{N} 形式の行リストに変換。"""
    N = layer
    lines = []
    warnings = []

    def out(s):
        lines.append(s)

    def warn(s):
        warnings.append(s)

    # --- Albedo ---
    out(f'// --- Albedo ---')
    albedo_from = int(params.get('ALBEDO_MAP_FROM', '0'))
    albedo_apply_diffuse = int(params.get('ALBEDO_MAP_APPLY_DIFFUSE', '1'))

    ctype, cval = get_const(params, 'albedo', '1.0')
    albedo_str = normalize_float3('float3', cval)

    out(f'#define L{N}_ALBEDO {albedo_str}')

    if albedo_from == 1:
        # 外部ファイル → そのまま
        out(f'#define L{N}_ALBEDO_MAP_FROM 1')
        albedo_file = params.get('ALBEDO_MAP_FILE', '"albedo.png"')
        out(f'#define L{N}_ALBEDO_MAP_FILE {albedo_file}')
        out(f'#define L{N}_ALBEDO_APPLY_DIFFUSE 0')
    elif albedo_from == 3:
        # モデルテクスチャ → APPLY_DIFFUSE で代替
        out(f'#define L{N}_ALBEDO_MAP_FROM 0')
        out(f'#define L{N}_ALBEDO_APPLY_DIFFUSE {albedo_apply_diffuse}')
        if albedo_apply_diffuse == 0:
            warn('ALBEDO_MAP_FROM=3 but APPLY_DIFFUSE=0: モデルテクスチャが使われません')
    elif albedo_from >= 2:
        out(f'#define L{N}_ALBEDO_MAP_FROM 0')
        out(f'#define L{N}_ALBEDO_APPLY_DIFFUSE {albedo_apply_diffuse}')
        warn(f'ALBEDO_MAP_FROM={albedo_from} は MaskedMaterial 非対応 → 0 に変換')
    else:
        out(f'#define L{N}_ALBEDO_MAP_FROM 0')
        out(f'#define L{N}_ALBEDO_APPLY_DIFFUSE {albedo_apply_diffuse}')

    # --- Albedo Sub ---
    albedo_sub_enable = int(params.get('ALBEDO_SUB_ENABLE', '0'))
    albedo_sub_from = int(params.get('ALBEDO_SUB_MAP_FROM', '0'))
    if albedo_sub_enable > 0 and albedo_sub_from == 1:
        out(f'')
        out(f'// --- Albedo Sub ---')
        out(f'#define L{N}_ALBEDO_SUB_ENABLE {albedo_sub_enable}')
        out(f'#define L{N}_ALBEDO_SUB_MAP_FROM 1')
        sub_file = params.get('ALBEDO_SUB_MAP_FILE', '"albedo.png"')
        out(f'#define L{N}_ALBEDO_SUB_MAP_FILE {sub_file}')

    # --- Normal map ---
    normal_from = convert_map_from(int(params.get('NORMAL_MAP_FROM', '0')))
    if normal_from == 1:
        out(f'')
        out(f'// --- Normal map ---')
        out(f'#define L{N}_NORMAL_MAP_FROM 1')
        out(f'#define L{N}_NORMAL_MAP_FILE {params.get("NORMAL_MAP_FILE", chr(34) + "normal.png" + chr(34))}')
        normal_type = params.get('NORMAL_MAP_TYPE', '0')
        if normal_type != '0':
            out(f'#define L{N}_NORMAL_MAP_TYPE {normal_type}')
        _, scale = get_const(params, 'normalMapScale', '1.0')
        if scale != '1.0':
            out(f'#define L{N}_NORMAL_MAP_SCALE {normalize_float(scale)}')
        _, loop = get_const(params, 'normalMapLoopNum', '1.0')
        if loop != '1.0':
            out(f'#define L{N}_NORMAL_MAP_LOOP {normalize_float(loop)}')

    if int(params.get('NORMAL_MAP_FROM', '0')) >= 2:
        warn(f'NORMAL_MAP_FROM={params["NORMAL_MAP_FROM"]} は非対応 → 無効化')

    # --- Normal sub map ---
    normal_sub_from = convert_map_from(int(params.get('NORMAL_SUB_MAP_FROM', '0')))
    if normal_sub_from == 1:
        out(f'')
        out(f'// --- Normal sub map ---')
        out(f'#define L{N}_NORMAL_SUB_MAP_FROM 1')
        out(f'#define L{N}_NORMAL_SUB_MAP_FILE {params.get("NORMAL_SUB_MAP_FILE", chr(34) + "normal.png" + chr(34))}')
        sub_type = params.get('NORMAL_SUB_MAP_TYPE', '0')
        if sub_type != '0':
            out(f'#define L{N}_NORMAL_SUB_MAP_TYPE {sub_type}')
        _, scale = get_const(params, 'normalSubMapScale', '1.0')
        if scale != '1.0':
            out(f'#define L{N}_NORMAL_SUB_MAP_SCALE {normalize_float(scale)}')
        _, loop = get_const(params, 'normalSubMapLoopNum', '1.0')
        if loop != '1.0':
            out(f'#define L{N}_NORMAL_SUB_MAP_LOOP {normalize_float(loop)}')

    # --- Material properties ---
    out(f'')
    out(f'// --- Material properties ---')

    _, smoothness = get_const(params, 'smoothness', '0.0')
    out(f'#define L{N}_SMOOTHNESS {normalize_float(smoothness)}')

    smooth_from = convert_map_from(int(params.get('SMOOTHNESS_MAP_FROM', '0')))
    if smooth_from == 1:
        out(f'#define L{N}_SMOOTHNESS_MAP_FROM 1')
        out(f'#define L{N}_SMOOTHNESS_MAP_FILE {params.get("SMOOTHNESS_MAP_FILE", chr(34) + "smoothness.png" + chr(34))}')
        swizzle = params.get('SMOOTHNESS_MAP_SWIZZLE', '0')
        if swizzle != '0':
            out(f'#define L{N}_SMOOTHNESS_MAP_SWIZZLE {swizzle}')
        stype = params.get('SMOOTHNESS_MAP_TYPE', '0')
        if stype != '0':
            out(f'#define L{N}_SMOOTHNESS_MAP_TYPE {stype}')

    if int(params.get('SMOOTHNESS_MAP_FROM', '0')) >= 2:
        warn(f'SMOOTHNESS_MAP_FROM={params["SMOOTHNESS_MAP_FROM"]} は非対応 → 無効化')

    _, metalness = get_const(params, 'metalness', '0.0')
    out(f'#define L{N}_METALNESS {normalize_float(metalness)}')

    metal_from = convert_map_from(int(params.get('METALNESS_MAP_FROM', '0')))
    if metal_from == 1:
        out(f'#define L{N}_METALNESS_MAP_FROM 1')
        out(f'#define L{N}_METALNESS_MAP_FILE {params.get("METALNESS_MAP_FILE", chr(34) + "metalness.png" + chr(34))}')

    _, spec_val = get_const(params, 'specular', '0.5')
    # specular は MaskedMaterial では float スカラー
    spec_str = normalize_float(spec_val)
    try:
        float(spec_str)
    except ValueError:
        # float3(...) の場合、最初の値を使う
        m = re.match(r'float3\(([\d.]+)', spec_str)
        if m:
            spec_str = m.group(1)
            warn('specular が float3 → 最初の成分をスカラーとして使用')
    out(f'#define L{N}_SPECULAR {spec_str}')

    spec_from = convert_map_from(int(params.get('SPECULAR_MAP_FROM', '0')))
    if spec_from == 1:
        out(f'#define L{N}_SPECULAR_MAP_FROM 1')
        out(f'#define L{N}_SPECULAR_MAP_FILE {params.get("SPECULAR_MAP_FILE", chr(34) + "specular.png" + chr(34))}')

    # --- Occlusion ---
    occ_from = convert_map_from(int(params.get('OCCLUSION_MAP_FROM', '0')))
    if occ_from == 1:
        out(f'')
        out(f'// --- Occlusion ---')
        out(f'#define L{N}_OCCLUSION_MAP_FROM 1')
        out(f'#define L{N}_OCCLUSION_MAP_FILE {params.get("OCCLUSION_MAP_FILE", chr(34) + "occlusion.png" + chr(34))}')

    # --- Shading model ---
    out(f'')
    out(f'// --- Shading ---')
    if shading_model >= 0:
        name = SHADING_MODEL_NAMES.get(shading_model, '?')
        out(f'#define L{N}_SHADING_MODEL {shading_model}  // {name}')
    else:
        out(f'#define L{N}_SHADING_MODEL 0  // TODO: CUSTOM_ENABLE=1 検出、モデルIDを手動指定してください')
        warn('CUSTOM_ENABLE=1 ですがシェーディングモデルを自動検出できません → 手動指定してください')

    # --- Emissive ---
    emissive_enable = int(params.get('EMISSIVE_ENABLE', '0'))
    if emissive_enable:
        _, em_val = get_const(params, 'emissive', '0')
        em_str = normalize_float3('float3', em_val)
        out(f'#define L{N}_EMISSIVE {em_str}')
        _, ei_val = get_const(params, 'emissiveIntensity', '0.0')
        out(f'#define L{N}_EMISSIVE_INTENSITY {normalize_float(ei_val)}')

        em_from = convert_map_from(int(params.get('EMISSIVE_MAP_FROM', '0')))
        if em_from == 1:
            out(f'#define L{N}_EMISSIVE_MAP_FROM 1')
            out(f'#define L{N}_EMISSIVE_MAP_FILE {params.get("EMISSIVE_MAP_FILE", chr(34) + "emissive.png" + chr(34))}')
    else:
        out(f'#define L{N}_EMISSIVE float3(0, 0, 0)')
        out(f'#define L{N}_EMISSIVE_INTENSITY 0.0')

    # --- Custom A/B ---
    custom_enable = int(params.get('CUSTOM_ENABLE', '0'))
    if custom_enable:
        _, ca_val = get_const(params, 'customA', '0.0')
        out(f'#define L{N}_CUSTOM_A {normalize_float(ca_val)}')

        _, cb_val = get_const(params, 'customB', '0')
        cb_str = normalize_float3('float3', cb_val)
        out(f'#define L{N}_CUSTOM_B {cb_str}')
    else:
        out(f'#define L{N}_CUSTOM_A 0.0')
        out(f'#define L{N}_CUSTOM_B float3(0, 0, 0)')

    return lines, warnings


# ============================================================
# メイン
# ============================================================

def main():
    parser = argparse.ArgumentParser(
        description='ray-mmd material_2.0.fx → MaskedMaterial レイヤー変換'
    )
    parser.add_argument('input', help='入力 .fx ファイルパス')
    parser.add_argument('-l', '--layer', type=int, default=0,
                        help='出力レイヤー番号 (0-7, デフォルト: 0)')
    parser.add_argument('-s', '--shading-model', type=int, default=None,
                        help='シェーディングモデルID (省略時: 自動検出)')
    parser.add_argument('-o', '--output', default=None,
                        help='出力ファイルパス (省略時: 標準出力)')
    args = parser.parse_args()

    # 入力ファイル読み込み
    input_path = Path(args.input)
    encodings = ['utf-8', 'utf-8-sig', 'cp932', 'shift_jis', 'latin-1']
    text = None
    for enc in encodings:
        try:
            text = input_path.read_text(encoding=enc)
            break
        except (UnicodeDecodeError, UnicodeError):
            continue
    if text is None:
        print(f'エラー: {input_path} を読み込めません', file=sys.stderr)
        sys.exit(1)

    # 解析
    params = parse_material_fx(text)

    # シェーディングモデル
    if args.shading_model is not None:
        shading_model = args.shading_model
    else:
        shading_model = detect_shading_model(params)

    # 変換
    output_lines, warnings = convert(params, args.layer, shading_model)

    # ヘッダコメント
    header = [
        f'// Converted from: {input_path.name}',
        f'// Target layer: L{args.layer}',
        f'',
    ]

    result = '\n'.join(header + output_lines) + '\n'

    # 出力
    if args.output:
        out_path = Path(args.output)
        out_path.write_text(result, encoding='utf-8', newline='\n')
        print(f'出力: {out_path}', file=sys.stderr)
    else:
        print(result)

    # 警告
    if warnings:
        print('', file=sys.stderr)
        print('=== 警告 ===', file=sys.stderr)
        for w in warnings:
            print(f'  ! {w}', file=sys.stderr)


if __name__ == '__main__':
    main()
