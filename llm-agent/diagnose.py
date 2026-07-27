"""
诊断脚本：检测 llama-cpp-python 在 cmd 环境下崩溃的原因。
请在 cmd 中运行: python diagnose.py
"""
import os, sys

print("=" * 60)
print("  llama-cpp-python 环境诊断")
print("=" * 60)

# 1. Python 信息
print(f"\n[1] Python 路径: {sys.executable}")
print(f"    Python 版本: {sys.version}")

# 2. 当前 CUDA 环境变量
print("\n[2] CUDA/NVIDIA 环境变量（清理前）:")
for k, v in sorted(os.environ.items()):
    ku = k.upper()
    if any(kw in ku for kw in ('CUDA', 'NVIDIA', 'NVCC', 'GPU', 'NVTOOL')):
        print(f"    {k} = {v}")

# 3. PATH 中的 CUDA 条目
print("\n[3] PATH 中的 CUDA/NVIDIA 条目:")
for entry in os.environ.get('PATH', '').split(os.pathsep):
    el = entry.lower()
    if any(kw in el for kw in ('cuda', 'nvidia', 'nvcc', 'cublas', 'libnvvp', 'nsight')):
        print(f"    {entry}")

# 4. 执行与 main.py 相同的清理
print("\n[4] 执行环境变量清理...")
cleaned = []
for var in list(os.environ.keys()):
    upper = var.upper()
    if any(kw in upper for kw in (
        'CUDA_PATH', 'CUDA_HOME', 'CUDA_TOOLKIT', 'CUDA_MODULE',
        'CUDA_CACHE', 'CUDA_VISIBLE', 'CUDA_VERSION',
        'NVCC', 'NVIDIA_DRIVER', 'NVTOOLSEXT',
        'NVCUDASAMPLES', 'GPU_', 'GGML_CUDA',
    )):
        cleaned.append(f"{var}={os.environ.pop(var)}")

if 'PATH' in os.environ:
    old = os.environ['PATH']
    new = []
    for e in old.split(os.pathsep):
        el = e.lower()
        if any(kw in el for kw in (
            'cuda', 'nvcc', 'cublas', 'cudnn',
            'nvidia corp', 'nvidia gpu', 'libnvvp', 'nsight',
        )):
            cleaned.append(f"PATH: {e}")
        else:
            new.append(e)
    if len(new) != len(old.split(os.pathsep)):
        os.environ['PATH'] = os.pathsep.join(new)

print(f"    清理了 {len(cleaned)} 个项目:")
for c in cleaned:
    print(f"      - {c}")

# 5. 验证清理结果
print("\n[5] 清理后残留的 CUDA 变量:")
remaining = []
for k, v in sorted(os.environ.items()):
    ku = k.upper()
    if any(kw in ku for kw in ('CUDA', 'NVIDIA', 'NVCC', 'GPU', 'NVTOOL')):
        remaining.append(f"    {k} = {v}")
if remaining:
    for r in remaining:
        print(r)
else:
    print("    (无残留)")

# 6. 尝试导入
print("\n[6] 导入 llama_cpp...")
try:
    import llama_cpp
    from llama_cpp import Llama
    import llama_cpp.llama_cpp as ll
    print(f"    导入成功 (版本: {llama_cpp.__version__})")
    print(f"    DLL 路径: {llama_cpp.__file__}")
except Exception as e:
    print(f"    导入失败: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# 7. 尝试 llama_backend_init
print("\n[7] 调用 llama_backend_init()...")
try:
    ll.llama_backend_init()
    print("    成功!")
    ll.llama_backend_free()
except OSError as e:
    print(f"    OSError: {e}")
    print("    >>> 崩溃点确认: llama_backend_init() 空指针 <<<")
    sys.exit(1)
except Exception as e:
    print(f"    异常: {e}")
    sys.exit(1)

# 8. 尝试加载模型
print("\n[8] 加载模型...")
model_path = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "models", "Qwen2.5-7B-Instruct-Q4_K_M.gguf"
)
print(f"    模型路径: {model_path}")
print(f"    文件存在: {os.path.exists(model_path)}")
if os.path.exists(model_path):
    size_gb = os.path.getsize(model_path) / (1024**3)
    print(f"    文件大小: {size_gb:.2f} GB")

try:
    llm = Llama(
        model_path=model_path,
        n_ctx=512,
        n_threads=4,
        verbose=False,
    )
    print("    模型加载成功!")
    del llm
except OSError as e:
    print(f"    OSError: {e}")
    print("    >>> 崩溃点确认: Llama() 构造时崩溃 <<<")
    sys.exit(1)
except Exception as e:
    print(f"    异常: {type(e).__name__}: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("  诊断完成：一切正常！")
print("=" * 60)
