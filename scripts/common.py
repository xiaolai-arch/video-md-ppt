"""video-md-ppt 公共工具：配置、工作区、状态机、子进程。

设计原则：这里只放确定性逻辑；任何需要判断的事情交给 Claude。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = ROOT / "config.toml"

STAGES = ("s0", "s1", "s2", "s3", "s4", "s5")
STAGE_LABELS = {
    "s0": "预处理",
    "s1": "转写",
    "s2": "抽帧",
    "s3": "大纲",
    "s4": "笔记",
    "s5": "课件",
}


class ToolError(RuntimeError):
    """可预期、可行动的错误（消息会直接展示给用户）。"""


def ensure_utf8_stdout() -> None:
    """Windows 控制台默认 GBK，避免中文/符号输出报错。"""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
        except Exception:
            pass


# ---------------------------------------------------------------------------
# 配置
# ---------------------------------------------------------------------------


def _strip_comment(line: str) -> str:
    out: list[str] = []
    quote = ""
    for ch in line:
        if quote:
            out.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            out.append(ch)
        elif ch == "#":
            break
        else:
            out.append(ch)
    return "".join(out).strip()


def _split_top_level(text: str) -> list[str]:
    parts: list[str] = []
    buf: list[str] = []
    quote = ""
    depth = 0
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = ""
        elif ch in "\"'":
            quote = ch
            buf.append(ch)
        elif ch in "[{":
            depth += 1
            buf.append(ch)
        elif ch in "]}":
            depth -= 1
            buf.append(ch)
        elif ch == "," and depth == 0:
            parts.append("".join(buf).strip())
            buf = []
        else:
            buf.append(ch)
    tail = "".join(buf).strip()
    if tail:
        parts.append(tail)
    return parts


def _parse_value(raw: str) -> Any:
    raw = raw.strip()
    if not raw:
        raise ValueError("配置值为空")
    if raw.startswith('"') and raw.endswith('"'):
        return json.loads(raw)
    if raw.startswith("'") and raw.endswith("'"):
        return raw[1:-1]
    low = raw.lower()
    if low == "true":
        return True
    if low == "false":
        return False
    if raw.startswith("[") and raw.endswith("]"):
        inner = raw[1:-1].strip()
        return [_parse_value(p) for p in _split_top_level(inner)] if inner else []
    try:
        return int(raw)
    except ValueError:
        pass
    try:
        return float(raw)
    except ValueError:
        pass
    return raw


def _mini_toml(text: str) -> dict:
    """极简 TOML 子集：节 + 标量 + 一维数组。

    仅作为 Python < 3.11 且未安装 tomli 时的兜底，覆盖本项目 config.toml 的用到的语法。
    """
    data: dict[str, Any] = {}
    section: dict[str, Any] = data
    for lineno, raw_line in enumerate(text.splitlines(), 1):
        line = _strip_comment(raw_line)
        if not line:
            continue
        if line.startswith("[") and line.endswith("]"):
            section = data
            for part in line[1:-1].strip().split("."):
                section = section.setdefault(part.strip(), {})
            continue
        if "=" not in line:
            raise ToolError(f"config.toml 第 {lineno} 行无法解析：{raw_line!r}")
        key, _, value = line.partition("=")
        key = key.strip().strip('"').strip("'")
        try:
            section[key] = _parse_value(value)
        except ValueError as exc:
            raise ToolError(f"config.toml 第 {lineno} 行解析失败：{exc}") from exc
    return data


def load_config(path: str | Path | None = None) -> dict:
    cfg_path = Path(path) if path else CONFIG_PATH
    if not cfg_path.exists():
        raise ToolError(f"找不到配置文件：{cfg_path}")
    text = cfg_path.read_text(encoding="utf-8")
    try:
        import tomllib  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        try:
            import tomli  # type: ignore[import-not-found]
        except ModuleNotFoundError:
            return _mini_toml(text)
        return tomli.loads(text)
    return tomllib.loads(text)


def cfg(conf: dict, dotted: str, default: Any = None) -> Any:
    cur: Any = conf
    for part in dotted.split("."):
        if not isinstance(cur, dict) or part not in cur:
            return default
        cur = cur[part]
    return cur


def path_cfg(conf: dict, dotted: str, default: str) -> Path:
    p = Path(str(cfg(conf, dotted, default))).expanduser()
    return p if p.is_absolute() else (ROOT / p)


def resolve_tool(value: str, hint: str) -> str:
    """把配置里的命令名/路径解析成可执行文件路径。"""
    if os.sep in value or "/" in value:
        p = Path(value).expanduser()
        if p.exists():
            return str(p)
        raise ToolError(f"找不到可执行文件：{value}（{hint}）")
    found = shutil.which(value)
    if not found:
        raise ToolError(f"找不到 {value}（{hint}）")
    return found


def prepare_cuda_dlls() -> tuple[bool, str]:
    """检查 CUDA 12 运行库是否可用；Windows 上把常见 DLL 目录加入搜索路径。

    ctranslate2 的 Windows wheel 不捆绑 cuBLAS/cuDNN，必须在系统或 site-packages
    里有 cublas64_12.dll 与 cudnn_ops64_9.dll，否则推理时才报错。
    """
    if sys.platform != "win32":
        try:
            import ctranslate2

            count = ctranslate2.get_cuda_device_count()
            return count > 0, f"CUDA device(s): {count}"
        except Exception as exc:
            return False, str(exc)

    dirs: list[str] = []
    try:
        import site

        for sp in site.getsitepackages():
            for sub in ("cublas", "cudnn"):
                candidate = Path(sp) / "nvidia" / sub / "bin"
                if candidate.exists():
                    dirs.append(str(candidate))
    except Exception:
        pass
    cuda_path = os.environ.get("CUDA_PATH")
    if cuda_path and (Path(cuda_path) / "bin").exists():
        dirs.append(str(Path(cuda_path) / "bin"))
    toolkit = Path(r"C:\Program Files\NVIDIA GPU Computing Toolkit\CUDA")
    if toolkit.exists():
        for version_dir in sorted(toolkit.glob("v12*")):
            if (version_dir / "bin").exists():
                dirs.append(str(version_dir / "bin"))

    for directory in dirs:
        try:
            os.add_dll_directory(directory)
        except Exception:
            pass
        os.environ["PATH"] = directory + os.pathsep + os.environ.get("PATH", "")

    try:
        import ctypes

        ctypes.WinDLL("cublas64_12.dll")
        ctypes.WinDLL("cudnn_ops64_9.dll")
    except OSError as exc:
        return False, f"缺少 CUDA 12 运行库：{exc}"

    try:
        import ctranslate2

        count = ctranslate2.get_cuda_device_count()
    except Exception as exc:
        return False, str(exc)
    if count <= 0:
        return False, "未检测到 CUDA 设备"
    return True, f"CUDA device(s): {count}"


# ---------------------------------------------------------------------------
# 路径 / 命名
# ---------------------------------------------------------------------------


def sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            block = fh.read(chunk)
            if not block:
                break
            h.update(block)
    return h.hexdigest()


def content_hash(path: Path, sample: int = 1 << 20) -> str:
    """大文件不必全量哈希：size + 头 + 尾就足以区分视频。"""
    size = path.stat().st_size
    h = hashlib.sha256(str(size).encode())
    with path.open("rb") as fh:
        h.update(fh.read(sample))
        if size > sample * 2:
            fh.seek(-sample, os.SEEK_END)
            h.update(fh.read(sample))
    return h.hexdigest()[:8]


def safe_stem(name: str, limit: int = 40) -> str:
    stem = Path(name).stem
    stem = re.sub(r"[^\w\-]+", "_", stem, flags=re.UNICODE).strip("._-")
    return (stem or "video")[:limit]


def make_slug(video: Path) -> str:
    return f"{safe_stem(video.name)}_{content_hash(video)}"


def fmt_duration(seconds: float | None) -> str:
    if seconds is None:
        return "?"
    total = int(round(seconds))
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    return f"{h:02d}:{m:02d}:{s:02d}" if h else f"{m:02d}:{s:02d}"


def _now() -> str:
    return datetime.now().astimezone().isoformat(timespec="seconds")


# ---------------------------------------------------------------------------
# 状态机：work/<slug>/meta.json
# ---------------------------------------------------------------------------


def _file_record(path: Path, base: Path) -> dict:
    try:
        rel = path.resolve().relative_to(base.resolve())
    except ValueError:
        rel = path
    return {
        "path": str(rel).replace("\\", "/"),
        "bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


class Meta:
    """每个视频一个 meta.json，记录各阶段状态与产物校验和。"""

    def __init__(self, path: Path):
        self.path = Path(path)
        self.data: dict[str, Any] = {}
        if self.path.exists():
            try:
                self.data = json.loads(self.path.read_text(encoding="utf-8"))
            except json.JSONDecodeError as exc:
                raise ToolError(f"meta.json 损坏：{self.path}（{exc}）") from exc
        self.data.setdefault("schema", 1)
        self.data.setdefault("stages", {})
        for name in STAGES:
            self.data["stages"].setdefault(name, {"status": "pending"})

    def save(self) -> None:
        self.data["updated_at"] = _now()
        tmp = self.path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(tmp, self.path)

    # -- 查询 ---------------------------------------------------------------
    def stage(self, name: str) -> dict:
        return self.data["stages"].setdefault(name, {"status": "pending"})

    def status(self, name: str) -> str:
        return str(self.stage(name).get("status", "pending"))

    def is_done(self, name: str) -> bool:
        return self.status(name) == "done"

    def error(self, name: str) -> str | None:
        return self.stage(name).get("error")

    # -- 变更 ---------------------------------------------------------------
    def mark_running(self, name: str) -> None:
        st = self.stage(name)
        st.update(
            status="running",
            started_at=_now(),
            started_epoch=time.time(),
            attempts=int(st.get("attempts", 0)) + 1,
        )
        st.pop("error", None)
        st.pop("finished_at", None)
        self.save()

    def mark_done(
        self,
        name: str,
        outputs: Sequence[Path] = (),
        params: dict | None = None,
        base_dir: Path | None = None,
    ) -> None:
        st = self.stage(name)
        started = st.get("started_epoch")
        st.update(
            status="done",
            finished_at=_now(),
            duration_s=round(time.time() - started, 1) if started else None,
            params=params or {},
        )
        if base_dir is not None:
            st["outputs"] = [
                _file_record(Path(p), Path(base_dir)) for p in outputs if Path(p).is_file()
            ]
        st.pop("error", None)
        self.save()

    def mark_failed(self, name: str, error: str) -> None:
        st = self.stage(name)
        st.update(status="failed", finished_at=_now(), error=str(error))
        self.save()


# ---------------------------------------------------------------------------
# 工作区定位
# ---------------------------------------------------------------------------


def resolve_workspace(target: str, conf: dict) -> tuple[str, Path, "Meta | None", Path]:
    """接受视频路径或 slug，返回 (slug, work_dir, meta 或 None, 源视频路径)。"""
    work_root = path_cfg(conf, "paths.work", "work")
    candidate = Path(target).expanduser()
    if candidate.exists():
        src = candidate.resolve()
        if not src.is_file():
            raise ToolError(f"不是文件：{src}")
        slug = make_slug(src)
        work_dir = work_root / slug
        meta_path = work_dir / "meta.json"
        meta = Meta(meta_path) if meta_path.exists() else None
        return slug, work_dir, meta, src

    meta_path = work_root / target / "meta.json"
    if not meta_path.exists():
        raise ToolError(f"找不到工作区或视频：{target}（先运行 scripts/probe.py）")
    meta = Meta(meta_path)
    source_path = (meta.data.get("source") or {}).get("path")
    if not source_path:
        raise ToolError(f"meta.json 缺少源视频路径：{meta_path}")
    src = Path(source_path)
    if not src.exists():
        raise ToolError(f"源视频不存在：{src}")
    return target, meta_path.parent, meta, src


# ---------------------------------------------------------------------------
# 子进程
# ---------------------------------------------------------------------------


def run(
    cmd: Sequence[Any],
    *,
    log_path: Path | None = None,
    timeout: float | None = None,
) -> subprocess.CompletedProcess:
    """执行命令，失败时抛出带 stderr 尾部信息的 ToolError。"""
    args = [str(c) for c in cmd]
    started = time.time()
    try:
        proc = subprocess.run(
            args,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise ToolError(f"无法执行 {args[0]}：命令不存在") from exc
    except subprocess.TimeoutExpired as exc:
        raise ToolError(f"命令超时（>{timeout}s）：{args[0]}") from exc

    if log_path is not None:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with log_path.open("a", encoding="utf-8") as fh:
            fh.write(f"\n$ {' '.join(args)}\n# exit={proc.returncode}  {time.time() - started:.1f}s\n")
            if proc.stdout:
                fh.write(proc.stdout.rstrip() + "\n")
            if proc.stderr:
                fh.write(proc.stderr.rstrip() + "\n")

    if proc.returncode != 0:
        tail = (proc.stderr or proc.stdout or "").strip().splitlines()[-8:]
        raise ToolError(
            f"命令失败（exit {proc.returncode}）：{args[0]}\n" + "\n".join(tail)
        )
    return proc


def ffprobe(ffprobe_bin: str, src: Path) -> dict:
    proc = run(
        [
            ffprobe_bin,
            "-v",
            "error",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            str(src),
        ]
    )
    try:
        return json.loads(proc.stdout or "{}")
    except json.JSONDecodeError as exc:
        raise ToolError(f"ffprobe 输出无法解析：{exc}") from exc


def _fps(stream: dict) -> float | None:
    for key in ("avg_frame_rate", "r_frame_rate"):
        value = stream.get(key)
        if not value or value in ("0/0", "N/A"):
            continue
        try:
            num, den = value.split("/")
            if float(den) == 0:
                continue
            return round(float(num) / float(den), 2)
        except (ValueError, AttributeError):
            continue
    return None


def summarize_probe(data: dict) -> dict:
    fmt = data.get("format") or {}
    streams = data.get("streams") or []
    video = next((s for s in streams if s.get("codec_type") == "video"), None)
    audio = next((s for s in streams if s.get("codec_type") == "audio"), None)

    duration: float | None = None
    for candidate in (fmt.get("duration"), (video or {}).get("duration"), (audio or {}).get("duration")):
        try:
            duration = float(candidate)
            break
        except (TypeError, ValueError):
            continue

    info: dict[str, Any] = {
        "duration_s": duration,
        "format": fmt.get("format_name"),
        "size_bytes": int(fmt.get("size") or 0),
        "bit_rate": int(fmt.get("bit_rate") or 0) or None,
        "has_audio": audio is not None,
        "video": None,
        "audio": None,
    }
    if video is not None:
        info["video"] = {
            "codec": video.get("codec_name"),
            "width": video.get("width"),
            "height": video.get("height"),
            "fps": _fps(video),
            "pix_fmt": video.get("pix_fmt"),
        }
    if audio is not None:
        info["audio"] = {
            "codec": audio.get("codec_name"),
            "channels": audio.get("channels"),
            "sample_rate": int(audio.get("sample_rate") or 0) or None,
            "language": (audio.get("tags") or {}).get("language"),
        }
    return info
