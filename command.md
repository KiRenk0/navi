# HTV2 强三维（faceted3d）指令速查

> 主线冻结 baseline：vehicle=`specs/vehicles/htv2_faceted3d_0629.yaml`，case 模板=`specs/cases/doc_ma6_alpha5_h30km_faceted3d.yaml`，sampling=`specs/sampling/engineering_full_wing_surface_grid_81x41.yaml`（81×41 全翼面网格）。工况由 `--mach / --alpha / --h_m` 显式指定，YAML 里的工况会被命令行覆盖。

## 0 每条指令固定的三件套（vehicle / case / sampling）

- `--vehicle`：几何 + cp 模型 + faceted3d 配置（HTV2 主线固定用 `htv2_faceted3d_0629.yaml`，cp_model 已冻结为 `newtonian_like`，A=0.38、n=1.15；换别的会触发告警/报错）。
- `--case`：环境/边界模板（大气、壁面条件等），工况数值由命令行覆盖。
- `--sampling`：输出采样网格。

## 1 单工况（official CLI = run_case_rem.py）

- 最简：TPG 是唯一正式且唯一可运行的热力学 baseline；CLI 无 thermo 选择。
  - `python scripts/run_case_rem.py --vehicle specs/vehicles/htv2_faceted3d_0629.yaml --case specs/cases/doc_ma6_alpha5_h30km_faceted3d.yaml --sampling specs/sampling/engineering_full_wing_surface_grid_81x41.yaml --run_dir runs/htv2_ma6_a5_h30km --mach 6 --alpha 5 --h_m 30000 --save_npz`
- 高马赫示例（Ma=20, α=13.3°, h=40km）：
  - `python scripts/run_case_rem.py --vehicle specs/vehicles/htv2_faceted3d_0629.yaml --case specs/cases/doc_ma6_alpha5_h30km_faceted3d.yaml --sampling specs/sampling/engineering_full_wing_surface_grid_81x41.yaml --run_dir runs/htv2_ma20_a13p3_h40km --mach 20 --alpha 13.3 --h_m 40000 --save_npz`

### 常用开关（含义）

- `--mach / --alpha / --h_m`：工况。`--alpha` 单位是度；高度可用 `--h_m`（米）或 `--h_km`（千米）。
- `--save_npz`：输出 `fields.npz`（全字段，默认已开）。`--no_plots`：不出图（更快）。
- TPG 是唯一正式且唯一可运行的 thermodynamic model；CLI 不提供 thermo 选择参数。
- `--transition case|on|off`：转捩。`case`=按 YAML（默认）；`on`=启用；`off`=强制全层流。
- `--transition_weighting step|logistic|smoothstep`：转捩过渡的混合方式（不填=按 YAML）。
- `--plot_x_over_c_min 0.0`：只画 x/c ≥ 该值的区域。

### faceted3d 三维专属开关（敏感性分析用，默认 `case`=按 YAML）

- HTV2 3D 主线 YAML 默认：`effective_alpha=on`、`effective_mach=off`、`x_length_mode=streamline`。
- 运行时可显式覆盖：
  - `--f3_effective_alpha on|off`：边缘状态链里是否用 sweep 修正后的攻角。
  - `--f3_effective_mach on|off`：是否用 sweep-reduced Mach（临时打开对照就加 `--f3_effective_mach on`）。
  - `--f3_x_length_mode local|global|streamline`：迎风面发展长度模型。

## 2 多工况扫描（sweep wrapper = run_case_sweep.py）

- 固定 HTV2 强三维，扫 Ma 和 α：
  - `python scripts/run_case_sweep.py --vehicle specs/vehicles/htv2_faceted3d_0629.yaml --case specs/cases/doc_ma6_alpha5_h30km_faceted3d.yaml --sampling specs/sampling/engineering_full_wing_surface_grid_81x41.yaml --run_dir_base runs/htv2_scan --mach_list 7.5,8.0,8.3,8.7 --alpha_list 0.0,1.5,2.2,3.0 --plot_x_over_c_min 0.0`
- `--mach_list / --alpha_list` 也支持范围格式：`--mach_list 7.5:8.7:0.4 --alpha_list 0.0:3.0:0.5`。
- 敏感性覆盖开关（`--f3_effective_*` / `--f3_x_length_mode`）与单工况一致。

## 3 回归自检（唯一 current regression）

- baseline 仅含 TPG 两工况：`ma6_a5_h30km`、`ma8_a5_h40km`。
- 唯一命令：
  - `python scripts/tools/current_baseline_regression_check.py`

## 4 local-incidence QA

- 单元测试：
  - `python -m unittest tests.test_local_incidence -v`
- 数值 QA：
  - `python scripts/tools/local_incidence_raw_facet_qa.py`
- 攻角扫描：
  - `python scripts/tools/local_incidence_alpha_scan.py`

## 5 2D / 椭圆翼（非 HTV 强三维，保留备查）

- 2D 双楔：
- python scripts/run_case_rem.py --vehicle specs/vehicles/trapezoid_doublewedge_t0p034_sweep34.yaml --case specs/cases/doc_ma5_8_alpha5_h30km_rad.yaml --sampling specs/sampling/engineering_full_wing_surface_grid_81x41.yaml --mach 7.8 --alpha 7.5 --h_m 41500 --run_dir runs/trap_dw_t0034_ma7.8_h41500m_a7.5_2d

- 椭圆 t/c=0.03 对称翼型坐标： ellipse_t0p03_21pt.dat
- 对应机翼规格（根弦2 m、稍弦0.9 m、taper 0.45、emissivity 0.8）： trapezoid_ellipse_t0p03_taper0p45.yaml
- 示例运行：
  - python scripts/run_case_rem.py --vehicle specs/vehicles/trapezoid_ellipse_t0p03_taper0p45.yaml --case specs/cases/doc_ma5_8_alpha5_h30km_rad.yaml --sampling specs/sampling/baseline_root_windward_chord_line_12.yaml --mach 5.8 --alpha 5 --run_dir runs/ellipse_demo