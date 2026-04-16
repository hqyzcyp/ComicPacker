#!/bin/bash
# ComicPacker Web Server 启动脚本

echo "======================================"
echo "ComicPacker Web 服务器启动脚本"
echo "======================================"
echo ""

PYTHON=""
PYTHON_DESC=""
WEB_WORKERS_DEFAULT=""

detect_cpu_count() {
    local cpu_count=""

    if command -v getconf >/dev/null 2>&1; then
        cpu_count="$(getconf _NPROCESSORS_ONLN 2>/dev/null || true)"
    fi

    if [ -z "$cpu_count" ] && command -v nproc >/dev/null 2>&1; then
        cpu_count="$(nproc 2>/dev/null || true)"
    fi

    if ! [[ "$cpu_count" =~ ^[0-9]+$ ]] || [ "$cpu_count" -lt 1 ]; then
        cpu_count=1
    fi

    echo "$cpu_count"
}

get_default_web_worker_count() {
    local cpu_count
    cpu_count="$(detect_cpu_count)"

    if [ "$cpu_count" -gt 4 ]; then
        echo "4"
    else
        echo "$cpu_count"
    fi
}

configure_web_workers() {
    WEB_WORKERS_DEFAULT="$(get_default_web_worker_count)"

    if [ -z "${COMICPACKER_WEB_WORKERS:-}" ]; then
        export COMICPACKER_WEB_WORKERS="$WEB_WORKERS_DEFAULT"
        echo "✓ 未设置 COMICPACKER_WEB_WORKERS，使用默认值: $COMICPACKER_WEB_WORKERS"
        return 0
    fi

    if [[ "${COMICPACKER_WEB_WORKERS}" =~ ^[1-9][0-9]*$ ]]; then
        echo "✓ 使用已设置的 COMICPACKER_WEB_WORKERS=$COMICPACKER_WEB_WORKERS"
        return 0
    fi

    echo "⚠ COMICPACKER_WEB_WORKERS=${COMICPACKER_WEB_WORKERS} 无效，回退到默认值: $WEB_WORKERS_DEFAULT"
    export COMICPACKER_WEB_WORKERS="$WEB_WORKERS_DEFAULT"
}

list_conda_envs() {
    conda info --envs 2>/dev/null | awk '
        /^#/ || NF == 0 { next }
        {
            path = $NF
            name = $1

            if (name == "*" || name == "+") {
                name = $2
            } else {
                sub(/^[*+]+/, "", name)
            }

            if (name != "" && path != "") {
                print name "|" path
            }
        }
    '
}

find_conda_env_by_name() {
    local target_name="$1"
    local env_name env_path

    while IFS='|' read -r env_name env_path; do
        [ -z "$env_name" ] && continue
        if [ "$env_name" = "$target_name" ]; then
            echo "$env_name|$env_path"
            return 0
        fi
    done < <(list_conda_envs)

    return 1
}

activate_conda_env() {
    local env_ref="$1"
    local env_label="$2"
    local conda_base conda_sh

    conda_base="$(conda info --base 2>/dev/null)" || return 1
    conda_sh="$conda_base/etc/profile.d/conda.sh"

    if [ ! -f "$conda_sh" ]; then
        return 1
    fi

    # shellcheck disable=SC1090
    source "$conda_sh"

    if conda activate "$env_ref" >/dev/null 2>&1; then
        PYTHON="python"
        PYTHON_DESC="conda 环境: $env_label"
        return 0
    fi

    return 1
}

conda_env_has_flask() {
    local env_path="$1"
    conda run -p "$env_path" python -c "import flask" >/dev/null 2>&1
}

try_conda_environment() {
    local env_record env_name env_path

    if ! command -v conda >/dev/null 2>&1; then
        return 1
    fi

    echo "检测到 conda，尝试查找可用环境..."

    env_record="$(find_conda_env_by_name "comic")"
    if [ -n "$env_record" ]; then
        IFS='|' read -r env_name env_path <<< "$env_record"
        echo "✓ 检测到 conda 环境 comic，优先使用"
        if activate_conda_env "$env_path" "$env_name"; then
            return 0
        fi
        echo "⚠ conda 环境 comic 激活失败，继续检查其他 conda 环境"
    else
        echo "⚠ 未找到 conda 环境 comic，开始检查其他 conda 环境"
    fi

    if [ -n "${CONDA_DEFAULT_ENV:-}" ] && [ "${CONDA_DEFAULT_ENV}" != "comic" ]; then
        env_record="$(find_conda_env_by_name "${CONDA_DEFAULT_ENV}")"
        if [ -n "$env_record" ]; then
            IFS='|' read -r env_name env_path <<< "$env_record"
            echo "✓ 当前 shell 已激活 conda 环境 ${env_name}，尝试直接使用"
            if activate_conda_env "$env_path" "$env_name"; then
                return 0
            fi
            echo "⚠ 当前 conda 环境 ${env_name} 激活失败，继续检查其他 conda 环境"
        fi
    fi

    while IFS='|' read -r env_name env_path; do
        [ -z "$env_name" ] && continue
        [ "$env_name" = "comic" ] && continue
        [ -n "${CONDA_DEFAULT_ENV:-}" ] && [ "$env_name" = "${CONDA_DEFAULT_ENV}" ] && continue

        echo "检查 conda 环境: $env_name"
        if conda_env_has_flask "$env_path"; then
            echo "✓ 在 conda 环境 $env_name 中检测到 Flask，使用该环境"
            if activate_conda_env "$env_path" "$env_name"; then
                return 0
            fi
            echo "⚠ conda 环境 $env_name 激活失败，继续检查"
        else
            echo "⚠ conda 环境 $env_name 未检测到 Flask，跳过"
        fi
    done < <(list_conda_envs)

    return 1
}

# 检查 Python 环境
if try_conda_environment; then
    echo "✓ 使用 ${PYTHON_DESC}"
elif [ -x ".venv/bin/python" ]; then
    echo "✓ 找到项目虚拟环境 .venv"
    # shellcheck disable=SC1091
    source .venv/bin/activate
    PYTHON="python"
    PYTHON_DESC="项目虚拟环境 .venv"
else
    echo "⚠ 未找到可用的 conda/.venv 环境，使用系统 Python"
    if command -v python3 >/dev/null 2>&1; then
        PYTHON="python3"
    else
        PYTHON="python"
    fi
    PYTHON_DESC="系统 Python"
fi

echo "当前 Python 来源: $PYTHON_DESC"
$PYTHON --version 2>/dev/null || true

# 检查依赖
echo "检查依赖..."
$PYTHON -c "import flask" 2>/dev/null
if [ $? -ne 0 ]; then
    echo "✗ Flask未安装，正在安装依赖..."
    $PYTHON -m pip install -r requirements.txt
else
    echo "✓ 依赖已安装"
fi

echo ""
echo "启动Web服务器..."
echo "访问地址: http://localhost:5000"
echo "按 Ctrl+C 停止服务器"
echo ""

# 设置 PYTHONPATH 以确保 KCC 脚本能找到模块
export PYTHONPATH="${PYTHONPATH:+$PYTHONPATH:}$(pwd)"

# 自动配置 Web 后台 worker 数
configure_web_workers
echo "后台 worker 数: $COMICPACKER_WEB_WORKERS"

# 启动服务器
$PYTHON web_server.py
