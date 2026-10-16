from app.api.routes_voice import parse


def test_known_commands():
    assert parse("Banyan, approve")["intent"] == "approve"
    assert parse("approve.")["intent"] == "approve"
    r = parse("reject it looks unsafe")
    assert r["intent"] == "reject" and r["text"] == "it looks unsafe"
    assert parse("pause")["intent"] == "pause"
    assert parse("Resume")["intent"] == "resume"
    assert parse("stop that branch")["intent"] == "prune"
    assert parse("what's happening?")["intent"] == "status"
    assert parse("show me the code")["intent"] == "show_code"
    assert parse("show the system map") == {"intent": "view", "target": "map", "text": None}
    assert parse("open timeline")["target"] == "timeline"
    assert parse("send a payment email")["intent"] == "demo_email"
    assert parse("منظور")["intent"] == "approve"


def test_everything_else_is_a_goal():
    r = parse("Banyan, track the gold price every hour")
    assert r == {"intent": "new_goal", "target": None, "text": "track the gold price every hour"}
    assert parse("Approximately how far is Lahore from Karachi?")["intent"] == "new_goal"
