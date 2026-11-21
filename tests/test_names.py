"""backend/names.py: an install and the plugins from before the project was renamed keep working."""
from backend import names


def test_env_reads_the_new_name_first(monkeypatch):
    monkeypatch.delenv("REINS_PORT", raising=False)
    monkeypatch.delenv("VERICLASS_PORT", raising=False)
    assert names.env("PORT") is None
    assert names.env("PORT", "8010") == "8010"
    monkeypatch.setenv("VERICLASS_PORT", "8020")  # an .env written before the rename
    assert names.env("PORT") == "8020"
    monkeypatch.setenv("REINS_PORT", "8030")
    assert names.env("PORT") == "8030"
    monkeypatch.setenv("REINS_PORT", "")  # empty counts as not set
    assert names.env("PORT") == "8020"


def test_headers_in_both_spellings():
    assert names.header({"X-Reins-Render": "markdown"}, "Render") == "markdown"
    assert names.header({"X-VeriClass-Render": "markdown"}, "Render") == "markdown"  # an older plugin
    assert names.header({}, "Render") == ""
    assert names.response_headers("Reask", "Sonnet") == {"X-Reins-Reask": "Sonnet", "X-VeriClass-Reask": "Sonnet"}


def test_an_older_install_keeps_its_database_and_private_folder(tmp_path):
    assert names.default_db(tmp_path) == tmp_path / "reins.db"  # a new install
    (tmp_path / "vericlass.db").write_bytes(b"")
    assert names.default_db(tmp_path) == tmp_path / "vericlass.db"  # an install from before the rename
    (tmp_path / "reins.db").write_bytes(b"")
    assert names.default_db(tmp_path) == tmp_path / "reins.db"

    assert names.private_dir(tmp_path) is None
    (tmp_path / "VeriClassPrivateData").mkdir()
    assert names.private_dir(tmp_path) == tmp_path / "VeriClassPrivateData"
    (tmp_path / "ReinsPrivateData").mkdir()
    assert names.private_dir(tmp_path) == tmp_path / "ReinsPrivateData"


def test_plugin_name_can_be_the_one_an_older_plugin_shows(monkeypatch):
    monkeypatch.delenv("REINS_PLUGIN_NAME", raising=False)
    monkeypatch.delenv("VERICLASS_PLUGIN_NAME", raising=False)
    assert names.plugin_name() == "REINS Edu"
    monkeypatch.setenv("REINS_PLUGIN_NAME", " Older Name ")
    assert names.plugin_name() == "Older Name"
