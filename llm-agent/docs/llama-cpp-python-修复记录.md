# llama-cpp-python 空指针崩溃修复记录

> **日期**: 2026-07-24  
> **问题**: `OSError: exception: access violation reading 0x0000000000000000`  
> **影响**: LLM 模型无法加载，ReAct 引擎无法初始化，服务降级运行

---

## 1. 问题根因

### 1.1 直接原因

`llama-cpp-python` 的 CUDA 编译版本在纯 CPU 机器上调用 `llama_backend_init()` 时，C 层尝试加载 CUDA 运行时 DLL（`cublas.dll`、`cudart.dll` 等），找不到则触发空指针访问违例。

### 1.2 环境问题链

```
系统 CUDA_PATH 错误指向 PyCharm 路径
  → llama-cpp-python 的 _ctypes_extensions.py 尝试 os.add_dll_directory() 不存在的目录
  → 即使清理 CUDA_PATH 后，CUDA 编译的 llama.dll 在 llama_backend_init() 中
    仍会尝试加载 CUDA 运行时 DLL
  → 本机无 NVIDIA GPU + 无 CUDA Toolkit → 空指针崩溃
```

### 1.3 双 Python 环境问题

系统中存在两个 Python：

| 环境 | 路径 | llama-cpp-python |
|------|------|------------------|
| Anaconda Python 3.8 | `F:\Anaconda3\python.exe` | 0.2.90 (CPU, 修复后) |
| Windows Python 3.10 | `C:\Program Files\Python310\python.exe` | 0.3.18 (CUDA, **崩溃**) |

- **Git Bash** 中 `python` 优先找到 Anaconda → 正常
- **cmd** 中 `python` 优先找到 Python 3.10 → 崩溃

### 1.4 错误的环境变量

系统环境变量 `CUDA_PATH` 及相关变量被错误设置为 PyCharm 安装路径：

```
CUDA_PATH          = F:\pycharm\PyCharm Community Edition 2020.3.5\Program Files
CUDA_PATH_V11_0    = F:\pycharm\PyCharm Community Edition 2020.3.5\Program Files
NVCUDASAMPLES_ROOT = F:\pycharm\PyCharm Community Edition 2020.3.5\Program Files
...
```

PATH 中包含不存在的 CUDA 目录条目：
```
F:\pycharm\...\Program Files\CUDA\bin
F:\pycharm\...\Program Files\CUDA\include
F:\pycharm\...\Program Files\libnvvp
```

---

## 2. 修复内容

### 2.1 `llm-agent/src/main.py` — 环境变量清理增强

**位置**: `lifespan()` 函数，LLM 模型加载前

**修改要点**:

1. **全量 CUDA 变量清理** — 遍历所有环境变量，按关键词匹配清理：

```python
for _var in list(os.environ.keys()):
    _upper = _var.upper()
    if any(kw in _upper for kw in (
        "CUDA_PATH", "CUDA_HOME", "CUDA_TOOLKIT", "CUDA_MODULE",
        "CUDA_CACHE", "CUDA_VISIBLE", "CUDA_VERSION",
        "NVCC", "NVIDIA_DRIVER", "NVTOOLSEXT",
        "NVCUDASAMPLES", "GPU_", "GGML_CUDA",
    )):
        _cleaned_cuda_vars.append(f"{_var}={os.environ.pop(_var)}")
```

2. **PATH 清理** — 移除包含 CUDA/NVIDIA 关键字的路径条目：

```python
if any(kw in _lower for kw in (
    "cuda", "nvcc", "cublas", "cudnn",
    "nvidia corp", "nvidia gpu", "libnvvp", "nsight",
)):
    # 移除此条目
```

3. **OSError 专项捕获** — 识别 C 层空指针崩溃，输出中文解决方案：

```python
except OSError as e:
    if "access violation" in str(e).lower() or "0x0000000000000000" in str(e):
        logger.error(
            f"LLM 模型加载失败（C 层空指针崩溃）: {e}\n"
            f"根本原因: llama-cpp-python 可能是 CUDA 编译版本，但本机没有 NVIDIA GPU。\n"
            f"解决方案: 请使用 conda 安装 CPU 版本:\n"
            f"  conda install -c conda-forge llama-cpp-python\n"
            f"或修复 CUDA_PATH 环境变量后重新安装 CPU-only 版本。"
        )
```

### 2.2 `llm-agent/start.bat` — 启动脚本更新

**修改要点**:

1. 扩充环境变量清理列表（从 1 个扩展到 13 个）：

```batch
set CUDA_PATH=
set CUDA_PATH_V11_0=
set CUDA_PATH_V12_4=
set CUDA_HOME=
set CUDA_TOOLKIT_ROOT_DIR=
set CUDA_MODULE_LOADING=
set CUDA_CACHE_PATH=
set CUDA_VISIBLE_DEVICES=
set NVCC=
set NVIDIA_DRIVER=
set NVCUDASAMPLES_ROOT=
set NVCUDASAMPLES11_0_ROOT=
set NVTOOLSEXT_PATH=
set GGML_CUDA_NO_PIN_MEM=
```

2. 使用 Anaconda Python 完整路径（避免 cmd 中误用 Python 3.10）：

```batch
REM 使用 Anaconda Python（避免 cmd 中默认 Python 3.10 的 CUDA 版 llama-cpp-python）
F:\Anaconda3\python.exe src/main.py
```

### 2.3 llama-cpp-python 版本替换

| 环境 | 修复前 | 修复后 |
|------|--------|--------|
| Python 3.8 (Anaconda) | 0.3.2 CUDA 版 | **0.2.90 CPU 预编译 wheel** |
| Python 3.10 (Windows) | 0.3.18 CUDA 版 | **0.2.90 CPU 预编译 wheel** |

安装来源：
```
https://github.com/abetlen/llama-cpp-python/releases/download/v0.2.90/
  llama_cpp_python-0.2.90-cp38-cp38-win_amd64.whl
  llama_cpp_python-0.2.90-cp310-cp310-win_amd64.whl
```

### 2.4 `llm-agent/diagnose.py` — 诊断脚本（新增）

逐步检测脚本，用于排查 llama-cpp-python 加载问题：
1. Python 路径和版本
2. 清理前的 CUDA 环境变量
3. PATH 中的 CUDA 条目
4. 执行环境变量清理
5. 清理后验证
6. 导入 llama_cpp
7. 调用 `llama_backend_init()`
8. 加载模型

```batch
python diagnose.py
```

---

## 3. 验证结果

```
============================================================
  llama-cpp-python 环境诊断
============================================================

[1] Python 路径: F:\Anaconda3\python.exe
    Python 版本: 3.8.8

[2] CUDA/NVIDIA 环境变量（清理前）:
    CUDA_PATH = F:\pycharm\...
    CUDA_PATH_V11_0 = F:\pycharm\...
    ... (共 5 个)

[3] PATH 中的 CUDA/NVIDIA 条目:
    ... (共 6 个)

[4] 执行环境变量清理...
    清理了 11 个项目

[5] 清理后残留的 CUDA 变量:
    (无残留)

[6] 导入 llama_cpp...
    导入成功 (版本: 0.2.90)

[7] 调用 llama_backend_init()...
    成功!

[8] 加载模型...
    模型加载成功!

============================================================
  诊断完成：一切正常！
============================================================
```

服务健康检查：

```json
{
  "status": "healthy",
  "model_loaded": true,
  "tools_count": 7,
  "memory_usage_mb": 571.44
}
```

---

## 4. CPU/GPU 自动切换方案

### 4.1 原理

单个 `llama-cpp-python` 安装即可支持 CPU/GPU 自动切换，无需安装两个版本：

- **安装 CUDA 编译版本**（正确构建的，如 conda-forge 的 0.3.x+）
- **运行时通过 `n_gpu_layers` 参数控制**：
  - `n_gpu_layers=0` → 纯 CPU 推理
  - `n_gpu_layers=-1` → 所有层卸载到 GPU
  - `n_gpu_layers=N` → 前 N 层卸载到 GPU

### 4.2 推荐实现

```python
import torch

# 检测 GPU
_gpu_available = torch.cuda.is_available()
_n_gpu_layers = -1 if _gpu_available else 0

llm_instance = Llama(
    model_path=model_path,
    n_ctx=app_config.N_CTX,
    n_threads=app_config.N_THREADS,
    n_gpu_layers=_n_gpu_layers,  # 0=CPU, -1=ALL GPU
    verbose=False,
)
```

> **注意**: 当前安装的 0.2.90 是 CPU-only 版本，`n_gpu_layers` 参数不生效。  
> 如需 GPU 加速，需安装 CUDA 编译版本（如通过 conda-forge）。

### 4.3 获取 CUDA 版本（如需 GPU）

```bash
# conda-forge 提供预编译的 CUDA 版本
conda install -c conda-forge llama-cpp-python

# 或指定 Python 版本升级以获得最新版
conda install python=3.10
conda install -c conda-forge "llama-cpp-python>=0.3.30"
```

---

## 5. 关键教训

1. **系统环境变量污染** — `CUDA_PATH` 被 PyCharm 错误设置，影响所有依赖 CUDA 的库
2. **多 Python 环境冲突** — cmd 和 Git Bash 可能使用不同的 Python，需用完整路径或激活环境
3. **CUDA 编译版 ≠ 需要 GPU** — 正确构建的版本可在 `n_gpu_layers=0` 时纯 CPU 运行；有 bug 的版本会在初始化阶段崩溃
4. **env var vs DLL search** — 仅清理 `CUDA_PATH` 不够，`llama.dll` 的依赖 DLL 可能通过其他路径加载

---

## 6. 相关文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `llm-agent/src/main.py` | 修改 | 环境变量清理增强 + OSError 专项处理 |
| `llm-agent/start.bat` | 修改 | 扩充 env var 清理 + 固定 Anaconda Python 路径 |
| `llm-agent/diagnose.py` | 新增 | 逐步诊断脚本 |
| `llm-agent/docs/llama-cpp-python-修复记录.md` | 新增 | 本文档 |
