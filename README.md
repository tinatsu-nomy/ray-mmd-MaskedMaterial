# MaskedMaterial - ビットマップマスクによるマルチレイヤーマテリアル

ray-mmd 互換のマテリアルエフェクトです。  
1つのサブセット（材質）に対して、**ビットマップマスクで最大8種類のマテリアルを重ね合わせ**できます（RGBAパッキング時）。  
各レイヤーに**個別のテクスチャマップ**（法線、スムースネス等）を割り当てることも可能です。

---

## 目次

1. [概要](#概要)
2. [ファイル構成](#ファイル構成)
3. [クイックスタート](#クイックスタート)
4. [レイヤー構造](#レイヤー構造)
5. [マスク画像の仕様](#マスク画像の仕様)
6. [パラメータリファレンス](#パラメータリファレンス)
7. [テクスチャマップリファレンス](#テクスチャマップリファレンス)
8. [既存マテリアルからの移行](#既存マテリアルからの移行)
9. [変換ツール (convert_material.py)](#変換ツール-convert_materialpy)
10. [シェーディングモデル](#シェーディングモデル)
11. [ray-mmd マテリアルパターン一覧](#ray-mmd-マテリアルパターン一覧)
12. [マスクパッキング](#マスクパッキング)
13. [サンプラー予算](#サンプラー予算)
14. [Main パスとの組み合わせ](#main-パスとの組み合わせ)
15. [制約事項](#制約事項)
16. [トラブルシューティング](#トラブルシューティング)

---

## 概要

### 従来の制約

ray-mmd の標準マテリアルシステムでは、**1つのサブセット = 1つのマテリアル** という制約があります。  
異なる部分に異なるマテリアルを割り当てるには、PMXエディタで材質を分割する必要がありました。

### MaskedMaterial の解決策

MaskedMaterial では、グレースケールのマスク画像を使って、**1つのサブセット内でピクセル単位のマテリアル合成**を行います。

- **最大6レイヤー**（個別マスク）/ **最大8レイヤー**（RGBAパッキング）のマテリアルを重ね合わせ
- 各レイヤーに**個別の外部テクスチャマップ**を指定可能（法線、スムースネス、エミッシブ等）
- グレースケールマスクで**境界のぼかし**にも対応
- **RGBAパッキング**で VRAM最大75%削減、サンプラー最大5枠節約
- 使わないレイヤー・テクスチャは**サンプラーを消費しない**
- **変換ツール** (`convert_material.py`) で既存 material_2.0.fx から自動移行

---

## ファイル構成

```
MaskedMaterial/
├── masked_material.fx          ← ユーザー設定テンプレート
├── masked_material_common.fxsub ← コアシェーダ（編集不要）
├── convert_material.py         ← material_2.0.fx → レイヤー変換ツール
├── masks/                      ← マスク画像を配置
│   ├── mask_1.png              （個別モード）
│   ├── mask_packed_a.tga       （パッキングモード: RGBA）
│   └── mask_packed_b.tga       （パッキングモード: RGB）
├── textures/                   ← レイヤー別テクスチャを配置
│   ├── L0_normal.png
│   ├── L1_smoothness.png
│   └── ...
└── README.md
```

---

## クイックスタート

### Step 1: マスク画像を準備

UV展開に合わせた 8bit グレースケール PNG を `masks/` フォルダに配置。

### Step 2: masked_material.fx を編集

```hlsl
#define LAYER_COUNT 3

// マスクファイル
#define MASK_1_FILE "masks/skin.png"
#define MASK_2_FILE "masks/metal.png"

// Layer 0: ベース（マスク残り領域）
#define L0_ALBEDO      float3(1, 1, 1)
#define L0_SMOOTHNESS  0.0

// Layer 1: 肌（法線マップ付き）
#define L1_ALBEDO            float3(1.0, 0.95, 0.9)
#define L1_SMOOTHNESS        0.3
#define L1_SHADING_MODEL     1
#define L1_NORMAL_MAP_FROM   1
#define L1_NORMAL_MAP_FILE   "textures/skin_normal.png"
#define L1_NORMAL_SUB_MAP_FROM 1
#define L1_NORMAL_SUB_MAP_FILE "textures/skin_detail.png"

// Layer 2: 金属（専用アルベドテクスチャ）
#define L2_ALBEDO_MAP_FROM   1
#define L2_ALBEDO_MAP_FILE   "textures/metal_albedo.png"
#define L2_ALBEDO            float3(1, 1, 1)
#define L2_ALBEDO_APPLY_DIFFUSE 0
#define L2_SMOOTHNESS        0.85
#define L2_METALNESS         1.0

#include "masked_material_common.fxsub"
```

### Step 3: MME で割り当て

MME でこの .fx ファイルを対象サブセットに割り当てます。

---

## レイヤー構造

| レイヤー | マスク（個別） | マスク（RGBA パッキング） | 説明 |
|:--------:|:--------------:|:------------------------:|:-----|
| Layer 0 | 不要 | 不要 | ベース。他レイヤーが塗られていない部分に自動表示 |
| Layer 1 | mask_1.png | Tex A : R | オーバーレイ |
| Layer 2 | mask_2.png | Tex A : G | オーバーレイ |
| Layer 3 | mask_3.png | Tex A : B | オーバーレイ |
| Layer 4 | mask_4.png | Tex A : A | オーバーレイ |
| Layer 5 | mask_5.png | Tex B : R | オーバーレイ |
| Layer 6 | *(PACKING=1のみ)* | Tex B : G | オーバーレイ |
| Layer 7 | *(PACKING=1のみ)* | Tex B : B | オーバーレイ |

- Layer 0 の重みは `w0 = max(0, 1 - Σマスク値)` で自動計算されます。
- MASK_PACKING=0 の場合、最大 Layer 5 まで（6レイヤー）。
- MASK_PACKING=1 の場合、最大 Layer 7 まで（8レイヤー）。

---

## マスク画像の仕様

| 項目 | 仕様 |
|:-----|:-----|
| 形式 | 8bit グレースケール PNG |
| 解像度 | モデルテクスチャと同じ推奨 |
| UV座標 | モデルのUV展開と一致 |
| 白 (255) | そのレイヤーを完全に表示 |
| 黒 (0) | そのレイヤーを非表示 |
| 中間値 | ブレンド比率（境界のぼかし等） |

---

## パラメータリファレンス

### 基本パラメータ（各レイヤー共通）

`L{N}_` プレフィクス付き。N = 0～5（MASK_PACKING=1 の場合 0～7）。

| パラメータ | 型 | デフォルト | 説明 |
|:-----------|:---|:-----------|:-----|
| `ALBEDO` | float3 | (1,1,1) | アルベドカラー / ティント |
| `ALBEDO_MAP_FROM` | int | 0 | 0=定数, 1=外部ファイル |
| `ALBEDO_MAP_FILE` | string | - | アルベドテクスチャパス |
| `ALBEDO_APPLY_DIFFUSE` | int | 1 | 1=モデルテクスチャ(MaterialDiffuse)を乗算 |
| `SMOOTHNESS` | float | 0.0 | スムースネス値 (定数 / テクスチャ不使用時) |
| `METALNESS` | float | 0.0 | メタルネス値 |
| `SPECULAR` | float | 0.5 | スペキュラ強度 (×0.08 → F0) |
| `SHADING_MODEL` | int | 0 | シェーディングモデルID |
| `EMISSIVE` | float3 | (0,0,0) | エミッシブカラー |
| `EMISSIVE_INTENSITY` | float | 0.0 | エミッシブ強度 |
| `CUSTOM_A` | float | 0.0 | カスタムデータA |
| `CUSTOM_B` | float3 | (0,0,0) | カスタムデータB |

---

## テクスチャマップリファレンス

各レイヤーに以下のテクスチャマップを個別指定できます。  
`_MAP_FROM = 0`（デフォルト）で無効、`= 1` で外部ファイルを読み込みます。

### ALBEDO_MAP（アルベドマップ）

| パラメータ | デフォルト | 説明 |
|:-----------|:-----------|:-----|
| `L{N}_ALBEDO_MAP_FROM` | 0 | 0=無効, 1=外部ファイル |
| `L{N}_ALBEDO_MAP_FILE` | - | テクスチャファイルパス |
| `L{N}_ALBEDO_APPLY_DIFFUSE` | 1 | FROM=0時: 1でモデルテクスチャ乗算 |

FROM=1 の場合、テクスチャ × `L{N}_ALBEDO` (ティント) として使用。

### ALBEDO_SUB_MAP（サブアルベドマップ）

| パラメータ | デフォルト | 説明 |
|:-----------|:-----------|:-----|
| `L{N}_ALBEDO_SUB_MAP_FROM` | 0 | 0=無効, 1=外部ファイル |
| `L{N}_ALBEDO_SUB_MAP_FILE` | - | テクスチャファイルパス |
| `L{N}_ALBEDO_SUB_ENABLE` | 1 | 合成モード: 1=乗算, 2=べき乗, 3=加算, 5=αブレンド |

アルベドに対して追加の質感（メラニン、汚れ等）を合成します。

### NORMAL_MAP（法線マップ）

| パラメータ | デフォルト | 説明 |
|:-----------|:-----------|:-----|
| `L{N}_NORMAL_MAP_FROM` | 0 | 0=無効, 1=外部ファイル |
| `L{N}_NORMAL_MAP_FILE` | - | テクスチャファイルパス |
| `L{N}_NORMAL_MAP_TYPE` | 0 | 0=RGB法線, 1=RG圧縮 |
| `L{N}_NORMAL_MAP_SCALE` | 1.0 | 法線強度 |
| `L{N}_NORMAL_MAP_LOOP` | 1.0 | UVリピート数 |

### NORMAL_SUB_MAP（サブ法線マップ）

| パラメータ | デフォルト | 説明 |
|:-----------|:-----------|:-----|
| `L{N}_NORMAL_SUB_MAP_FROM` | 0 | 0=無効, 1=外部ファイル |
| `L{N}_NORMAL_SUB_MAP_FILE` | - | テクスチャファイルパス |
| `L{N}_NORMAL_SUB_MAP_TYPE` | 0 | 0=RGB法線, 1=RG圧縮 |
| `L{N}_NORMAL_SUB_MAP_SCALE` | 1.0 | 法線強度 |
| `L{N}_NORMAL_SUB_MAP_LOOP` | 1.0 | UVリピート数 |

NORMAL_MAP と NORMAL_SUB_MAP の両方が有効な場合、RNM (Reoriented Normal Mapping) で合成されます。  
レイヤー間の法線は重み付き線形補間 → `normalize()` でブレンドされます。

### SMOOTHNESS_MAP（スムースネスマップ）

| パラメータ | デフォルト | 説明 |
|:-----------|:-----------|:-----|
| `L{N}_SMOOTHNESS_MAP_FROM` | 0 | 0=無効, 1=外部ファイル |
| `L{N}_SMOOTHNESS_MAP_FILE` | - | テクスチャファイルパス |
| `L{N}_SMOOTHNESS_MAP_SWIZZLE` | 0 | 0=R, 1=G, 2=B, 3=A |
| `L{N}_SMOOTHNESS_MAP_TYPE` | 0 | 0=Smoothness値, 1=Roughness値(反転) |
| `L{N}_SMOOTHNESS_MAP_LOOP` | 1.0 | UVリピート数 |

FROM=1 の場合、テクスチャの値がそのまま使用されます（`L{N}_SMOOTHNESS` 定数は無視）。

### METALNESS_MAP / SPECULAR_MAP

| パラメータ | デフォルト | 説明 |
|:-----------|:-----------|:-----|
| `L{N}_{MAP}_MAP_FROM` | 0 | 0=無効, 1=外部ファイル |
| `L{N}_{MAP}_MAP_FILE` | - | テクスチャファイルパス |
| `L{N}_{MAP}_MAP_SWIZZLE` | 0 | 0=R, 1=G, 2=B, 3=A |
| `L{N}_{MAP}_MAP_LOOP` | 1.0 | UVリピート数 |

### OCCLUSION_MAP（オクルージョンマップ）

| パラメータ | デフォルト | 説明 |
|:-----------|:-----------|:-----|
| `L{N}_OCCLUSION_MAP_FROM` | 0 | 0=無効, 1=外部ファイル |
| `L{N}_OCCLUSION_MAP_FILE` | - | テクスチャファイルパス |
| `L{N}_OCCLUSION_MAP_SWIZZLE` | 0 | 0=R, 1=G, 2=B, 3=A |
| `L{N}_OCCLUSION_MAP_LOOP` | 1.0 | UVリピート数 |

ray-mmd の `material.visibility` にマッピングされます。FROM=0 の場合、オクルージョン = 1.0（遮蔽なし）。

### EMISSIVE_MAP（エミッシブマップ）

| パラメータ | デフォルト | 説明 |
|:-----------|:-----------|:-----|
| `L{N}_EMISSIVE_MAP_FROM` | 0 | 0=無効, 1=外部ファイル |
| `L{N}_EMISSIVE_MAP_FILE` | - | テクスチャファイルパス |
| `L{N}_EMISSIVE_MAP_LOOP` | 1.0 | UVリピート数 |

FROM=1 の場合、テクスチャ × `L{N}_EMISSIVE` (ティント) として使用。

---

## 既存マテリアルからの移行

### material_2.0.fx の場合

| 旧パラメータ | 新パラメータ |
|:-------------|:-------------|
| `const float3 albedo = ...` | `#define L{N}_ALBEDO float3(...)` |
| `#define ALBEDO_MAP_FROM 1` | `#define L{N}_ALBEDO_MAP_FROM 1` |
| `#define ALBEDO_MAP_FILE "..."` | `#define L{N}_ALBEDO_MAP_FILE "..."` |
| `const float smoothness = ...` | `#define L{N}_SMOOTHNESS ...` |
| `#define SMOOTHNESS_MAP_FROM 1` | `#define L{N}_SMOOTHNESS_MAP_FROM 1` |
| `const float metalness = ...` | `#define L{N}_METALNESS ...` |
| `#define NORMAL_MAP_FROM 1` | `#define L{N}_NORMAL_MAP_FROM 1` |
| `#define NORMAL_MAP_FILE "..."` | `#define L{N}_NORMAL_MAP_FILE "..."` |
| `const float normalMapScale = ...` | `#define L{N}_NORMAL_MAP_SCALE ...` |
| `#define NORMAL_SUB_MAP_FROM 1` | `#define L{N}_NORMAL_SUB_MAP_FROM 1` |
| `#define OCCLUSION_MAP_FROM 1` | `#define L{N}_OCCLUSION_MAP_FROM 1` |

### 移行例: Skin マテリアル

旧 (`material_skin.fx`):
```hlsl
const float3 albedo = 1.0;
const float smoothness = 0.5;
#define NORMAL_SUB_MAP_FROM 1
#define NORMAL_SUB_MAP_FILE "skin_normal.png"
const float normalSubMapScale = 1.0;
#define CUSTOM_ENABLE 1
const float customA = 0.5;
const float3 customB = float3(0.9, 0.5, 0.4);
```

新 (Layer 1 として):
```hlsl
#define L1_ALBEDO float3(1.0, 1.0, 1.0)
#define L1_SMOOTHNESS 0.5
#define L1_SHADING_MODEL 1
#define L1_NORMAL_SUB_MAP_FROM 1
#define L1_NORMAL_SUB_MAP_FILE "textures/skin_normal.png"
#define L1_NORMAL_SUB_MAP_SCALE 1.0
#define L1_CUSTOM_A 0.5
#define L1_CUSTOM_B float3(0.9, 0.5, 0.4)
```

### 移行時の注意点

| 旧パラメータ | 変換内容 | 備考 |
|:---|:---|:---|
| `ALBEDO_MAP_FROM 3` | `L{N}_ALBEDO_MAP_FROM 0` + `L{N}_ALBEDO_APPLY_DIFFUSE 1` | `FROM=3`（モデルテクスチャ）は非対応。`APPLY_DIFFUSE` で同等の効果 |
| `const float3 albedo = 1.0` | `#define L{N}_ALBEDO float3(1.0, 1.0, 1.0)` | `const` → `#define`、スカラー → `float3()` |
| `SMOOTHNESS_MAP_FROM 9` | 無効化（`FROM=0`） | `FROM` 値 2～9 は MaskedMaterial 非対応 |
| `CUSTOM_ENABLE 1` | `L{N}_SHADING_MODEL 1` + `L{N}_CUSTOM_A/B` | ray-mmd では `CUSTOM_ENABLE` の値がシェーディングモデルIDに対応 |
| `SSS_SKIN_TRANSMITTANCE(x)` | 事前計算した `float3(...)` | `masked_material_common.fxsub` にこのマクロがないため |
| `EMISSIVE_ENABLE 0` | `L{N}_EMISSIVE float3(0,0,0)` | 非ゼロで自動的に Emissive モデルになる |

---

## 変換ツール (convert_material.py)

既存の ray-mmd `material_2.0.fx` 形式のファイルを MaskedMaterial のレイヤー定義に自動変換するPythonスクリプトです。

### 使い方

```bash
# 基本: material_body.fx を L1 として変換（シェーディングモデル自動検出）
python convert_material.py material_body.fx --layer 1

# シェーディングモデルを明示指定
python convert_material.py material_cloth.fx -l 2 -s 5

# ファイルに出力
python convert_material.py material_skin.fx -l 1 -o layer1_output.txt
```

### オプション

| オプション | 短縮 | デフォルト | 説明 |
|:---|:---|:---|:---|
| `--layer` | `-l` | 0 | 出力レイヤー番号 (0-7) |
| `--shading-model` | `-s` | 自動検出 | シェーディングモデルID |
| `--output` | `-o` | 標準出力 | 出力ファイルパス |

### 自動検出される項目

- **シェーディングモデル**: `CUSTOM_ENABLE` の値から直接判定（1=Skin, 3=Anisotropy, 5=Cloth, 7=Subsurface）。`EMISSIVE_ENABLE=1` → Emissive (2)
- **SSS_SKIN_TRANSMITTANCE マクロ**: `exp((1-saturate(x)) * float3(-8,-40,-64))` を事前計算して `float3(...)` に変換
- **MAP_FROM 値 2～9**: 自動的に 0（無効）に変換し、警告を出力
- **スカラー→ベクトル変換**: `albedo = 1.0` → `float3(1.0, 1.0, 1.0)`

### 変換例

入力 (`material_body.fx`):
```hlsl
#define ALBEDO_MAP_FROM 3
#define ALBEDO_MAP_APPLY_DIFFUSE 1
const float3 albedo = 1.0;
const float smoothness = 0.55;
#define CUSTOM_ENABLE 1
const float customA = 0.6;
#define SSS_SKIN_TRANSMITTANCE(x) exp((1 - saturate(x)) * float3(-8, -40, -64))
const float3 customB = SSS_SKIN_TRANSMITTANCE(0.75);
```

出力 (`python convert_material.py material_body.fx -l 1`):
```hlsl
#define L1_ALBEDO float3(1.0, 1.0, 1.0)
#define L1_ALBEDO_MAP_FROM 0
#define L1_ALBEDO_APPLY_DIFFUSE 1
#define L1_SMOOTHNESS 0.55
#define L1_METALNESS 0.0
#define L1_SPECULAR 0.35
#define L1_SHADING_MODEL 1  // Skin
#define L1_CUSTOM_A 0.6
#define L1_CUSTOM_B float3(0.135335, 4.53999e-05, 1.12535e-07)
```

---

## シェーディングモデル

| ID | 名前 | 用途 | CUSTOM_A | CUSTOM_B |
|:--:|:-----|:-----|:---------|:---------|
| 0 | Default | 標準PBR | - | - |
| 1 | Skin | 皮膚SSS | 曲率 | サブサーフェスカラー |
| 2 | Emissive | 発光 | - | (自動:emissive色) |
| 3 | Anisotropy | 異方性 | 角度シフト | - |
| 4 | Glass | ガラス | - | - |
| 5 | Cloth | 布 | 光沢 | シーンカラー |
| 6 | ClearCoat | クリアコート | 滑らかさ | - |
| 7 | Subsurface | サブサーフェス | 曲率 | サブサーフェスカラー |

EMISSIVE 定数が非ゼロの場合、シェーディングモデルは自動的に Emissive (2) に設定されます。

ray-mmd では `CUSTOM_ENABLE` の値がシェーディングモデルIDに直接対応します:
- `CUSTOM_ENABLE = 0` → Default (0)
- `CUSTOM_ENABLE = 1` → Skin (1)
- `CUSTOM_ENABLE = 3` → Anisotropy (3)
- `CUSTOM_ENABLE = 5` → Cloth (5)
- `CUSTOM_ENABLE = 7` → Subsurface (7)

---

## ray-mmd マテリアルパターン一覧

ray-mmd の `Materials/` ディレクトリに含まれるマテリアルタイプと、MaskedMaterial への移行可否です。

| タイプ | CUSTOM_ENABLE | SHADING_MODEL | 特徴 | 変換可否 |
|:---|:---:|:---:|:---|:---:|
| **Standard** | 0 | 0 | 基本PBR、特殊設定なし | OK |
| **Skin** | 1 | 1 | SSS_SKIN_TRANSMITTANCE, ALBEDO_SUB_ENABLE=4, skin.png | OK |
| **Hair (Anisotropy)** | 3 | 3 | CUSTOM_B_MAP_FROM=1 (shift2.png) | OK |
| **Hair (SSS)** | 7 | 7 | CUSTOM_B_MAP_FROM=3 | OK |
| **Cloth** | 5 | 5 | 布用法線マップ, シーンカラー | OK |
| **ClearCoat** | 0 | 0 | metalness=1.0, 高smoothness | OK |
| **Metal** | 0 | 0 | ALBEDO_MAP_FROM=0, 固定albedo色 | OK |
| **Glass** | 0 | 4 | ALPHA_MAP_FROM=3, 透過 | OK |
| **Subsurface** | 0 | 7 | 翡翠/大理石等の半透明 | OK |
| **Emissive** | 0 | 2 | EMISSIVE_ENABLE=1, Blink変種あり | OK |
| **Editor** | 動的 | 動的 | static const + PMXコントローラー | NG (動的パラメータ) |
| **Programmable** | N/A | N/A | Water/Wetness、独自fxsub | NG (独自シェーダ) |

> `convert_material.py` は上記の OK マークのタイプを自動変換できます。  
> Editor 系（PMXコントローラー連動）と Programmable 系（Water/Wetness）は変換対象外です。

---

## マスクパッキング

`MASK_PACKING` でマスクの格納方式を切り替えられます。

| 値 | 方式 | 説明 |
|:--:|:-----|:-----|
| 0 | 個別グレースケール（デフォルト） | レイヤーごとに1枚の8bitグレースケールPNG |
| 1 | RGBパッキング | 2枚のRGBテクスチャにチャンネル分離で格納 |

### RGBAパッキングのチャンネル配置

| テクスチャ | R | G | B | A |
|:-----------|:--|:--|:--|:--|
| `MASK_PACKED_A_FILE` | mask1 (Layer 1) | mask2 (Layer 2) | mask3 (Layer 3) | mask4 (Layer 4) |
| `MASK_PACKED_B_FILE` | mask5 (Layer 5) | mask6 (Layer 6) | mask7 (Layer 7) | (未使用) |

- LAYER_COUNT 2～5: Tex A のみ使用（サンプラー1つ）
- LAYER_COUNT 6～8: Tex A + Tex B 使用（サンプラー2つ）
- **MASK_PACKING=1 の場合、最大8レイヤーまで拡張可能**

### 使い方

```hlsl
#define LAYER_COUNT 8
#define MASK_PACKING 1
#define MASK_PACKED_A_FILE "masks/mask_packed_a.png"   // RGBA: L1,L2,L3,L4
#define MASK_PACKED_B_FILE "masks/mask_packed_b.png"   // RGB: L5,L6,L7 (6層以上)
```

### パッキング画像の作成方法

個別のグレースケールマスク画像からRGBAパッキング画像を作成する方法です。

> **推奨出力形式: Targa（TGA）32bit**  
> PNG は可逆圧縮ですが、ツール依存で sRGB ガンマ補正や色空間の自動変換が発生し、  
> マスク値に意図しない誤差が生じる可能性があります。  
> TGA は非圧縮で値がそのまま保持されるため、Packed Texture には最も安全です。

#### Photoshop

準備: メニューバー →「ウィンドウ」→「レイヤー」/「チャンネル」でパネルを表示。

**RGBチャンネルへの格納:**

1. 各チャンネルに格納するグレースケールマスク画像を別レイヤーとして配置
2. レイヤーをダブルクリック →「レイヤースタイル」を開く
3. 「チャンネル」項目で格納先を1つだけチェック:
   - R だけチェック → Rチャンネルに格納（mask1）
   - G だけチェック → Gチャンネルに格納（mask2）
   - B だけチェック → Bチャンネルに格納（mask3）

**Alphaチャンネルへの格納:**

4. RGBチャンネルに格納したレイヤーを一旦非表示にする
5. Alpha用レイヤーを選択し、`Ctrl+A`（全選択）→ `Ctrl+C`（コピー）
6. チャンネルパネルの「+」ボタンで「アルファチャンネル1」を追加
7. 「アルファチャンネル1」を選択し、`Ctrl+Shift+V`（同じ位置にペースト）

**出力:**

8. アルファチャンネルとAlpha用レイヤーを非表示にする
9. 「ファイル → コピーを保存」→ **Targa（TGA）** → **32bit/pixel** で保存

> 参考: [RGBAチャンネルに別々のテクスチャを格納する方法](https://note.com/natty_violet4982/n/n63c40d27c434) (taka)

#### ImageMagick

**Tex A（RGBA: L1, L2, L3, L4）:**
```bash
magick mask_1.png mask_2.png mask_3.png mask_4.png \
  -channel RGBA -combine mask_packed_a.tga
```

**Tex B（RGB: L5, L6, L7）:**
```bash
magick mask_5.png mask_6.png mask_7.png \
  -channel RGB -combine mask_packed_b.tga
```

**レイヤー3つだけの場合（Aチャンネルを黒埋め）:**
```bash
magick mask_1.png mask_2.png mask_3.png \
  ( -clone 0 -evaluate set 0 ) \
  -channel RGBA -combine mask_packed_a.tga
```

> `-combine` はグレースケール画像を入力順に R, G, B, A へ割り当てます。  
> 確認: `magick identify -verbose mask_packed_a.tga` でチャンネル深度を確認できます。

#### Python (Pillow)

```python
from PIL import Image

r = Image.open("mask_1.png").convert("L")
g = Image.open("mask_2.png").convert("L")
b = Image.open("mask_3.png").convert("L")
a = Image.open("mask_4.png").convert("L")
Image.merge("RGBA", (r, g, b, a)).save("mask_packed_a.tga")
```

#### Substance Designer

1. RGBA Merge ノードを使用
2. 各チャンネル入力にグレースケール画像を接続
3. Targa 形式で出力

### メリット

- **VRAM削減**: 個別グレースケールはDX9内部で32bit/pixelに変換されるため、パッキングで最大75%削減
- **サンプラー節約**: マスク用サンプラーが最大7→最大2に（+5枠の余裕）
- **速度向上**: tex2D呼び出しが最大7→最大2に削減
- **レイヤー拡張**: 個別モードの最大6→パッキングモードの最大8レイヤー

---

## サンプラー予算

SM3.0 の上限: **16 サンプラー**

### 固定消費

| 用途 | MASK_PACKING=0 | MASK_PACKING=1 |
|:-----|:--------------:|:--------------:|
| DiffuseMapSamp | 1 | 1 |
| マスクテクスチャ | LAYER_COUNT - 1 | 1～2 |
| **固定合計** | **LAYER_COUNT** | **2～3** |

### レイヤー数別の外部テクスチャ予算

| LAYER_COUNT | 個別 (PACKING=0) | パッキング (PACKING=1) |
|:-----------:|:----------------:|:---------------------:|
| 2 | **14** | **14** |
| 3 | **13** | **14** |
| 4 | **12** | **14** |
| 5 | **11** | **14** |
| 6 | **10** | **13** |
| 7 | N/A | **13** |
| 8 | N/A | **13** |

### 外部テクスチャとは

`L{N}_*_MAP_FROM = 1` を指定したマップのみサンプラーを消費します。  
- `_MAP_FROM = 0` → サンプラー消費なし（定数値使用）
- `_MAP_FROM = 1` → **1サンプラー消費**

### 構成例 (LAYER_COUNT = 3, 予算13)

| Layer | ALBEDO | NORMAL | N_SUB | SMOOTH | 小計 |
|:-----:|:------:|:------:|:-----:|:------:|:----:|
| L0 ベース | `FROM=0` | 1 | - | - | 1 |
| L1 肌 | `FROM=0` | 1 | 1 | 1 | 3 |
| L2 金属 | 1 | 1 | - | 1 | 3 |
| **合計** | | | | | **7/13** ✓ |

---

## Main パスとの組み合わせ

ray-mmd では MME のエフェクト割当で **Main タブ** と **MaterialMap タブ** に別々のエフェクトを割り当てます。  
MaskedMaterial は **MaterialMap タブ** に割り当てるエフェクトです。

```
MME エフェクト割当:
┌──────────────┬──────────────────────────────────────┐
│ Main タブ     │ main.fx（フォワードレンダリング）       │
│ MaterialMap   │ masked_material.fx（G-Buffer書き込み） │
└──────────────┴──────────────────────────────────────┘
```

### Main パスのバリエーション

| ファイル | alphaThreshold | 用途 |
|:---|:---:|:---|
| `main.fx` | 0.999 | 通常の不透明オブジェクト（標準） |
| `main_ex_alpha.fx` | 1.1 | 半透明を完全に無視（G-Bufferから除外） |
| `main_ex_noalpha.fx` | 0.01 | アルファを完全に無効化（常に不透明） |
| `main_ex_mask.fx` | 0.01 | アルファマスク描画（くっきり切り抜き） |
| `main_ex_with_sphmap.fx` | 0.999 | main.fx + スフィアマップ対応 |

### 推奨組み合わせ

| モデルの材質 | Main タブ | MaterialMap タブ |
|:---|:---|:---|
| 通常（不透明） | `main.fx` | `masked_material.fx` |
| くっきり切り抜き（葉・レース） | `main_ex_mask.fx` | `masked_material.fx` |
| アルファが壊れたモデル | `main_ex_noalpha.fx` | `masked_material.fx` |
| スフィアマップ併用 | `main_ex_with_sphmap.fx` | `masked_material.fx` |

> Main と MaterialMap は独立したレンダリングパスです。  
> Main が「フォワード描画」、MaterialMap が「PBR属性のG-Buffer書き込み」を担当し、互いに干渉しません。  
> **重要**: Main 側と MaterialMap 側で `ALPHA_MAP_FROM` の設定を揃えてください。

---

## 制約事項

1. **ALPHA_MAP / PARALLAX_MAP はレイヤー別指定不可**  
   - ALPHA: ジオメトリ全体の表示/非表示を制御するため、レイヤー別に分ける意味がない
   - PARALLAX: UV変位が全テクスチャサンプリングに影響するため、マスクベースの合成と根本的に非互換

2. **`_MAP_FROM` は 0 (無効) と 1 (外部ファイル) のみ**  
   - ray-mmd 本体の `3`(モデルテクスチャ), `4`(スフィア), `5`(トゥーン) はマスクレイヤーシステムでは非対応
   - アルベドでモデルテクスチャを使う場合は `ALBEDO_APPLY_DIFFUSE = 1` を使用

3. **非ブレンド属性の境界**  
   - SHADING_MODEL, CUSTOM_A, CUSTOM_B はブレンドせず、最大重み(dominant)レイヤーの値を使用
   - マスク境界部分で急な切り替わりが発生する可能性あり

4. **CONTROLOBJECT 非対応**  
   - ボーン・モーフによるランタイム値変更は非対応

5. **法線マップの TYPE 制限**  
   - レイヤー別法線マップは TYPE 0 (RGB) と TYPE 1 (RG圧縮) のみ対応
   - TYPE 2 (グレースケール低品質) と TYPE 3 (グレースケール高品質) は非対応

---

## トラブルシューティング

### マスクが反映されない

- マスク画像がグレースケールか確認（RGB画像だと R チャンネルのみ使用）
- ファイルパスの大文字小文字を確認
- `LAYER_COUNT` がマスク数+1以上か確認

### 真っ黒になる

- `L{N}_ALBEDO` が `float3(0,0,0)` になっていないか確認
- アルベドテクスチャのパスが正しいか確認
- `ALBEDO_APPLY_DIFFUSE = 0` で定数カラーのみの場合、`ALBEDO` に適切な色を設定

### テクスチャが読み込まれない

- `_MAP_FROM = 1` が設定されているか確認
- ファイルパスが正しいか確認（.fx からの相対パス）
- SM3.0 サンプラー上限（16）を超えていないか確認

### コンパイルエラー

- `LAYER_COUNT` が 2～6（MASK_PACKING=0）または 2～8（MASK_PACKING=1）の範囲か確認
- `#define` の末尾にセミコロンがないか確認
- `float3(...)` の括弧が正しいか確認
- ファイルパスのダブルクォーテーション `"` が閉じているか確認（`error X1005: string continues past end of line` の原因）

### 法線マップの境界が不自然

- マスク画像の境界にぼかし（グラデーション）を入れる
- 法線はタンジェント空間で重み付き線形補間されるため、急なマスク変化は段差になりやすい
