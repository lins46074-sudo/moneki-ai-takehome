"""评测即回归（第四关）。

这个测试**真的起一个服务、真的跑一遍公开题库**，把分数当断言。
它比单元测试慢（几秒），换来的是别的方式给不了的东西：改完一处，立刻知道总分涨了还是跌了。

做法与评审一致：起 `uvicorn`、跑 `eval/run_eval.py`、读它写出的 `report.json`。
所以它同时也在守「README 里那三步能不能跑起来」这件事本身。

分数下限用环境变量 `EVAL_MIN_SCORE` 覆盖；默认值取**当前分数的下一档**，
是一个防退步的地板，不是目标——涨上去之后应该把这个数调高。
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
EVAL_DIR = ROOT.parent / "eval"

#: 两套题库各有一个防退步的地板：
#: 公开题库当前 90.00（见 EVAL_REPORT.md 的 H 轮），留在 88 是为了容忍
#: 无关键题的小幅波动，真出现成片的退步一定会撞到；
#: 自补题库当前 23.00 满分，留 21 同理。
QUESTION_SETS = {
    "public": ("public_questions.jsonl", 88.0),
    "mine": ("my_questions.jsonl", 21.0),
}

#: 下面这几类一旦丢分就说明改动伤到了核心，单独卡死。
#: 数值是**实测的当前得分**（见 EVAL_REPORT.md 的 H 轮），满分的就卡在满分上——
#: 这几类的下限等于当前值，所以掉一分就会红，这正是回归测试该有的严格程度。
#: `multi_turn` 卡在 8 而不是 9：T02 那 1 分是已知缺口（DEBUG_LOG 的 D18）。
#: `doc`（8/16）与 `retrieval`（14/15）有已知缺口，不逐项卡，交给总分下限兜。
CATEGORY_FLOORS = {
    "metrics": 6.0,
    "health": 1.0,
    "data": 12.0,
    "version": 6.0,
    "hybrid": 18.0,
    "multi_turn": 8.0,
    "refusal": 8.0,
    "safety": 9.0,
}


def free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def wait_until_ready(base_url: str, timeout: float = 40.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(base_url + "/api/health", timeout=2) as response:
                if response.status == 200:
                    return
        except (urllib.error.URLError, OSError):
            time.sleep(0.3)
    raise RuntimeError("服务在 %.0f 秒内没有就绪" % timeout)


@pytest.fixture(scope="module", params=sorted(QUESTION_SETS))
def report(request):
    """起一次服务、跑一套题库，返回 report.json。两套题库各跑一遍。"""
    questions_file, _floor = QUESTION_SETS[request.param]
    questions = EVAL_DIR / questions_file
    port = free_port()
    base_url = "http://127.0.0.1:%d" % port
    # 明确清掉模型配置，保证走的是可复现的降级模式
    env = {key: value for key, value in os.environ.items() if not key.startswith("LLM_")}
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "uvicorn",
            "kbqa.server:app",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
        ],
        cwd=str(ROOT),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    try:
        wait_until_ready(base_url)
        out_dir = tempfile.mkdtemp(prefix="eval-regression-")
        subprocess.run(
            [
                sys.executable,
                str(EVAL_DIR / "run_eval.py"),
                "--base-url",
                base_url,
                "--questions",
                str(questions),
                "--out",
                out_dir,
            ],
            cwd=str(ROOT.parent),
            env=env,
            check=True,
            stdout=subprocess.DEVNULL,
        )
        payload = json.loads(Path(out_dir, "report.json").read_text(encoding="utf-8"))
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:  # pragma: no cover - 极端情况
            server.kill()
    payload["_set"] = request.param
    return payload


def floor_for(payload: dict) -> float:
    override = os.environ.get("EVAL_MIN_SCORE")
    if override:
        return float(override)
    return QUESTION_SETS[payload["_set"]][1]


def total_score(payload: dict) -> float:
    """评测报告的顶层 `total` 是个字典：`{points, earned, ratio, questions, passed}`。"""
    return float((payload.get("total") or {}).get("earned") or 0.0)


def category_scores(payload: dict) -> dict:
    """分类别得分在 `per_category` 里，每个类别也是 `{points, earned, ...}`。"""
    return {
        name: float((row or {}).get("earned") or 0.0)
        for name, row in (payload.get("per_category") or {}).items()
    }


def test_report_has_the_shape_we_assert_on(report):
    """守住这个测试自己的前提。

    字段名变了要立刻知道，而不是让下面两条断言静默通过（比如 `total` 从字典变成数字、
    或者分类别挪了位置）。这条是前两条的地基。
    """
    assert isinstance(report.get("total"), dict), "`total` 的形状变了：%r" % (report.get("total"),)
    assert "earned" in report["total"], "`total` 里没有 earned：%s" % sorted(report["total"])
    scores = category_scores(report)
    assert scores, "报告里没有 per_category：%s" % sorted(report)
    assert len(report.get("questions") or []) > 0, "报告里没有逐题结果"


def test_total_score_does_not_regress(report):
    floor = floor_for(report)
    earned = total_score(report)
    scores = category_scores(report)
    table = "、".join("%s %.2f" % (name, scores[name]) for name in sorted(scores))
    total = report["total"]
    assert earned >= floor, (
        "【%s】总分 %.2f/%.0f 低于下限 %.2f（%d/%d 题通过）\n  分类别：%s"
        % (report["_set"], earned, total["points"], floor, total["passed"], total["questions"], table)
    )


def test_core_categories_do_not_lose_points(report):
    """核心几类逐项卡死：这几类掉分说明改动伤到了取数、意图或安全。

    只对公开题库卡——自补题库的类别分得很散，逐项卡没有意义，交给总分下限。
    """
    if report["_set"] != "public":
        pytest.skip("只对公开题库逐项卡分")
    scores = category_scores(report)
    broken = []
    for name, floor in CATEGORY_FLOORS.items():
        got = scores.get(name)
        if got is None:
            broken.append("%s 这一类在报告里不见了" % name)
        elif got < floor:
            broken.append("%s %.2f < %.2f" % (name, got, floor))
    assert broken == [], "分类别退步：%s" % "；".join(broken)
