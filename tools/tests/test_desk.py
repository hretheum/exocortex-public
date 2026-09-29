import http.client
import json
import re
import socket
import threading
from pathlib import Path

import pytest

from tools.gate import desk as desk_mod
from tools.gate.desk import ConfigError, DeskConfig, load_token, make_server
from tools.publisher.quarantine import Store

TOKEN = "t" * 32
H = [c * 64 for c in "abcdef"]
STATIC = Path(desk_mod.__file__).parent / "desk_static"


class FakeProvider:
    def card(self, finding):
        return {"finding_id": finding["id"], "public": "<script>alert(1)</script> public", "hint": "h",
                "neighbours": [{"score": 0.9, "text": "protected", "source": "notes/a.md", "note_path": "notes/a.md",
                                "folder_path": "notes/"}]}


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture()
def env(tmp_path):
    hard = tmp_path / "hard.txt"
    hard.write_text("protected-area/\n")
    store = Store(tmp_path / "q.sqlite3", never_exclude_file=hard)
    port = free_port()
    cfg = DeskConfig(db=tmp_path / "q.sqlite3", token=TOKEN, port=port, state=tmp_path)
    server = make_server(cfg, store, FakeProvider())
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield type("Env", (), {"store": store, "port": port, "cfg": cfg, "tmp": tmp_path})
    server.shutdown()
    server.server_close()
    store.close()


def call(env, method, path, body=None, headers=None, token=True, raw=None):
    conn = http.client.HTTPConnection("127.0.0.1", env.port, timeout=10)
    hdrs = {"Host": f"127.0.0.1:{env.port}"}
    if token:
        hdrs["Authorization"] = f"Bearer {TOKEN}"
    hdrs.update(headers or {})
    data = raw
    if body is not None:
        data = json.dumps(body)
        hdrs.setdefault("Content-Type", "application/json")
    conn.request(method, path, body=data, headers=hdrs)
    r = conn.getresponse()
    payload = r.read()
    conn.close()
    return r, payload


def jcall(env, method, path, body=None, **kw):
    r, payload = call(env, method, path, body, **kw)
    return r.status, json.loads(payload or b"{}")


def seed(store, findings, key="exp-a", cls="experiment"):
    store.sync_unit(cls, key, sorted({f["path"] for f in findings}), "s1", findings)
    return store.list_units()[0]["id"]


def sem(path, h, score=0.95, rule="semantic"):
    return {"rule": rule, "path": path, "para_hash": h, "score": score}


def login(env):
    r, _ = call(env, "POST", "/login", {"token": TOKEN}, token=False)
    assert r.status == 200
    cookie = r.getheader("Set-Cookie")
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie
    sess = cookie.split(";")[0]
    page, html = call(env, "GET", "/", headers={"Cookie": sess}, token=False)
    csrf = re.search(rb'name="csrf-token" content="([0-9a-f]+)"', html).group(1).decode()
    return sess, csrf


# -- configuration ------------------------------------------------------------------------------

def test_no_token_file_means_no_start(monkeypatch, tmp_path, capsys):
    monkeypatch.delenv("GATE_DESK_TOKEN_FILE", raising=False)
    with pytest.raises(ConfigError):
        DeskConfig.from_env()
    assert desk_mod.serve() == 2
    assert "token" in capsys.readouterr().err
    with pytest.raises(ConfigError):
        load_token(tmp_path / "missing")
    short = tmp_path / "short"
    short.write_text("abc\n")
    with pytest.raises(ConfigError):
        load_token(short)
    ok = tmp_path / "ok"
    ok.write_text(TOKEN + "\n")
    monkeypatch.setenv("GATE_DESK_TOKEN_FILE", str(ok))
    monkeypatch.setenv("GATE_STATE", str(tmp_path / "state"))
    cfg = DeskConfig.from_env()
    assert cfg.token == TOKEN and cfg.host == "127.0.0.1"  # loopback by default


# -- authentication -----------------------------------------------------------------------------

def test_401_without_token(env):
    for path in ("/api/units", "/api/rules", "/api/history", "/api/findings/1/card"):
        assert jcall(env, "GET", path, token=False)[0] == 401
    assert jcall(env, "POST", "/api/undo", {}, token=False)[0] == 401
    assert jcall(env, "GET", "/api/units", headers={"Authorization": "Bearer wrong"}, token=False)[0] == 401
    r, html = call(env, "GET", "/", token=False)
    assert r.status == 401 and b"login-form" in html and b"csrf-token" not in html


def test_bearer_token_works(env):
    assert jcall(env, "GET", "/api/units")[0] == 200


def test_login_and_throttle(env):
    assert jcall(env, "POST", "/login", {"token": "nope"}, token=False)[0] == 401
    sess, csrf = login(env)
    assert jcall(env, "GET", "/api/units", headers={"Cookie": sess}, token=False)[0] == 200
    for _ in range(12):
        code = jcall(env, "POST", "/login", {"token": "nope"}, token=False)[0]
    assert code == 429
    assert csrf


def test_wrong_host_is_refused(env):
    assert jcall(env, "GET", "/api/units", headers={"Host": "evil.example"})[0] == 421


# -- CSRF ---------------------------------------------------------------------------------------

def test_csrf_protection_on_cookie_sessions(env):
    seed(env.store, [sem("en/experiments/exp-a/a.md", H[0])])
    sess, csrf = login(env)
    body = {"decision": "keep"}
    url = "/api/findings/1/decide"
    no_header = {"Cookie": sess}
    assert jcall(env, "POST", url, body, headers=no_header, token=False)[0] == 403
    assert jcall(env, "POST", url, body, headers={**no_header, "X-CSRF-Token": "0" * 64}, token=False)[0] == 403
    evil = {**no_header, "X-CSRF-Token": csrf, "Origin": "http://evil.example"}
    assert jcall(env, "POST", url, body, headers=evil, token=False)[0] == 403
    cross = {**no_header, "X-CSRF-Token": csrf, "Sec-Fetch-Site": "cross-site"}
    assert jcall(env, "POST", url, body, headers=cross, token=False)[0] == 403
    assert env.store.approved_hashes() == set()
    good = {**no_header, "X-CSRF-Token": csrf, "Origin": f"http://127.0.0.1:{env.port}"}
    assert jcall(env, "POST", url, body, headers=good, token=False)[0] == 200
    assert env.store.approved_hashes() == {H[0]}


def test_post_needs_json_and_small_body(env):
    r, _ = call(env, "POST", "/api/undo", raw="a=b", headers={"Content-Type": "application/x-www-form-urlencoded"})
    assert r.status == 415
    assert jcall(env, "POST", "/api/undo", raw="x" * (70 * 1024), headers={"Content-Type": "application/json"})[0] == 400
    assert jcall(env, "POST", "/api/undo", raw="[1]", headers={"Content-Type": "application/json"})[0] == 400


def test_bearer_posts_need_no_csrf_header(env):
    assert jcall(env, "POST", "/api/undo", {})[0] == 200


# -- headers and page ---------------------------------------------------------------------------

def test_no_store_on_every_response(env):
    seed(env.store, [sem("en/experiments/exp-a/a.md", H[0])])
    for method, path, kw in [("GET", "/", {}), ("GET", "/", {"token": False}), ("GET", "/api/units", {}),
                             ("GET", "/api/units", {"token": False}), ("GET", "/static/desk.js", {}),
                             ("GET", "/static/desk.css", {"token": False}), ("GET", "/nope", {}),
                             ("GET", "/static/other.txt", {}), ("POST", "/login", {"token": False, "body": {"token": "x"}}),
                             ("GET", "/api/units/999", {})]:
        r, _ = call(env, method, path, kw.pop("body", None), **kw)
        assert r.getheader("Cache-Control") == "no-store", (path, r.status)
        assert "default-src 'none'" in r.getheader("Content-Security-Policy")


EXTERNAL = re.compile(r"(https?:)?//[a-z0-9.-]+\.[a-z]{2,}|@import|url\(\s*['\"]?(https?:|//)|\bimport\s*\(|\bWebSocket\b|\bXMLHttpRequest\b", re.I)


def test_pages_request_nothing_external(env):
    _, page = call(env, "GET", "/")
    _, login_page = call(env, "GET", "/", token=False)
    for html in (page.decode(), login_page.decode()):
        refs = re.findall(r'(?:src|href|action)="([^"]*)"', html)
        assert refs and all(r.startswith("/static/") or r == "" for r in refs), refs
        assert "<iframe" not in html and "<link rel=\"preconnect" not in html
        assert "<script>" not in html  # scripts are files of the same origin
    for name in ("desk.js", "logic.js", "md.js", "desk.css"):
        text = (STATIC / name).read_text()
        assert not EXTERNAL.search(text), name
    js = (STATIC / "desk.js").read_text() + (STATIC / "logic.js").read_text() + (STATIC / "md.js").read_text()
    assert not re.search(r"outerHTML|insertAdjacentHTML|document\.write|\beval\(|new Function", js)
    # the one place that takes HTML: the output of marked, cleaned by DOMPurify
    assert js.count("innerHTML") == 1 and "DOMPurify.sanitize(html" in js
    assert re.findall(r"fetch\(([^,]+),", js) and all(m.strip().startswith(('"/', "path")) for m in re.findall(r"fetch\(([^,]+),", js))


def test_request_content_is_never_logged(env, capfd):
    marker = "SENTINEL-NOTE-TEXT"
    seed(env.store, [sem("en/experiments/exp-a/a.md", H[0])])
    jcall(env, "POST", "/api/findings/1/decide", {"decision": "to_edit", "note": marker})
    jcall(env, "GET", f"/api/units/1?x={marker}")
    out = capfd.readouterr()
    assert marker not in out.out + out.err


# -- API ----------------------------------------------------------------------------------------

def test_queue_and_unit_views(env):
    uid = seed(env.store, [sem("en/experiments/exp-a/a.md", H[0]), sem("en/experiments/exp-a/sub/b.md", H[1], 0.8)])
    code, q = jcall(env, "GET", "/api/units")
    [u] = q["units"]
    assert code == 200 and (u["key"], u["cls"], u["findings"], u["state"], u["age_days"]) == ("exp-a", "experiment", 2, "open", 0)
    _, v = jcall(env, "GET", f"/api/units/{uid}")
    assert v["progress"] == {"total": 2, "decided": 0, "to_edit": 0, "open": 2}
    assert set(v["bulk"]["folders"]) == {"en/experiments/exp-a/", "en/experiments/exp-a/sub/"}
    assert "ids" not in v["bulk"]["unit"]
    assert jcall(env, "GET", "/api/units/999")[0] == 404
    code, card = jcall(env, "GET", "/api/findings/1/card")
    assert code == 200 and card["neighbours"][0]["note_path"] == "notes/a.md"


def test_decisions_progress_and_undo(env):
    uid = seed(env.store, [sem("en/experiments/exp-a/a.md", H[0]), sem("en/experiments/exp-a/b.md", H[1])])
    assert jcall(env, "POST", "/api/findings/1/decide", {"decision": "keep"})[0] == 200
    code, r = jcall(env, "POST", "/api/findings/2/decide", {"decision": "to_edit", "note": "reword it"})
    assert r["progress"] == {"total": 2, "decided": 2, "to_edit": 1, "open": 0}
    assert jcall(env, "POST", "/api/findings/1/decide", {"decision": "maybe"})[0] == 400
    code, u = jcall(env, "POST", "/api/undo", {})
    assert u["undone"]["findings"] == [2]
    assert env.store.progress(uid)["decided"] == 1
    hist = jcall(env, "GET", "/api/history")[1]["history"]
    assert hist[0]["decision"] == "undo" and all("text" not in h and "note" not in h for h in hist)


def test_a_decided_finding_can_be_reopened_through_the_api(env):
    uid = seed(env.store, [sem("en/experiments/exp-a/a.md", H[0])])
    assert jcall(env, "POST", "/api/findings/1/reopen", {}, token=False)[0] == 401
    assert jcall(env, "POST", "/api/findings/1/reopen", {})[0] == 409  # still open
    jcall(env, "POST", "/api/findings/1/decide", {"decision": "keep"})
    code, r = jcall(env, "POST", "/api/findings/1/reopen", {})
    assert code == 200 and r["finding"]["state"] == "open" and r["progress"]["open"] == 1
    assert env.store.get_unit(uid)["state"] == "open"
    assert jcall(env, "POST", "/api/findings/99/reopen", {})[0] == 404


def test_publish_request_writes_a_file_once_and_reports_the_last_run(env):
    assert jcall(env, "POST", "/api/publish", {}, token=False)[0] == 401
    code, r = jcall(env, "GET", "/api/publish")
    assert code == 200 and r == {"configured": True, "pending": False, "last": None}
    (env.tmp / "runs.jsonl").write_text(
        json.dumps({"time": "2026-09-29T18:07:26+00:00", "status": "ok", "published": ["a.md", "b.md"],
                    "held": {"c.md": ["simcheck"]}, "pushed": True}) + "\n" + "not json\n")
    assert jcall(env, "GET", "/api/publish")[1]["last"] == {"time": "2026-09-29T18:07:26+00:00", "status": "ok",
                                                            "published": 2, "held": 1, "pushed": True}
    assert jcall(env, "POST", "/api/publish", {}) == (200, {"requested": True, "already": False})
    assert json.loads((env.tmp / "publish-request").read_text())["who"] == "owner"
    assert jcall(env, "POST", "/api/publish", {}) == (200, {"requested": True, "already": True})
    assert jcall(env, "GET", "/api/publish")[1]["pending"] is True


def test_publish_request_needs_a_state_folder(env):
    env.cfg.state = None
    assert jcall(env, "POST", "/api/publish", {})[0] == 503
    assert jcall(env, "GET", "/api/publish")[1] == {"configured": False, "pending": False, "last": None}


def test_literal_cannot_be_kept_through_the_api(env):
    seed(env.store, [sem("en/experiments/exp-a/a.md", H[0], rule="leakgate:name")])
    assert jcall(env, "POST", "/api/findings/1/decide", {"decision": "keep"})[0] == 409
    assert env.store.approved_hashes() == set()


def test_bulk_actions_need_confirmation(env):
    uid = seed(env.store, [sem("en/experiments/exp-a/a.md", H[0], 0.9), sem("en/experiments/exp-a/b.md", H[1], 0.93)])
    _, pv = jcall(env, "GET", f"/api/units/{uid}/bulk")
    assert (pv["files"], pv["paragraphs"], pv["max_score"], pv["disabled"]) == (2, 2, 0.93, False)
    url = f"/api/units/{uid}/bulk"
    assert jcall(env, "POST", url, {"digest": pv["digest"]})[0] == 400  # no confirmation
    assert jcall(env, "POST", url, {"digest": "x" * 24, "confirm": True})[0] == 409  # stale summary
    assert env.store.approved_hashes() == set()
    code, r = jcall(env, "POST", url, {"digest": pv["digest"], "confirm": True})
    assert code == 200 and r["paragraphs"] == 2 and env.store.approved_hashes() == {H[0], H[1]}
    assert jcall(env, "POST", "/api/undo", {})[1]["undone"]["findings"] == [1, 2]
    assert env.store.approved_hashes() == set()


def test_bulk_refused_with_literal_findings(env):
    uid = seed(env.store, [sem("en/experiments/exp-a/a.md", H[0]), sem("en/experiments/exp-a/b.md", H[1], rule="literal")])
    _, pv = jcall(env, "GET", f"/api/units/{uid}/bulk")
    assert pv["disabled"] and pv["reason"]
    assert jcall(env, "POST", f"/api/units/{uid}/bulk", {"digest": pv["digest"], "confirm": True})[0] == 409
    assert env.store.approved_hashes() == set()


def test_standing_rules_through_the_api(env):
    seed(env.store, [sem("en/experiments/exp-a/a.md", H[0]), sem("en/experiments/exp-a/b.md", H[1], rule="literal")])
    assert jcall(env, "POST", "/api/rules/standing", {"folder": "en/experiments/exp-a/", "reason": ""})[0] == 400
    code, r = jcall(env, "POST", "/api/rules/standing", {"folder": "en/experiments/exp-a/", "reason": "reviewed"})
    assert code == 200 and r["applied"] == 1
    rules = jcall(env, "GET", "/api/rules")[1]
    assert rules["standing"][0]["active"] and rules["hard_list"] == {"available": True, "entries": 1}
    assert jcall(env, "POST", f"/api/rules/standing/{r['id']}/revoke", {})[0] == 200
    assert env.store.approved_hashes() == set()


def test_exclusions_through_the_api(env):
    assert jcall(env, "POST", "/api/exclusions", {"path": "protected-area/x.md", "scope": "note", "reason": "why not"})[0] == 403
    assert jcall(env, "POST", "/api/exclusions", {"path": "notes/a.md", "scope": "note", "reason": ""})[0] == 400
    assert jcall(env, "POST", "/api/exclusions", {"path": "notes/a.md", "scope": "weird", "reason": "why not"})[0] == 400
    code, r = jcall(env, "POST", "/api/exclusions", {"path": "notes/", "scope": "folder", "reason": "public texts", "days": 30})
    assert code == 200 and r["path"] == "notes/" and env.store.active_exclusion_paths() == ["notes/"]
    assert jcall(env, "POST", f"/api/exclusions/{r['id']}/revoke", {})[0] == 200
    assert env.store.active_exclusion_paths() == []


def test_exclusions_refused_without_hard_list(env):
    env.store.never_exclude_file = env.tmp / "gone.txt"
    code, r = jcall(env, "POST", "/api/exclusions", {"path": "notes/a.md", "scope": "note", "reason": "why not"})
    assert code == 503 and env.store.active_exclusion_paths() == []
