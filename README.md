# MaskedMaterial - Multi-Layer Material with Bitmap Mask Blending

A ray-mmd compatible material effect.  
Blend **up to 8 different materials** on a single subset (material) using bitmap masks (with RGBA packing).  
Each layer can have its own **external texture maps** (normal, smoothness, emissive, etc.).

---

## Table of Contents

1. [Overview](#overview)
2. [File Structure](#file-structure)
3. [Quick Start](#quick-start)
4. [Layer Structure](#layer-structure)
5. [Mask Image Spec](#mask-image-spec)
6. [Parameter Reference](#parameter-reference)
7. [Texture Map Reference](#texture-map-reference)
8. [Migration from Existing Materials](#migration-from-existing-materials)
9. [Conversion Tool (convert_material.py)](#conversion-tool-convert_materialpy)
10. [Shading Models](#shading-models)
11. [ray-mmd Material Pattern Reference](#ray-mmd-material-pattern-reference)
12. [Mask Packing](#mask-packing)
13. [Sampler Budget](#sampler-budget)
14. [Combining with Main Pass](#combining-with-main-pass)
15. [Limitations](#limitations)
16. [Troubleshooting](#troubleshooting)

---

## Overview

### The Problem

In ray-mmd's standard material system, **one subset = one material**.  
To assign different materials to different parts, you had to split materials in PMX Editor.

### The Solution

MaskedMaterial uses grayscale mask images for **per-pixel material compositing within a single subset**.

- **Up to 6 layers** (individual masks) / **up to 8 layers** (RGBA packing)
- **Per-layer external texture maps** (normal, smoothness, emissive, etc.)
- Grayscale masks support **soft boundaries** (blending)
- **RGBA packing** saves up to 75% VRAM and 5 sampler slots
- Unused layers and textures **consume no samplers**
- **Conversion tool** (`convert_material.py`) for automatic migration from material_2.0.fx

---

## File Structure

```
MaskedMaterial/
├── masked_material.fx          <- User settings template
├── masked_material_common.fxsub <- Core shader (do not edit)
├── convert_material.py         <- material_2.0.fx -> layer conversion tool
├── masks/                      <- Place mask images here
│   ├── mask_1.png              (individual mode)
│   ├── mask_packed_a.tga       (packing mode: RGBA)
│   └── mask_packed_b.tga       (packing mode: RGB)
├── textures/                   <- Place per-layer textures here
│   ├── L0_normal.png
│   ├── L1_smoothness.png
│   └── ...
└── README.md
```

---

## Quick Start

### Step 1: Prepare Mask Images

Place 8-bit grayscale PNGs matching the model's UV layout in the `masks/` folder.

### Step 2: Edit masked_material.fx

```hlsl
#define LAYER_COUNT 3

// Mask files
#define MASK_1_FILE "masks/skin.png"
#define MASK_2_FILE "masks/metal.png"

// Layer 0: Base (fills remaining area)
#define L0_ALBEDO      float3(1, 1, 1)
#define L0_SMOOTHNESS  0.0

// Layer 1: Skin (with normal map)
#define L1_ALBEDO            float3(1.0, 0.95, 0.9)
#define L1_SMOOTHNESS        0.3
#define L1_SHADING_MODEL     1
#define L1_NORMAL_MAP_FROM   1
#define L1_NORMAL_MAP_FILE   "textures/skin_normal.png"
#define L1_NORMAL_SUB_MAP_FROM 1
#define L1_NORMAL_SUB_MAP_FILE "textures/skin_detail.png"

// Layer 2: Metal (with dedicated albedo texture)
#define L2_ALBEDO_MAP_FROM   1
#define L2_ALBEDO_MAP_FILE   "textures/metal_albedo.png"
#define L2_ALBEDO            float3(1, 1, 1)
#define L2_ALBEDO_APPLY_DIFFUSE 0
#define L2_SMOOTHNESS        0.85
#define L2_METALNESS         1.0

#include "masked_material_common.fxsub"
```

### Step 3: Assign to MaterialMap Tab in MME

MaskedMaterial must be assigned to the **MaterialMap** pass in ray-mmd.

1. MMD menu bar -> "MMEffect" -> "Effect Mapping"
2. Select the **"MaterialMap" tab** (NOT the "Main" tab)
3. Expand the target model tree and select the subset (material) to apply
4. Click "Select File" and choose `masked_material.fx`
5. Optionally assign `main.fx` (or an appropriate variant) to the "Main" tab

```
Effect Mapping Dialog:
┌─ Main ─┬─ MaterialMap ─┬─ Edge ─┬─ Shadow ─┐
│        │  <- HERE      │        │          │
├────────┴───────────────┴────────┴──────────┤
│ Model Name                                  │
│  ├ Subset 0: (none)                         │
│  ├ Subset 1: masked_material.fx  <- assign  │
│  └ Subset 2: (none)                         │
└─────────────────────────────────────────────┘
```

> **Important**: Always assign `masked_material.fx` to the **MaterialMap tab**.  
> Assigning it to the Main tab will not write to the G-Buffer, and materials will not be applied.

---

## Layer Structure

| Layer | Mask (Individual) | Mask (RGBA Packing) | Description |
|:-----:|:-----------------:|:-------------------:|:------------|
| Layer 0 | Not needed | Not needed | Base. Automatically fills areas not covered by other layers |
| Layer 1 | mask_1.png | Tex A : R | Overlay |
| Layer 2 | mask_2.png | Tex A : G | Overlay |
| Layer 3 | mask_3.png | Tex A : B | Overlay |
| Layer 4 | mask_4.png | Tex A : A | Overlay |
| Layer 5 | mask_5.png | Tex B : R | Overlay |
| Layer 6 | *(PACKING=1 only)* | Tex B : G | Overlay |
| Layer 7 | *(PACKING=1 only)* | Tex B : B | Overlay |

- Layer 0 weight is auto-calculated as `w0 = max(0, 1 - sum(masks))`.
- MASK_PACKING=0: up to Layer 5 (6 layers).
- MASK_PACKING=1: up to Layer 7 (8 layers).

---

## Mask Image Spec

| Property | Specification |
|:---------|:-------------|
| Format | 8-bit grayscale PNG |
| Resolution | Same as model texture (recommended) |
| UV coordinates | Must match model's UV layout |
| White (255) | Fully show this layer |
| Black (0) | Hide this layer |
| Mid values | Blend ratio (for soft boundaries) |

---

## Parameter Reference

### Base Parameters (Per Layer)

Prefixed with `L{N}_`. N = 0-5 (or 0-7 when MASK_PACKING=1).

| Parameter | Type | Default | Description |
|:----------|:-----|:--------|:------------|
| `ALBEDO` | float3 | (1,1,1) | Albedo color / tint |
| `ALBEDO_MAP_FROM` | int | 0 | 0=constant, 1=external file |
| `ALBEDO_MAP_FILE` | string | - | Albedo texture path |
| `ALBEDO_APPLY_DIFFUSE` | int | 1 | 1=multiply by model texture (MaterialDiffuse) |
| `SMOOTHNESS` | float | 0.0 | Smoothness value (when no texture) |
| `METALNESS` | float | 0.0 | Metalness value |
| `SPECULAR` | float | 0.5 | Specular intensity (x0.08 -> F0) |
| `SHADING_MODEL` | int | 0 | Shading model ID |
| `EMISSIVE` | float3 | (0,0,0) | Emissive color |
| `EMISSIVE_INTENSITY` | float | 0.0 | Emissive intensity |
| `CUSTOM_A` | float | 0.0 | Custom data A |
| `CUSTOM_B` | float3 | (0,0,0) | Custom data B |

---

## Texture Map Reference

Each layer can have individual texture maps.  
`_MAP_FROM = 0` (default) disables, `= 1` loads an external file.

### ALBEDO_MAP

| Parameter | Default | Description |
|:----------|:--------|:------------|
| `L{N}_ALBEDO_MAP_FROM` | 0 | 0=disabled, 1=external file |
| `L{N}_ALBEDO_MAP_FILE` | - | Texture file path |
| `L{N}_ALBEDO_APPLY_DIFFUSE` | 1 | When FROM=0: 1=multiply by model texture |

When FROM=1, used as texture x `L{N}_ALBEDO` (tint).

### ALBEDO_SUB_MAP

| Parameter | Default | Description |
|:----------|:--------|:------------|
| `L{N}_ALBEDO_SUB_MAP_FROM` | 0 | 0=disabled, 1=external file |
| `L{N}_ALBEDO_SUB_MAP_FILE` | - | Texture file path |
| `L{N}_ALBEDO_SUB_ENABLE` | 1 | Blend mode: 1=multiply, 2=power, 3=add, 5=alpha blend |

Composites additional texture detail (melanin, dirt, etc.) onto the albedo.

### NORMAL_MAP

| Parameter | Default | Description |
|:----------|:--------|:------------|
| `L{N}_NORMAL_MAP_FROM` | 0 | 0=disabled, 1=external file |
| `L{N}_NORMAL_MAP_FILE` | - | Texture file path |
| `L{N}_NORMAL_MAP_TYPE` | 0 | 0=RGB normal, 1=RG compressed |
| `L{N}_NORMAL_MAP_SCALE` | 1.0 | Normal intensity |
| `L{N}_NORMAL_MAP_LOOP` | 1.0 | UV repeat count |

### NORMAL_SUB_MAP

| Parameter | Default | Description |
|:----------|:--------|:------------|
| `L{N}_NORMAL_SUB_MAP_FROM` | 0 | 0=disabled, 1=external file |
| `L{N}_NORMAL_SUB_MAP_FILE` | - | Texture file path |
| `L{N}_NORMAL_SUB_MAP_TYPE` | 0 | 0=RGB normal, 1=RG compressed |
| `L{N}_NORMAL_SUB_MAP_SCALE` | 1.0 | Normal intensity |
| `L{N}_NORMAL_SUB_MAP_LOOP` | 1.0 | UV repeat count |

When both NORMAL_MAP and NORMAL_SUB_MAP are enabled, they are composited using RNM (Reoriented Normal Mapping).  
Normals between layers are blended via weighted linear interpolation followed by `normalize()`.

### SMOOTHNESS_MAP

| Parameter | Default | Description |
|:----------|:--------|:------------|
| `L{N}_SMOOTHNESS_MAP_FROM` | 0 | 0=disabled, 1=external file |
| `L{N}_SMOOTHNESS_MAP_FILE` | - | Texture file path |
| `L{N}_SMOOTHNESS_MAP_SWIZZLE` | 0 | 0=R, 1=G, 2=B, 3=A |
| `L{N}_SMOOTHNESS_MAP_TYPE` | 0 | 0=Smoothness, 1=Roughness (inverted) |
| `L{N}_SMOOTHNESS_MAP_LOOP` | 1.0 | UV repeat count |

When FROM=1, the texture value is used directly (`L{N}_SMOOTHNESS` constant is ignored).

### METALNESS_MAP / SPECULAR_MAP

| Parameter | Default | Description |
|:----------|:--------|:------------|
| `L{N}_{MAP}_MAP_FROM` | 0 | 0=disabled, 1=external file |
| `L{N}_{MAP}_MAP_FILE` | - | Texture file path |
| `L{N}_{MAP}_MAP_SWIZZLE` | 0 | 0=R, 1=G, 2=B, 3=A |
| `L{N}_{MAP}_MAP_LOOP` | 1.0 | UV repeat count |

### OCCLUSION_MAP

| Parameter | Default | Description |
|:----------|:--------|:------------|
| `L{N}_OCCLUSION_MAP_FROM` | 0 | 0=disabled, 1=external file |
| `L{N}_OCCLUSION_MAP_FILE` | - | Texture file path |
| `L{N}_OCCLUSION_MAP_SWIZZLE` | 0 | 0=R, 1=G, 2=B, 3=A |
| `L{N}_OCCLUSION_MAP_LOOP` | 1.0 | UV repeat count |

Maps to ray-mmd's `material.visibility`. When FROM=0, occlusion = 1.0 (no occlusion).

### EMISSIVE_MAP

| Parameter | Default | Description |
|:----------|:--------|:------------|
| `L{N}_EMISSIVE_MAP_FROM` | 0 | 0=disabled, 1=external file |
| `L{N}_EMISSIVE_MAP_FILE` | - | Texture file path |
| `L{N}_EMISSIVE_MAP_LOOP` | 1.0 | UV repeat count |

When FROM=1, used as texture x `L{N}_EMISSIVE` (tint).

---

## Migration from Existing Materials

### From material_2.0.fx

| Old Parameter | New Parameter |
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

### Example: Skin Material

Old (`material_skin.fx`):
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

New (as Layer 1):
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

### Migration Notes

| Old Parameter | Conversion | Notes |
|:---|:---|:---|
| `ALBEDO_MAP_FROM 3` | `L{N}_ALBEDO_MAP_FROM 0` + `L{N}_ALBEDO_APPLY_DIFFUSE 1` | `FROM=3` (model texture) not supported; use `APPLY_DIFFUSE` instead |
| `const float3 albedo = 1.0` | `#define L{N}_ALBEDO float3(1.0, 1.0, 1.0)` | `const` -> `#define`, scalar -> `float3()` |
| `SMOOTHNESS_MAP_FROM 9` | Disabled (`FROM=0`) | `FROM` values 2-9 not supported in MaskedMaterial |
| `CUSTOM_ENABLE 1` | `L{N}_SHADING_MODEL 1` + `L{N}_CUSTOM_A/B` | In ray-mmd, `CUSTOM_ENABLE` value maps directly to shading model ID |
| `SSS_SKIN_TRANSMITTANCE(x)` | Pre-computed `float3(...)` | This macro is not available in `masked_material_common.fxsub` |
| `EMISSIVE_ENABLE 0` | `L{N}_EMISSIVE float3(0,0,0)` | Non-zero automatically triggers Emissive shading model |

---

## Conversion Tool (convert_material.py)

A Python script that automatically converts existing ray-mmd `material_2.0.fx` files to MaskedMaterial layer definitions.

### Usage

```bash
# Basic: convert material_body.fx as L1 (auto-detect shading model)
python convert_material.py material_body.fx --layer 1

# Explicitly specify shading model
python convert_material.py material_cloth.fx -l 2 -s 5

# Output to file
python convert_material.py material_skin.fx -l 1 -o layer1_output.txt
```

### Options

| Option | Short | Default | Description |
|:---|:---|:---|:---|
| `--layer` | `-l` | 0 | Output layer number (0-7) |
| `--shading-model` | `-s` | Auto-detect | Shading model ID |
| `--output` | `-o` | stdout | Output file path |

### Auto-Detection

- **Shading model**: Detected from `CUSTOM_ENABLE` value (1=Skin, 3=Anisotropy, 5=Cloth, 7=Subsurface). `EMISSIVE_ENABLE=1` -> Emissive (2)
- **SSS_SKIN_TRANSMITTANCE macro**: Pre-computes `exp((1-saturate(x)) * float3(-8,-40,-64))` to `float3(...)`
- **MAP_FROM values 2-9**: Automatically converted to 0 (disabled) with a warning
- **Scalar to vector**: `albedo = 1.0` -> `float3(1.0, 1.0, 1.0)`

### Conversion Example

Input (`material_body.fx`):
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

Output (`python convert_material.py material_body.fx -l 1`):
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

## Shading Models

| ID | Name | Use | CUSTOM_A | CUSTOM_B |
|:--:|:-----|:----|:---------|:---------|
| 0 | Default | Standard PBR | - | - |
| 1 | Skin | Skin SSS | Curvature | Subsurface color |
| 2 | Emissive | Light emission | - | (auto: emissive color) |
| 3 | Anisotropy | Anisotropic | Angle shift | - |
| 4 | Glass | Glass | - | - |
| 5 | Cloth | Fabric | Sheen | Sheen color |
| 6 | ClearCoat | Clear coat | Smoothness | - |
| 7 | Subsurface | Subsurface scattering | Curvature | Subsurface color |

When the EMISSIVE constant is non-zero, the shading model is automatically set to Emissive (2).

In ray-mmd, `CUSTOM_ENABLE` values map directly to shading model IDs:
- `CUSTOM_ENABLE = 0` -> Default (0)
- `CUSTOM_ENABLE = 1` -> Skin (1)
- `CUSTOM_ENABLE = 3` -> Anisotropy (3)
- `CUSTOM_ENABLE = 5` -> Cloth (5)
- `CUSTOM_ENABLE = 7` -> Subsurface (7)

---

## ray-mmd Material Pattern Reference

Material types found in ray-mmd's `Materials/` directory and their conversion compatibility.

| Type | CUSTOM_ENABLE | SHADING_MODEL | Characteristics | Convertible |
|:---|:---:|:---:|:---|:---:|
| **Standard** | 0 | 0 | Basic PBR, no special settings | OK |
| **Skin** | 1 | 1 | SSS_SKIN_TRANSMITTANCE, ALBEDO_SUB_ENABLE=4, skin.png | OK |
| **Hair (Anisotropy)** | 3 | 3 | CUSTOM_B_MAP_FROM=1 (shift2.png) | OK |
| **Hair (SSS)** | 7 | 7 | CUSTOM_B_MAP_FROM=3 | OK |
| **Cloth** | 5 | 5 | Fabric normal map, sheen color | OK |
| **ClearCoat** | 0 | 0 | metalness=1.0, high smoothness | OK |
| **Metal** | 0 | 0 | ALBEDO_MAP_FROM=0, fixed albedo color | OK |
| **Glass** | 0 | 4 | ALPHA_MAP_FROM=3, transparency | OK |
| **Subsurface** | 0 | 7 | Jade/marble/lampshade translucency | OK |
| **Emissive** | 0 | 2 | EMISSIVE_ENABLE=1, blink variants | OK |
| **Editor** | Dynamic | Dynamic | static const + PMX controller | NG (dynamic params) |
| **Programmable** | N/A | N/A | Water/Wetness, custom fxsub | NG (custom shader) |

> `convert_material.py` can automatically convert all types marked OK.  
> Editor types (PMX controller linked) and Programmable types (Water/Wetness) are not convertible.

---

## Mask Packing

`MASK_PACKING` switches the mask storage method.

| Value | Method | Description |
|:-----:|:-------|:------------|
| 0 | Individual grayscale (default) | One 8-bit grayscale PNG per layer |
| 1 | RGBA packing | Channel-packed into 2 RGBA textures |

### RGBA Packing Channel Layout

| Texture | R | G | B | A |
|:--------|:--|:--|:--|:--|
| `MASK_PACKED_A_FILE` | mask1 (Layer 1) | mask2 (Layer 2) | mask3 (Layer 3) | mask4 (Layer 4) |
| `MASK_PACKED_B_FILE` | mask5 (Layer 5) | mask6 (Layer 6) | mask7 (Layer 7) | (unused) |

- LAYER_COUNT 2-5: Tex A only (1 sampler)
- LAYER_COUNT 6-8: Tex A + Tex B (2 samplers)
- **MASK_PACKING=1 enables up to 8 layers**

### Usage

```hlsl
#define LAYER_COUNT 8
#define MASK_PACKING 1
#define MASK_PACKED_A_FILE "masks/mask_packed_a.tga"   // RGBA: L1,L2,L3,L4
#define MASK_PACKED_B_FILE "masks/mask_packed_b.tga"   // RGB: L5,L6,L7 (6+ layers)
```

### Creating Packed Mask Images

How to create RGBA packed images from individual grayscale mask images.

> **Recommended output format: Targa (TGA) 32-bit**  
> PNG is lossless but tool-dependent sRGB gamma correction and color space auto-conversion  
> can introduce unintended errors in mask values.  
> TGA is uncompressed and preserves values exactly, making it the safest choice for packed textures.

#### Photoshop

Preparation: Menu bar -> "Window" -> "Layers" / "Channels" to show panels.

**Storing to RGB channels:**

1. Place each grayscale mask image on a separate layer
2. Double-click the layer -> open "Layer Style"
3. Under "Channels", check only the target channel:
   - R only -> stores to R channel (mask1)
   - G only -> stores to G channel (mask2)
   - B only -> stores to B channel (mask3)

**Storing to Alpha channel:**

4. Hide the RGB-assigned layers temporarily
5. Select the Alpha layer, `Ctrl+A` (Select All) -> `Ctrl+C` (Copy)
6. Click the "+" button in the Channels panel to add "Alpha Channel 1"
7. Select "Alpha Channel 1" and `Ctrl+Shift+V` (Paste in Place)

**Export:**

8. Hide the Alpha channel and Alpha layer
9. "File -> Save a Copy" -> **Targa (TGA)** -> **32 bits/pixel**

> Reference: [Storing Separate Textures in RGBA Channels](https://note.com/natty_violet4982/n/n63c40d27c434) (taka)

#### ImageMagick

**Tex A (RGBA: L1, L2, L3, L4):**
```bash
magick mask_1.png mask_2.png mask_3.png mask_4.png \
  -channel RGBA -combine mask_packed_a.tga
```

**Tex B (RGB: L5, L6, L7):**
```bash
magick mask_5.png mask_6.png mask_7.png \
  -channel RGB -combine mask_packed_b.tga
```

**3 layers only (fill A channel with black):**
```bash
magick mask_1.png mask_2.png mask_3.png \
  ( -clone 0 -evaluate set 0 ) \
  -channel RGBA -combine mask_packed_a.tga
```

> `-combine` assigns grayscale images to R, G, B, A in input order.  
> Verify: `magick identify -verbose mask_packed_a.tga` to check channel depth.

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

1. Use the RGBA Merge node
2. Connect grayscale images to each channel input
3. Export in Targa format

### Benefits

- **VRAM reduction**: Individual grayscale textures are internally converted to 32-bit/pixel in DX9, so packing saves up to 75%
- **Sampler savings**: Mask samplers reduced from up to 7 to a maximum of 2 (+5 slots freed)
- **Speed improvement**: tex2D calls reduced from up to 7 to a maximum of 2
- **Layer expansion**: Individual mode max 6 -> packing mode max 8 layers

---

## Sampler Budget

SM3.0 limit: **16 samplers**

### Fixed Consumption

| Usage | MASK_PACKING=0 | MASK_PACKING=1 |
|:------|:--------------:|:--------------:|
| DiffuseMapSamp | 1 | 1 |
| Mask textures | LAYER_COUNT - 1 | 1-2 |
| **Fixed total** | **LAYER_COUNT** | **2-3** |

### Texture Budget by Layer Count

| LAYER_COUNT | Individual (PACKING=0) | Packed (PACKING=1) |
|:-----------:|:----------------------:|:-------------------:|
| 2 | **14** | **14** |
| 3 | **13** | **14** |
| 4 | **12** | **14** |
| 5 | **11** | **14** |
| 6 | **10** | **13** |
| 7 | N/A | **13** |
| 8 | N/A | **13** |

### What Counts as an External Texture

Only maps with `L{N}_*_MAP_FROM = 1` consume a sampler.  
- `_MAP_FROM = 0` -> no sampler consumed (constant value used)
- `_MAP_FROM = 1` -> **1 sampler consumed**

### Example Configuration (LAYER_COUNT = 3, budget 13)

| Layer | ALBEDO | NORMAL | N_SUB | SMOOTH | Subtotal |
|:-----:|:------:|:------:|:-----:|:------:|:--------:|
| L0 Base | `FROM=0` | 1 | - | - | 1 |
| L1 Skin | `FROM=0` | 1 | 1 | 1 | 3 |
| L2 Metal | 1 | 1 | - | 1 | 3 |
| **Total** | | | | | **7/13** |

---

## Combining with Main Pass

In ray-mmd, the MME effect mapping assigns separate effects to the **Main tab** and **MaterialMap tab**.  
MaskedMaterial is assigned to the **MaterialMap tab**.

```
MME Effect Mapping:
┌──────────────┬──────────────────────────────────────────┐
│ Main tab     │ main.fx (forward rendering)              │
│ MaterialMap  │ masked_material.fx (G-Buffer write)      │
└──────────────┴──────────────────────────────────────────┘
```

### Main Pass Variants

| File | alphaThreshold | Use |
|:-----|:--------------:|:----|
| `main.fx` | 0.999 | Standard opaque objects (default) |
| `main_ex_alpha.fx` | 1.1 | Completely ignore semi-transparency (exclude from G-Buffer) |
| `main_ex_noalpha.fx` | 0.01 | Completely disable alpha (always opaque) |
| `main_ex_mask.fx` | 0.01 | Alpha mask rendering (sharp cutout) |
| `main_ex_with_sphmap.fx` | 0.999 | main.fx + sphere map support |

### Recommended Combinations

| Material Type | Main Tab | MaterialMap Tab |
|:---|:---|:---|
| Standard (opaque) | `main.fx` | `masked_material.fx` |
| Sharp cutout (leaves, lace) | `main_ex_mask.fx` | `masked_material.fx` |
| Broken alpha model | `main_ex_noalpha.fx` | `masked_material.fx` |
| With sphere map | `main_ex_with_sphmap.fx` | `masked_material.fx` |

> Main and MaterialMap are independent rendering passes.  
> Main handles "forward rendering", MaterialMap handles "PBR attribute G-Buffer writing" -- they do not interfere with each other.  
> **Important**: Keep `ALPHA_MAP_FROM` settings consistent between Main and MaterialMap.

---

## Limitations

1. **ALPHA_MAP / PARALLAX_MAP cannot be set per layer**  
   - ALPHA: Controls geometry-wide visibility, so per-layer separation is meaningless
   - PARALLAX: UV displacement affects all texture sampling, fundamentally incompatible with mask-based compositing

2. **`_MAP_FROM` only supports 0 (disabled) and 1 (external file)**  
   - ray-mmd's `3` (model texture), `4` (sphere), `5` (toon) are not supported in the mask layer system
   - To use model texture for albedo, use `ALBEDO_APPLY_DIFFUSE = 1`

3. **Non-blendable attribute boundaries**  
   - SHADING_MODEL, CUSTOM_A, CUSTOM_B are not blended; the dominant (max weight) layer's values are used
   - Abrupt transitions may occur at mask boundaries

4. **CONTROLOBJECT not supported**  
   - Runtime value changes via bones/morphs are not supported

5. **Normal map TYPE limitation**  
   - Per-layer normal maps support only TYPE 0 (RGB) and TYPE 1 (RG compressed)
   - TYPE 2 (grayscale low quality) and TYPE 3 (grayscale high quality) are not supported

---

## Troubleshooting

### Mask not applied

- Verify mask image is grayscale (RGB images will only use the R channel)
- Check file path case sensitivity
- Ensure `LAYER_COUNT` is >= number of masks + 1

### Screen goes black

- Check that `L{N}_ALBEDO` is not `float3(0,0,0)`
- Verify albedo texture path is correct
- When `ALBEDO_APPLY_DIFFUSE = 0` with constant color only, set `ALBEDO` to an appropriate color

### Texture not loading

- Verify `_MAP_FROM = 1` is set
- Check file path is correct (relative to .fx file)
- Ensure SM3.0 sampler limit (16) is not exceeded

### Compile errors

- Verify `LAYER_COUNT` is in range 2-6 (MASK_PACKING=0) or 2-8 (MASK_PACKING=1)
- Check for semicolons at the end of `#define` lines
- Verify `float3(...)` parentheses are correct
- Check that file path double quotes `"` are properly closed (`error X1005: string continues past end of line`)

### Unnatural normal map boundaries

- Add blur (gradient) to mask image boundaries
- Normals are blended via weighted linear interpolation in tangent space, so abrupt mask changes can cause visible seams
