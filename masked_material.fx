// ============================================================
// masked_material.fx
// Multi-layer material with bitmap mask blending
//
// ray-mmd Materials compatible G-Buffer material pass
// ============================================================
//
// Usage:
//   1. Set LAYER_COUNT (2-6)
//   2. Configure material parameters for each layer
//   3. Place grayscale mask PNGs in masks/ folder
//   4. Assign this .fx to target subset via MME
//
// Layer structure:
//   Layer 0 = Base layer (no mask needed, fills remaining area)
//   Layer 1-5 = Overlay layers (mask image defines region)
//
// Mask image spec:
//   - 8bit grayscale PNG
//   - White(255) = fully show this layer
//   - Black(0)   = hide this layer
//   - Mid values  = blend (for soft boundaries)
//
// Texture maps:
//   Per-layer external texture files can be assigned:
//     ALBEDO_MAP, ALBEDO_SUB_MAP, NORMAL_MAP, NORMAL_SUB_MAP,
//     SMOOTHNESS_MAP, METALNESS_MAP, SPECULAR_MAP, OCCLUSION_MAP, EMISSIVE_MAP
//   _MAP_FROM = 0: disabled (use constant), 1: load external file
//
// Mask packing:
//   MASK_PACKING = 0: individual grayscale PNGs (default, max 6 layers)
//   MASK_PACKING = 1: RGBA packed (max 2 textures, up to 8 layers)
//     TexA: R=mask1, G=mask2, B=mask3, A=mask4
//     TexB: R=mask5, G=mask6, B=mask7
//
// Sampler budget:
//   SM3.0 limit: 16 samplers
//   MASK_PACKING=0: Fixed = DiffuseMap(1) + Masks(LAYER_COUNT-1)
//   MASK_PACKING=1: Fixed = DiffuseMap(1) + PackedTex(1-2)
//     Layers 2-5: 1+1 = 2, Layers 6-8: 1+2 = 3
//   e.g. 8 layers packed = up to 13 external textures
//
// Shading model IDs:
//   0 = Default (standard PBR)
//   1 = Skin (subsurface scattering)
//   2 = Emissive (auto-applied when EMISSIVE is non-zero)
//   3 = Anisotropy
//   4 = Glass
//   5 = Cloth
//   6 = ClearCoat
//   7 = Subsurface
// ============================================================

// ==================== Basic Settings ====================

// Number of active layers, including Layer 0 (base)
// e.g. LAYER_COUNT=3 means L0(base) + L1 + L2
// Range: 2-6 (MASK_PACKING=0), 2-8 (MASK_PACKING=1)
#define LAYER_COUNT 3

// ==================== Mask Packing ====================
// 0 = individual grayscale PNGs (1 file per layer, max 6 layers)
// 1 = RGBA packed (mask1-4 in TexA.rgba, mask5-7 in TexB.rgb, max 8 layers)
#define MASK_PACKING 0

// ==================== Mask Files ====================
// --- Individual mode (MASK_PACKING=0) ---
#define MASK_1_FILE "masks/mask_1.png"
#define MASK_2_FILE "masks/mask_2.png"
#define MASK_3_FILE "masks/mask_3.png"
#define MASK_4_FILE "masks/mask_4.png"
#define MASK_5_FILE "masks/mask_5.png"

// --- Packed mode (MASK_PACKING=1) ---
// TexA: R=Layer1, G=Layer2, B=Layer3, A=Layer4
// TexB: R=Layer5, G=Layer6, B=Layer7, A=(unused)
// #define MASK_PACKED_A_FILE "masks/mask_packed_a.png"
// #define MASK_PACKED_B_FILE "masks/mask_packed_b.png"

// ==================== Common Settings ====================

// Alpha map (0=disabled, 3=model texture)
#define ALPHA_MAP_FROM 3
#define ALPHA_MAP_SWIZZLE 3   // 0=R, 1=G, 2=B, 3=A

// ==================== Layer 0: Base ====================
// No mask needed. Automatically fills areas not covered by other layers.

// --- Albedo ---
#define L0_ALBEDO      float3(1.0, 1.0, 1.0)  // Albedo color / tint
#define L0_ALBEDO_MAP_FROM 0                    // 0=constant/tint only, 1=external file
// #define L0_ALBEDO_MAP_FILE "textures/L0_albedo.png"
#define L0_ALBEDO_APPLY_DIFFUSE 1              // 1=multiply by model texture (MaterialDiffuse)

// --- Material properties ---
#define L0_SMOOTHNESS  0.0
#define L0_METALNESS   0.0
#define L0_SPECULAR    0.5             // Fresnel reflectance (x0.08 -> F0=0.04)

// --- Shading ---
#define L0_SHADING_MODEL 0             // Default
#define L0_EMISSIVE    float3(0, 0, 0)
#define L0_EMISSIVE_INTENSITY 0.0
#define L0_CUSTOM_A    0.0
#define L0_CUSTOM_B    float3(0, 0, 0)

// --- Texture maps (uncomment as needed) ---
// #define L0_NORMAL_MAP_FROM 1
// #define L0_NORMAL_MAP_FILE "textures/L0_normal.png"
// #define L0_NORMAL_MAP_SCALE 1.0
//
// #define L0_SMOOTHNESS_MAP_FROM 1
// #define L0_SMOOTHNESS_MAP_FILE "textures/L0_smoothness.png"

// ==================== Layer 1: Skin ====================

// --- Albedo ---
#define L1_ALBEDO      float3(1.0, 0.95, 0.9)
#define L1_ALBEDO_MAP_FROM 0
#define L1_ALBEDO_APPLY_DIFFUSE 1

// --- Material properties ---
#define L1_SMOOTHNESS  0.3
#define L1_METALNESS   0.0
#define L1_SPECULAR    0.5

// --- Shading ---
#define L1_SHADING_MODEL 1             // Skin
#define L1_EMISSIVE    float3(0, 0, 0)
#define L1_EMISSIVE_INTENSITY 0.0
#define L1_CUSTOM_A    0.5             // Skin curvature
#define L1_CUSTOM_B    float3(0.9, 0.5, 0.4)  // Subsurface color

// --- Texture maps (typical Skin material config) ---
// #define L1_NORMAL_MAP_FROM 1
// #define L1_NORMAL_MAP_FILE "textures/L1_normal.png"
// #define L1_NORMAL_MAP_SCALE 1.0
//
// #define L1_NORMAL_SUB_MAP_FROM 1
// #define L1_NORMAL_SUB_MAP_FILE "textures/L1_normal_sub.png"
// #define L1_NORMAL_SUB_MAP_SCALE 1.0
//
// #define L1_SMOOTHNESS_MAP_FROM 1
// #define L1_SMOOTHNESS_MAP_FILE "textures/L1_smoothness.png"

// ==================== Layer 2: Metal ====================

// --- Albedo ---
#define L2_ALBEDO      float3(0.85, 0.85, 0.85)
#define L2_ALBEDO_MAP_FROM 0           // No texture, constant color only
#define L2_ALBEDO_APPLY_DIFFUSE 0

// --- Material properties ---
#define L2_SMOOTHNESS  0.85
#define L2_METALNESS   1.0
#define L2_SPECULAR    0.5

// --- Shading ---
#define L2_SHADING_MODEL 0             // Default
#define L2_EMISSIVE    float3(0, 0, 0)
#define L2_EMISSIVE_INTENSITY 0.0
#define L2_CUSTOM_A    0.0
#define L2_CUSTOM_B    float3(0, 0, 0)

// --- Texture maps ---
// #define L2_ALBEDO_MAP_FROM 1
// #define L2_ALBEDO_MAP_FILE "textures/L2_albedo.png"
//
// #define L2_NORMAL_MAP_FROM 1
// #define L2_NORMAL_MAP_FILE "textures/L2_normal.png"
// #define L2_NORMAL_MAP_SCALE 1.0
//
// #define L2_OCCLUSION_MAP_FROM 1
// #define L2_OCCLUSION_MAP_FILE "textures/L2_occlusion.png"

// ==================== Layer 3-5 ====================
// Configure only the layers you need. Undefined parameters use defaults.
//
// Example (Layer 3: Cloth material):
//
// #define L3_ALBEDO      float3(0.3, 0.3, 0.6)
// #define L3_ALBEDO_MAP_FROM 0
// #define L3_ALBEDO_APPLY_DIFFUSE 1
// #define L3_SMOOTHNESS  0.5
// #define L3_METALNESS   0.0
// #define L3_SPECULAR    0.5
// #define L3_SHADING_MODEL 5           // Cloth
// #define L3_EMISSIVE    float3(0, 0, 0)
// #define L3_EMISSIVE_INTENSITY 0.0
// #define L3_CUSTOM_A    0.5           // Cloth sheen
// #define L3_CUSTOM_B    float3(0.5, 0.5, 0.8) // Subsurface color
//
// #define L3_NORMAL_MAP_FROM 1
// #define L3_NORMAL_MAP_FILE "textures/L3_normal.png"

// ==================== Texture Map Parameter Reference ====================
//
// Available texture map definitions for each layer (N=0-5):
//
// +------------------------------------------------------+
// | ALBEDO_MAP (Albedo map)                              |
// |   L{N}_ALBEDO_MAP_FROM    0=disabled, 1=external     |
// |   L{N}_ALBEDO_MAP_FILE    file path                  |
// |   L{N}_ALBEDO_APPLY_DIFFUSE  1=multiply MaterialDiff |
// +------------------------------------------------------+
// | ALBEDO_SUB_MAP (Sub-albedo map)                      |
// |   L{N}_ALBEDO_SUB_MAP_FROM   0=disabled, 1=external  |
// |   L{N}_ALBEDO_SUB_MAP_FILE   file path               |
// |   L{N}_ALBEDO_SUB_ENABLE     blend mode (1-5)        |
// |     1=multiply, 2=power, 3=add, 4=melanin, 5=alpha   |
// +------------------------------------------------------+
// | NORMAL_MAP (Normal map)                              |
// |   L{N}_NORMAL_MAP_FROM    0=disabled, 1=external     |
// |   L{N}_NORMAL_MAP_FILE    file path                  |
// |   L{N}_NORMAL_MAP_TYPE    0=RGB, 1=RG compressed     |
// |   L{N}_NORMAL_MAP_SCALE   intensity (default 1.0)    |
// |   L{N}_NORMAL_MAP_LOOP    UV repeat (default 1.0)    |
// +------------------------------------------------------+
// | NORMAL_SUB_MAP (Sub-normal map)                      |
// |   L{N}_NORMAL_SUB_MAP_FROM   0=disabled, 1=external  |
// |   L{N}_NORMAL_SUB_MAP_FILE   file path               |
// |   L{N}_NORMAL_SUB_MAP_TYPE   0=RGB, 1=RG compressed  |
// |   L{N}_NORMAL_SUB_MAP_SCALE  intensity (default 1.0) |
// |   L{N}_NORMAL_SUB_MAP_LOOP   UV repeat (default 1.0) |
// +------------------------------------------------------+
// | SMOOTHNESS_MAP (Smoothness map)                      |
// |   L{N}_SMOOTHNESS_MAP_FROM   0=disabled, 1=external  |
// |   L{N}_SMOOTHNESS_MAP_FILE   file path               |
// |   L{N}_SMOOTHNESS_MAP_SWIZZLE  0=R, 1=G, 2=B, 3=A   |
// |   L{N}_SMOOTHNESS_MAP_TYPE     0=Smooth, 1=Rough     |
// |   L{N}_SMOOTHNESS_MAP_LOOP     UV repeat             |
// +------------------------------------------------------+
// | METALNESS_MAP (Metalness map)                        |
// |   L{N}_METALNESS_MAP_FROM    0=disabled, 1=external  |
// |   L{N}_METALNESS_MAP_FILE    file path               |
// |   L{N}_METALNESS_MAP_SWIZZLE   0=R, 1=G, 2=B, 3=A   |
// |   L{N}_METALNESS_MAP_LOOP      UV repeat             |
// +------------------------------------------------------+
// | SPECULAR_MAP (Specular map)                          |
// |   L{N}_SPECULAR_MAP_FROM     0=disabled, 1=external  |
// |   L{N}_SPECULAR_MAP_FILE     file path               |
// |   L{N}_SPECULAR_MAP_SWIZZLE    0=R, 1=G, 2=B, 3=A   |
// |   L{N}_SPECULAR_MAP_LOOP       UV repeat             |
// +------------------------------------------------------+
// | OCCLUSION_MAP (Occlusion map)                        |
// |   L{N}_OCCLUSION_MAP_FROM    0=disabled, 1=external  |
// |   L{N}_OCCLUSION_MAP_FILE    file path               |
// |   L{N}_OCCLUSION_MAP_SWIZZLE   0=R, 1=G, 2=B, 3=A   |
// |   L{N}_OCCLUSION_MAP_LOOP      UV repeat             |
// +------------------------------------------------------+
// | EMISSIVE_MAP (Emissive map)                          |
// |   L{N}_EMISSIVE_MAP_FROM     0=disabled, 1=external  |
// |   L{N}_EMISSIVE_MAP_FILE     file path               |
// |   L{N}_EMISSIVE_MAP_LOOP        UV repeat            |
// +------------------------------------------------------+

#include "masked_material_common.fxsub"
