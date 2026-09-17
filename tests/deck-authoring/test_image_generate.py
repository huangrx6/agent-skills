#!/usr/bin/env python3
"""生图后端（`--generate`）的验证：契约驱动、配了就直连、没配就说清手动怎么走。

提示词一路生成到契约里（`--brief`），出图这一步多了一条路：

    配了后端（`--provider-cmd`，或 `MINIMAX_API_KEY` / `MINIMAX_CN_API_KEY`）
        → 按契约里**填好的**提示词直接出图；
    没配
        → 一步都不跑，一次说清两条路（手动出图放哪个目录、或配哪个变量）。

要钉的是四件事：

1. **只读契约**：出图不许把契约重写回模板 —— 否则人填好的提示词会被占位符覆盖，
   而且"发出去的提示词"与"契约里的提示词"会变成两条（本文件逐字比对）。
2. **没填就阻塞**：中英两种占位符都拦，且报错要指明**改哪个文件**。把模板发给
   模型也能出图，但那是花真钱买一张模板画。
3. **没配就一次说清**，不是循环里每张抛一次；报错文本里要有手动路径与 `--check`。
4. **不重复付费**：已存在的图不覆盖、同一提示词重跑命中缓存。

所有 HTTP 都换成本地假服务器（127.0.0.1 随机端口）——测试不出外网、不花钱。
子进程环境里**显式摘掉**真密钥（含 `MINIMAX_CN_API_KEY`）：机器上真配了也不能被
测试拿去用。

跑法：
    python3 -m unittest discover -s tests -v
    python3 tests/deck-authoring/test_image_generate.py
"""

from __future__ import annotations

import http.server
import io
import json
import os
import shutil
import socketserver
import subprocess
import sys
import tempfile
import threading
import unittest
from collections.abc import Iterator
from contextlib import contextmanager

from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
SKILL = os.path.join(os.path.dirname(os.path.dirname(HERE)), "skills", os.path.basename(HERE))
FIXTURES_DIR = os.path.join(HERE, "fixtures")
SCRIPTS = os.path.join(SKILL, "scripts")
IMAGE_SOURCE = os.path.join(SCRIPTS, "image_source.py")
DEMO = os.path.join(FIXTURES_DIR, "demo.spec.json")
# 能从环境里溜进来的东西 —— 测试一个都不留（含本机真配了的密钥）。
# 缓存目录不在这个名单里：`_run` 每次都把它**显式**写成用例自己的目录，
# 若在这里先 pop 再写，就会把刚写进去的值又抹掉（曾经就是这么掉到用户真缓存上的）。
KEY_VARS = ("MINIMAX_API_KEY", "MINIMAX_CN_API_KEY", "MINIMAX_API_HOST",
            "MINIMAX_IMAGE_MODEL")


def _png(w: int = 1536, h: int = 1024, color: tuple[int, int, int] = (150, 140, 130)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


@contextmanager
def _fake_api(blob: bytes | None = None) -> Iterator[tuple[str, list[dict]]]:
    """本地假 MiniMax：POST 收请求、GET 交出 PNG 字节。

    验收点是"发出去的请求对不对、回来的字节有没有落盘" —— 不该拿真 API 验（既花钱
    又不确定，还把测试变成网络依赖）。假服务器把**发出去的东西**原样记下来给断言看。
    """
    seen: list[dict] = []
    payload = _png() if blob is None else blob

    class Handler(http.server.BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: object) -> None:  # noqa: A002 (基类签名)
            pass                      # 访问日志不进测试输出

        def _send(self, body: bytes, ctype: str) -> None:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_POST(self) -> None:
            raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
            seen.append({"path": self.path,
                         "auth": self.headers.get("Authorization", ""),
                         "body": json.loads(raw or b"{}"),
                         "blob": raw})
            # 回给客户端的 URL 用请求里的 Host：这就是它自己那个地址
            url = f"http://{self.headers.get('Host', '')}/img.png"
            self._send(json.dumps({"data": {"image_urls": [url]}}).encode(),
                       "application/json")

        def do_GET(self) -> None:
            self._send(payload, "image/png")

    server = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}", seen
    finally:
        server.shutdown()
        server.server_close()


def _deck(tmp: str) -> tuple[str, str]:
    """一个最小 deck 项目：spec（带一个图槽位）+ 它自己带的风格与品牌。

    风格与品牌走夹具（`DECK_STYLES` / `DECK_BRANDS` 指到 tests/ 下）：工具链不内置
    任何风格，可拷贝的模板必然变成默认答案。
    """
    with open(DEMO, encoding="utf-8") as fh:
        spec = json.load(fh)
    path = os.path.join(tmp, "deck-spec.json")
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(spec, fh, ensure_ascii=False)
    return path, next(s["image"] for s in spec["deck"]["slides"] if s.get("image"))


def _contract(tmp: str, image: str, prompt: str, aspect: float | None = 1.5) -> str:
    """手写一份 `--brief` 会写出的契约（形状同上，字段一个不多一个不少）。

    手写是为了跳过"渲染量槽位"那一步：这里要测的是出图，不是量槽位。
    """
    path = os.path.join(tmp, "assets", "requests", f"{image}.json")
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump({"schemaVersion": 1, "slide": [3], "role": "content-image",
                   "aspect": aspect, "focal": "",
                   "negative_space": "文字不压在图上，图内不必为文字留白",
                   "prompt": prompt, "required": True, "note": "实测槽位 583×388px"},
                  fh, ensure_ascii=False)
    return path


def _run(spec: str, env_extra: dict, *args: str) -> subprocess.CompletedProcess:
    env = {**os.environ,
           "DECK_STYLES": os.path.join(FIXTURES_DIR, "styles"),
           "DECK_BRANDS": os.path.join(FIXTURES_DIR, "brands"),
           # 缓存圈在本次用例自己的目录里：一是不去写用户真实缓存，二是用例之间
           # 不通过缓存互相干扰（同一提示词“命中缓存”会让“发了请求”的断言假失败）。
           "AGENT_SKILLS_CACHE_DIR": os.path.join(os.path.dirname(spec), "cache")}
    for name in KEY_VARS:
        env.pop(name, None)
    env.update(env_extra)
    return subprocess.run([sys.executable, IMAGE_SOURCE, "--generate", spec, *args],
                          capture_output=True, text=True, env=env, timeout=300)


FILLED = "editorial photo of one matte ceramic kettle on a concrete counter, soft window light"


class TestNoBackend(unittest.TestCase):
    """没配后端时**一步都不跑**，但要一次说清两条路。"""

    def test_says_both_ways_and_writes_nothing(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            spec, image = _deck(tmp)
            _contract(tmp, image, FILLED)
            done = _run(spec, {})
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            out = done.stdout + done.stderr
            # 手动这条路：契约 md + 放哪 + 回来怎么验
            self.assertIn("image-brief.md", out)
            self.assertIn(tmp, out)
            self.assertIn("--check", out)
            # 直连这条路：配哪个变量
            self.assertIn("MINIMAX_API_KEY", out)
            self.assertFalse(os.path.isfile(os.path.join(tmp, image)),
                             "没配后端却写出了图")

    def test_no_backend_never_touches_the_network(self) -> None:
        """连不上也报不对：没配后端时根本不该发请求。"""
        with tempfile.TemporaryDirectory() as tmp, _fake_api() as (host, seen):
            spec, image = _deck(tmp)
            _contract(tmp, image, FILLED)
            _run(spec, {"MINIMAX_API_HOST": host})       # 有 host、没密钥
            self.assertEqual(seen, [], "没密钥却发了请求")


class TestUnfilledPromptBlocks(unittest.TestCase):
    """没填的模板不许发出去：发出去就是花真钱买一张模板画。"""

    def _blocked(self, prompt: str) -> tuple[subprocess.CompletedProcess, list[dict], str]:
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        spec, image = _deck(tmp)
        req = _contract(tmp, image, prompt)
        with _fake_api() as (host, seen):
            done = _run(spec, {"MINIMAX_API_KEY": "test-key", "MINIMAX_API_HOST": host})
        return done, seen, req

    def test_chinese_placeholder_is_blocked(self) -> None:
        done, seen, _ = self._blocked("主体：〈写：是什么、几个、主要特征〉")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("还没填", done.stdout + done.stderr)
        self.assertEqual(seen, [], "占位符提示词被发出去了")

    def test_english_placeholder_is_blocked(self) -> None:
        """英文模板的占位符是 `<…>` 而不是 `〈…〉` —— 只拦一种就等于漏一半。"""
        done, seen, _ = self._blocked("subject: <what it is / key features>")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertIn("还没填", done.stdout + done.stderr)
        self.assertEqual(seen, [], "英文占位符提示词被发出去了")

    def test_error_names_the_file_to_edit(self) -> None:
        """报错要能直接照着改：给出**那个文件**的相对路径。"""
        done, _seen, req = self._blocked("〈写：主体〉")
        self.assertIn(os.path.relpath(req), done.stdout + done.stderr)

    def test_empty_prompt_is_blocked(self) -> None:
        done, seen, _ = self._blocked("   ")
        self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
        self.assertEqual(seen, [])

    def test_a_filled_prompt_is_not_blocked(self) -> None:
        """反面对照：填好了就得放行 —— 门不许把正常输入也拦下。"""
        tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, tmp, ignore_errors=True)
        spec, image = _deck(tmp)
        _contract(tmp, image, FILLED)
        with _fake_api() as (host, seen):
            done = _run(spec, {"MINIMAX_API_KEY": "test-key", "MINIMAX_API_HOST": host})
        self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
        self.assertEqual(len(seen), 1)


class TestGenerateFromContract(unittest.TestCase):
    """配好了就从契约出图：发出去的东西与落盘的字节都要对。"""

    def test_prompt_is_sent_verbatim_and_image_lands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _fake_api() as (host, seen):
            spec, image = _deck(tmp)
            _contract(tmp, image, FILLED)
            done = _run(spec, {"MINIMAX_API_KEY": "test-key", "MINIMAX_API_HOST": host})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)

            self.assertEqual(len(seen), 1, f"应只调一次：{seen}")
            call = seen[0]
            self.assertEqual(call["path"], "/v1/image_generation")
            self.assertEqual(call["auth"], "Bearer test-key")
            body = call["body"]
            # 契约里的提示词**逐字**发出去：这是"契约就是合同"的全部意义
            self.assertEqual(body["prompt"], FILLED)
            self.assertEqual(body["model"], "image-01")
            self.assertEqual(body["aspect_ratio"], "3:2")     # 契约的 1.5 → 官方档
            self.assertEqual(body["n"], 1)

            # 落盘：契约里那个文件名、真能解码的字节
            out = os.path.join(tmp, image)
            self.assertTrue(os.path.isfile(out), sorted(os.listdir(tmp)))
            with Image.open(out) as im:
                self.assertEqual(im.size, (1536, 1024))

    def test_contract_is_not_rewritten(self) -> None:
        """跑一次出图不许把契约覆盖回模板 —— 那是人填过的东西。"""
        with tempfile.TemporaryDirectory() as tmp, _fake_api() as (host, _seen):
            spec, image = _deck(tmp)
            req = _contract(tmp, image, FILLED)
            with open(req, encoding="utf-8") as fh:
                before = fh.read()
            _run(spec, {"MINIMAX_API_KEY": "test-key", "MINIMAX_API_HOST": host})
            with open(req, encoding="utf-8") as fh:
                self.assertEqual(fh.read(), before, "契约被出图这一步改写了")

    def test_ratio_is_mapped_to_the_nearest_official_step(self) -> None:
        """比例是**实测槽位**算出来的，落到官方八档里最近的一档。"""
        with tempfile.TemporaryDirectory() as tmp, _fake_api() as (host, seen):
            spec, image = _deck(tmp)
            _contract(tmp, image, FILLED, aspect=1.78)      # 接近 16:9
            _run(spec, {"MINIMAX_API_KEY": "test-key", "MINIMAX_API_HOST": host})
            self.assertEqual(seen[0]["body"]["aspect_ratio"], "16:9")

    def test_missing_contract_says_run_brief(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _fake_api() as (host, seen):
            spec, _image = _deck(tmp)
            done = _run(spec, {"MINIMAX_API_KEY": "test-key", "MINIMAX_API_HOST": host})
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            self.assertIn("--brief", done.stdout + done.stderr)
            self.assertEqual(seen, [])

    def test_bad_response_is_reported_without_a_fallback_image(self) -> None:
        """远端出错时不产降级图：交付里少一张图，好过混进一张没人认领的图。"""
        with tempfile.TemporaryDirectory() as tmp:
            spec, image = _deck(tmp)
            _contract(tmp, image, FILLED)
            with _fake_api(blob=b"<html>not an image</html>") as (host, _seen):
                done = _run(spec, {"MINIMAX_API_KEY": "test-key",
                                   "MINIMAX_API_HOST": host})
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            self.assertFalse(os.path.isfile(os.path.join(tmp, image)), "写出了坏字节")
            out = done.stdout + done.stderr
            # 不静默：说清没有降级产物，并给出手动那条路
            self.assertIn("没有降级产物", out)
            self.assertIn("--check", out)


class TestNoDoubleSpend(unittest.TestCase):
    """钱是真花的：已出的图不重出、同一提示词重跑命中缓存。"""

    def test_existing_image_is_not_regenerated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _fake_api() as (host, seen):
            spec, image = _deck(tmp)
            _contract(tmp, image, FILLED)
            Image.new("RGB", (1536, 1024), (10, 20, 30)).save(os.path.join(tmp, image))
            done = _run(spec, {"MINIMAX_API_KEY": "test-key", "MINIMAX_API_HOST": host})
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(seen, [], "已有的图被重出一遍（重复付费）")
            self.assertIn("已存在", done.stdout + done.stderr)

    def test_same_prompt_hits_the_cache(self) -> None:
        """删掉产物再跑一遍：同一提示词 + 同一色板 = 同一把缓存 key，不该再调一次。"""
        with tempfile.TemporaryDirectory() as tmp, _fake_api() as (host, seen):
            spec, image = _deck(tmp)
            _contract(tmp, image, FILLED)
            env = {"MINIMAX_API_KEY": "test-key", "MINIMAX_API_HOST": host}
            first = _run(spec, env)
            self.assertEqual(first.returncode, 0, first.stdout + first.stderr)
            self.assertEqual(len(seen), 1)
            os.remove(os.path.join(tmp, image))
            second = _run(spec, env)
            self.assertEqual(second.returncode, 0, second.stdout + second.stderr)
            self.assertEqual(len(seen), 1, "同一提示词又调了一次（重复付费）")
            self.assertIn("缓存", second.stdout + second.stderr)
            self.assertTrue(os.path.isfile(os.path.join(tmp, image)))


class TestBackendPriority(unittest.TestCase):
    """两条直连的路都给时，用你的命令（内置那条只是没配时的方便路）。"""

    def test_provider_cmd_wins_over_the_builtin(self) -> None:
        with tempfile.TemporaryDirectory() as tmp, _fake_api() as (host, seen):
            spec, image = _deck(tmp)
            _contract(tmp, image, FILLED)
            marker = os.path.join(tmp, "provider-was-called")
            # 假 provider：留痕 + 写一张真图（真被调过，产物就在）
            script = os.path.join(tmp, "fake_provider.py")
            with open(script, "w", encoding="utf-8") as fh:
                fh.write("import sys\n"
                         "from PIL import Image\n"
                         f"open({marker!r}, 'w', encoding='utf-8').write('called')\n"
                         "Image.new('RGB', (1536, 1024), (7, 8, 9)).save(sys.argv[2])\n")
            env = {"MINIMAX_API_KEY": "test-key", "MINIMAX_API_HOST": host}
            done = _run(spec, env, "--provider-cmd", f"{sys.executable} {script} {{prompt}} {{out}}")
            self.assertEqual(done.returncode, 0, done.stdout + done.stderr)
            self.assertEqual(seen, [], "给了 provider-cmd 还去调内置后端")
            self.assertTrue(os.path.isfile(marker), "provider-cmd 没被调用")
            self.assertTrue(os.path.isfile(os.path.join(tmp, image)))

    def test_non_http_host_is_refused(self) -> None:
        """`MINIMAX_API_HOST` 来自环境变量：不给 scheme 把关就会去读本机文件。"""
        with tempfile.TemporaryDirectory() as tmp:
            spec, image = _deck(tmp)
            _contract(tmp, image, FILLED)
            done = _run(spec, {"MINIMAX_API_KEY": "test-key",
                               "MINIMAX_API_HOST": "file:///etc"})
            self.assertEqual(done.returncode, 1, done.stdout + done.stderr)
            out = done.stdout + done.stderr
            self.assertIn("http", out)
            self.assertNotIn("Traceback", out)
            self.assertFalse(os.path.isfile(os.path.join(tmp, image)))


class TestRatioTable(unittest.TestCase):
    """比例映射本身（纯函数）：八档都能命中自己，极端值不炸。"""

    def setUp(self) -> None:
        import importlib.util
        spec = importlib.util.spec_from_file_location("image_source_probe", IMAGE_SOURCE)
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        self.mod = module

    def test_every_official_step_maps_to_itself(self) -> None:
        for w, h in self.mod.MINIMAX_RATIOS:
            self.assertEqual(self.mod.minimax_ratio(w / h), f"{w}:{h}")

    def test_extremes_do_not_raise(self) -> None:
        """槽位量出 0 或没有槽位时不能炸 —— 比例本来就不阻塞交付。"""
        self.assertEqual(self.mod.minimax_ratio(0), "3:2")
        self.assertEqual(self.mod.minimax_ratio(None), "3:2")
        self.assertEqual(self.mod.minimax_ratio(-1), "3:2")
        self.assertIn(self.mod.minimax_ratio(99.0), {"21:9", "16:9"})


if __name__ == "__main__":
    unittest.main()
